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


def _build_structures(gs: GameState, faction_id: str, owned_planets) -> None:
    faction = gs.factions[faction_id]
    for planet in owned_planets:
        if len(planet.buildings) >= planet.slots:
            continue

        budget = max(0, faction.treasury - 120)
        if budget <= 0:
            break

        options = [b for b in gs.buildings_db.keys() if b not in planet.buildings]
        if not options:
            continue

        needs_military = planet.military < 2
        needs_stability = planet.stability < 50
        economy_low = faction.treasury < 450

        priorities = []
        if needs_stability:
            priorities.extend(["Security Bureau"])
        if needs_military:
            priorities.extend(["Barracks", "Vehicle Depot"])
        if economy_low:
            priorities.extend(["Trade Port", "Factory"])
        priorities.extend(["Trade Port", "Factory", "Barracks", "Vehicle Depot"])

        selected = next((name for name in priorities if name in options), options[0])
        cost = gs.buildings_db[selected]["cost"]
        if faction.treasury >= cost and cost <= budget:
            faction.treasury -= cost
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


def _recruit_units(gs: GameState, faction_id: str, owned_planets) -> None:
    faction = gs.factions[faction_id]
    roster = gs.unit_db[faction_id]

    for planet in owned_planets:
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
        if not stationed or faction.treasury <= 120:
            continue

        enemy_adjacent = any(
            gs.planets[n].owner not in (faction_id, "neutral") for n in planet.connections
        )
        local_armies = [a for a in gs.armies.values() if a.faction_id == faction_id and a.planet == planet.name]
        local_power = sum(_army_power(a) for a in local_armies)
        min_power_goal = 180 if enemy_adjacent else 120

        if local_power >= min_power_goal and faction.treasury < 400:
            continue

        recruit_pool.sort(key=lambda unit: (_template_power(unit), -unit["cost"]), reverse=True)
        template = next((u for u in recruit_pool if u["cost"] <= faction.treasury), None)
        if template:
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
