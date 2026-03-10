from __future__ import annotations

import random
from collections import deque

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

    posture = _strategic_posture(gs, faction_id)
    recruit_budget, build_budget = _spending_plan(gs, faction_id, posture)

    # Under pressure, raise troops first. When comfortable, invest in infrastructure first.
    if posture >= 0.55:
        _recruit_units(gs, faction_id, owned, posture, recruit_budget)
        _build_structures(gs, faction_id, owned, posture, build_budget)
    else:
        _build_structures(gs, faction_id, owned, posture, build_budget)
        _recruit_units(gs, faction_id, owned, posture, recruit_budget)

    _move_armies(gs, faction_id, posture)


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


def _faction_total_power(gs: GameState, faction_id: str) -> float:
    return sum(_army_power(a) for a in gs.armies.values() if a.faction_id == faction_id)


def _frontier_pressure(gs: GameState, faction_id: str) -> float:
    owned = [p for p in gs.planets.values() if p.owner == faction_id]
    if not owned:
        return 0.0

    threatened = 0
    for planet in owned:
        if any(gs.planets[n].owner == gs.player_faction for n in planet.connections):
            threatened += 1
    return threatened / max(1, len(owned))


def _strategic_posture(gs: GameState, faction_id: str) -> float:
    """0..1 where higher means stronger military urgency against the player."""
    ai_planets = sum(1 for p in gs.planets.values() if p.owner == faction_id)
    player_planets = sum(1 for p in gs.planets.values() if p.owner == gs.player_faction)
    ai_power = _faction_total_power(gs, faction_id)
    player_power = _faction_total_power(gs, gs.player_faction)

    planet_pressure = player_planets / max(1, ai_planets + player_planets)
    military_pressure = player_power / max(1.0, ai_power + player_power)
    frontier_pressure = _frontier_pressure(gs, faction_id)

    # Heavier emphasis on military/frontline state to keep AI threatening but not reckless.
    weighted = planet_pressure * 0.35 + military_pressure * 0.4 + frontier_pressure * 0.25
    return min(1.0, max(0.0, weighted))


def _spending_plan(gs: GameState, faction_id: str, posture: float) -> tuple[int, int]:
    """Return (recruit_budget, build_budget) for this AI turn."""
    treasury = gs.factions[faction_id].treasury

    # Higher posture => more recruitment. Lower posture => more buildings.
    recruit_ratio = 0.38 + posture * 0.34
    build_ratio = 0.44 - posture * 0.18

    recruit_budget = int(treasury * recruit_ratio)
    build_budget = int(treasury * build_ratio)

    # Always retain a reserve so AI can react next turns.
    reserve = max(180, int(treasury * 0.16))
    available = max(0, treasury - reserve)
    total = recruit_budget + build_budget
    if total > available and total > 0:
        scale = available / total
        recruit_budget = int(recruit_budget * scale)
        build_budget = int(build_budget * scale)

    return recruit_budget, build_budget


def _planet_threat(gs: GameState, faction_id: str, planet) -> int:
    hostile_neighbors = sum(1 for n in planet.connections if gs.planets[n].owner not in (faction_id, "neutral"))
    player_neighbors = sum(1 for n in planet.connections if gs.planets[n].owner == gs.player_faction)
    neutral_neighbors = sum(1 for n in planet.connections if gs.planets[n].owner == "neutral")
    return hostile_neighbors * 2 + neutral_neighbors + player_neighbors * 2


def _planet_has_faction_army(gs: GameState, planet_name: str, faction_id: str) -> bool:
    return any(a.planet == planet_name and a.faction_id == faction_id and len(a.units) > 0 for a in gs.armies.values())


def _distance_to_player_objective(gs: GameState, start_planet: str) -> int | None:
    """Shortest hops from start_planet to any player-owned or player-army planet."""
    queue = deque([(start_planet, 0)])
    visited = {start_planet}

    while queue:
        current, distance = queue.popleft()
        if gs.planets[current].owner == gs.player_faction or _planet_has_faction_army(gs, current, gs.player_faction):
            return distance

        for nxt in gs.planets[current].connections:
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, distance + 1))
    return None


def _building_score(gs: GameState, faction_id: str, planet, building_name: str, posture: float) -> float:
    b = gs.buildings_db[building_name]
    threat = _planet_threat(gs, faction_id, planet)
    effective_order = planet.stability + sum(gs.buildings_db[x].get("order", 0) for x in planet.buildings) - planet.unrest

    military_weight = 18 + int(18 * posture)
    economy_weight = 1.0 + (1.0 - posture) * 0.75

    score = 0.0
    score += b.get("income", 0) * 1.4 * economy_weight
    score += b.get("trade", 0) * 0.8 * economy_weight
    score += b.get("industry", 0) * 0.7 * economy_weight
    score += b.get("military", 0) * (military_weight if threat > 0 else 13 + int(7 * posture))
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
        score += 18 + int((1.0 - posture) * 10)

    return score


def _build_structures(gs: GameState, faction_id: str, owned_planets, posture: float, build_budget: int) -> None:
    faction = gs.factions[faction_id]
    spent = 0

    while faction.treasury >= 240 and spent < build_budget:
        best_choice = None

        for planet in owned_planets:
            if len(planet.buildings) >= planet.slots:
                continue

            options = [b for b in gs.buildings_db.keys() if b not in planet.buildings]
            affordable = [
                b for b in options
                if gs.buildings_db[b]["cost"] <= faction.treasury and spent + gs.buildings_db[b]["cost"] <= build_budget
            ]
            if not affordable:
                continue

            for option in affordable:
                score = _building_score(gs, faction_id, planet, option, posture)
                if best_choice is None or score > best_choice[0]:
                    best_choice = (score, planet, option)

        if best_choice is None:
            break

        _, planet, selected = best_choice
        cost = gs.buildings_db[selected]["cost"]
        faction.treasury -= cost
        spent += cost
        planet.buildings.append(selected)
        planet.military += gs.buildings_db[selected].get("military", 0)


def _move_armies(gs: GameState, faction_id: str, posture: float) -> None:
    faction = gs.factions[faction_id]
    armies = sorted(
        [a for a in gs.armies.values() if a.faction_id == faction_id and a.movement > 0 and a.can_move],
        key=_army_power,
        reverse=True,
    )

    for army in armies:
        planet = gs.planets[army.planet]
        if not planet.connections:
            continue

        our_power = _army_power(army)
        scored_targets = []

        for neighbor in planet.connections:
            neighbor_planet = gs.planets[neighbor]
            if neighbor_planet.owner == "revolutionaries":
                continue

            defenders = [
                other for other in gs.armies.values() if other.planet == neighbor and other.faction_id != faction_id
            ]
            if any(defender.faction_id == "revolutionaries" for defender in defenders):
                continue
            defender_power = sum(_army_power(defender) for defender in defenders)

            if neighbor_planet.owner == gs.player_faction:
                owner_score = 150 + int(35 * posture)
            elif neighbor_planet.owner == "neutral":
                owner_score = 68 + int(12 * (1.0 - posture))
            elif neighbor_planet.owner == faction_id:
                owner_score = -35
            else:
                owner_score = 38

            player_armies_present = any(defender.faction_id == gs.player_faction for defender in defenders)
            army_objective_score = (95 + int(35 * posture)) if player_armies_present else (30 if defenders else 0)

            if defender_power <= 0:
                strength_score = 25
            elif our_power >= defender_power * 1.2:
                strength_score = 70
            elif our_power >= defender_power * 0.9:
                strength_score = 30
            elif our_power >= defender_power * 0.75:
                strength_score = -10
            else:
                strength_score = -85

            value_score = neighbor_planet.base_income * 2 + neighbor_planet.military * 8
            player_distance = _distance_to_player_objective(gs, neighbor)
            proximity_score = 0 if player_distance is None else max(0, 28 - player_distance * 5)
            total = owner_score + army_objective_score + strength_score + value_score + proximity_score - int(defender_power * 0.18)
            scored_targets.append((total, neighbor, defender_power))

        scored_targets.sort(key=lambda item: item[0], reverse=True)
        if not scored_targets:
            continue

        _, target, defender_power = scored_targets[0]

        # Fairness guardrail: avoid clearly suicidal attacks.
        min_ratio = 0.8 - posture * 0.08
        if defender_power > 0 and our_power < defender_power * min_ratio:
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


def _pick_recruit_template(recruit_pool: list[dict], treasury: int, player_adjacent: bool) -> dict | None:
    affordable = [u for u in recruit_pool if u["cost"] <= treasury]
    if not affordable:
        return None

    if player_adjacent:
        affordable.sort(key=lambda unit: (_template_power(unit), -unit["cost"]), reverse=True)
    else:
        affordable.sort(
            key=lambda unit: ((_template_power(unit) / max(1, unit["cost"])), _template_power(unit)),
            reverse=True,
        )
    return affordable[0]


def _recruit_units(gs: GameState, faction_id: str, owned_planets, posture: float, recruit_budget: int) -> None:
    faction = gs.factions[faction_id]
    roster = gs.unit_db[faction_id]
    spent = 0

    for planet in sorted(
        owned_planets,
        key=lambda p: (_planet_threat(gs, faction_id, p), p.military, len(p.connections)),
        reverse=True,
    ):
        if spent >= recruit_budget:
            break

        if any(q["faction"] == faction_id and q["planet"] == planet.name for q in gs.recruit_queue):
            continue

        military_level = planet.military
        if military_level < 1:
            continue

        recruit_pool = [unit for unit in roster if unit["req"] <= military_level]
        if not recruit_pool:
            continue

        cheapest_cost = min(unit["cost"] for unit in recruit_pool)
        if faction.treasury < cheapest_cost:
            continue

        player_adjacent = any(gs.planets[n].owner == gs.player_faction for n in planet.connections)
        template = _pick_recruit_template(recruit_pool, faction.treasury, player_adjacent)
        if not template:
            continue

        cost = template["cost"]
        if spent + cost > recruit_budget:
            continue

        faction.treasury -= cost
        spent += cost
        gs.recruit_queue.append(
            {
                "faction": faction_id,
                "planet": planet.name,
                "unit": template["name"],
                "turns": max(1, 4 - planet.military),
            }
        )


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
