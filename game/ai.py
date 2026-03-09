from __future__ import annotations

import random

from game.state import Army, GameState, General, UnitCard


def run_ai_turn(gs: GameState, faction_id: str) -> None:
    """Run one strategic AI turn for a faction."""
    if faction_id == "revolutionaries":
        return
    faction = gs.factions[faction_id]
    owned = [p for p in gs.planets.values() if p.owner == faction_id]
    if not owned:
        faction.alive = False
        return

    _recruit_units(gs, faction_id, owned)
    _build_structures(gs, faction_id, owned)
    _move_armies(gs, faction_id)


def _unit_power(unit: UnitCard) -> float:
    return (
        unit.stats["damage"] * 2.5
        + unit.stats["health"] * 0.25
        + unit.stats["armor"] * 5.0
        + unit.stats["range"] * 2.0
    )


def _army_power(army: Army) -> float:
    return sum(_unit_power(unit) for unit in army.units if unit.hp > 0)


def _template_power(template: dict) -> float:
    return (
        template["damage"] * 2.5
        + template["health"] * 0.25
        + template["armor"] * 5.0
        + template["range"] * 2.0
    )


def _planet_threat(gs: GameState, faction_id: str, planet) -> int:
    hostile_neighbors = sum(1 for n in planet.connections if gs.planets[n].owner not in (faction_id, "neutral"))
    neutral_neighbors = sum(1 for n in planet.connections if gs.planets[n].owner == "neutral")
    return hostile_neighbors * 2 + neutral_neighbors


def _building_score(gs: GameState, faction_id: str, planet, building_name: str) -> float:
    b = gs.buildings_db[building_name]
    threat = _planet_threat(gs, faction_id, planet)
    effective_order = planet.stability + sum(gs.buildings_db[x].get("order", 0) for x in planet.buildings) - planet.unrest

    score = 0.0
    score += b.get("income", 0) * 1.4
    score += b.get("trade", 0) * 0.8
    score += b.get("industry", 0) * 0.7
    score += b.get("military", 0) * (32 if threat > 0 else 18)
    score += b.get("research", 0) * (0.5 if threat > 1 else 0.9)
    score += b.get("order", 0) * (7 if effective_order < 55 else 3)

    if threat > 0 and building_name in {"Barracks", "Vehicle Depot", "Security Bureau"}:
        score += 24
    if effective_order < 50 and building_name == "Security Bureau":
        score += 32
    if planet.military < 1 and building_name == "Barracks":
        score += 26
    if planet.military < 2 and building_name == "Vehicle Depot":
        score += 18
    if threat == 0 and building_name in {"Trade Port", "Factory"}:
        score += 18

    return score


def _build_structures(gs: GameState, faction_id: str, owned_planets) -> None:
    faction = gs.factions[faction_id]

    while faction.treasury >= 240:
        best_choice = None

        for planet in owned_planets:
            if len(planet.buildings) >= planet.slots:
                continue

            options = [b for b in gs.buildings_db.keys() if b not in planet.buildings]
            affordable = [b for b in options if gs.buildings_db[b]["cost"] <= faction.treasury]
            if not affordable:
                continue

            for option in affordable:
                score = _building_score(gs, faction_id, planet, option)
                if best_choice is None or score > best_choice[0]:
                    best_choice = (score, planet, option)

        if best_choice is None:
            break

        _, planet, selected = best_choice
        faction.treasury -= gs.buildings_db[selected]["cost"]
        planet.buildings.append(selected)
        planet.military += gs.buildings_db[selected].get("military", 0)


def _move_armies(gs: GameState, faction_id: str) -> None:
    faction = gs.factions[faction_id]
    for army in [a for a in gs.armies.values() if a.faction_id == faction_id and a.movement > 0 and a.can_move]:
        planet = gs.planets[army.planet]
        if not planet.connections:
            continue

        our_power = _army_power(army)

        scored_targets = []
        for neighbor in planet.connections:
            neighbor_planet = gs.planets[neighbor]
            defenders = [
                other for other in gs.armies.values() if other.planet == neighbor and other.faction_id != faction_id
            ]
            defender_power = sum(_army_power(defender) for defender in defenders)

            if neighbor_planet.owner == "neutral":
                owner_score = 60
            elif neighbor_planet.owner == faction_id:
                owner_score = 10
            else:
                owner_score = 100

            strength_score = 35 if our_power >= max(1, defender_power) * 0.8 else -40
            value_score = neighbor_planet.base_income * 2 + neighbor_planet.military * 8
            total = owner_score + strength_score + value_score - int(defender_power * 0.2)
            scored_targets.append((total, neighbor, defender_power))

        scored_targets.sort(key=lambda item: item[0], reverse=True)
        if not scored_targets:
            continue

        _, target, defender_power = scored_targets[0]
        if defender_power > 0 and our_power < defender_power * 0.7:
            continue
        army.planet = target
        army.movement -= 1

        defenders_present = any(
            other.planet == target and other.faction_id != faction_id and len(other.units) > 0
            for other in gs.armies.values()
        )

        if gs.planets[target].owner == "neutral":
            gs.planets[target].owner = faction_id
            gs.message = f"{faction.name} peacefully claims {target}."
        elif not defenders_present:
            gs.planets[target].owner = faction_id
            gs.message = f"{faction.name} captures undefended {target}."
        elif gs.planets[target].owner != faction_id:
            gs.message = f"{faction.name} attacks {target}!"


def _pick_recruit_template(recruit_pool: list[dict], treasury: int, enemy_adjacent: bool) -> dict | None:
    affordable = [u for u in recruit_pool if u["cost"] <= treasury]
    if not affordable:
        return None

    if enemy_adjacent:
        affordable.sort(key=lambda unit: (_template_power(unit), -unit["cost"]), reverse=True)
    else:
        affordable.sort(
            key=lambda unit: ((_template_power(unit) / max(1, unit["cost"])), _template_power(unit)),
            reverse=True,
        )
    return affordable[0]


def _recruit_units(gs: GameState, faction_id: str, owned_planets) -> None:
    faction = gs.factions[faction_id]
    roster = gs.unit_db[faction_id]

    for planet in sorted(owned_planets, key=lambda p: (_planet_threat(gs, faction_id, p), len(p.connections)), reverse=True):
        military_level = planet.military
        if military_level < 1:
            continue

        recruit_pool = [unit for unit in roster if unit["req"] <= military_level]
        if not recruit_pool:
            continue

        stationed = [
            army
            for army in gs.armies.values()
            if army.faction_id == faction_id and army.planet == planet.name
        ]
        if not stationed or faction.treasury <= 90:
            continue

        enemy_adjacent = any(gs.planets[n].owner not in (faction_id, "neutral") for n in planet.connections)
        min_power_goal = 280 if enemy_adjacent else 180

        spending_floor = 110
        loops = 0
        while faction.treasury > spending_floor:
            loops += 1
            if loops > 8:
                break

            local_armies = [a for a in gs.armies.values() if a.faction_id == faction_id and a.planet == planet.name]
            local_power = sum(_army_power(a) for a in local_armies)
            if local_power >= min_power_goal and faction.treasury < 560:
                break

            template = _pick_recruit_template(recruit_pool, faction.treasury, enemy_adjacent)
            if not template:
                break

            faction.treasury -= template["cost"]
            gs.armies[gs.next_army_id] = Army(
                id=gs.next_army_id,
                faction_id=faction_id,
                planet=planet.name,
                general=General(name="Field Commander"),
                units=[UnitCard.from_template(template)],
                movement=0,
            )
            gs.next_army_id += 1


def start_research_if_idle(gs: GameState, faction_id: str) -> None:
    fac = gs.factions[faction_id]
    if fac.research_target:
        return

    choices = [
        tech for tech in gs.tech_db if tech["id"] not in fac.unlocked_techs and tech["cost"] <= fac.treasury
    ]
    if not choices:
        return

    tech = random.choice(choices)
    fac.treasury -= tech["cost"]
    fac.research_target = tech["id"]
    fac.research_left = max(1, int(tech["turns"] / fac.research_mod))
