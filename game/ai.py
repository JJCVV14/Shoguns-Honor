from __future__ import annotations

import random

from game.state import GameState, UnitCard


def run_ai_turn(gs: GameState, faction_id: str) -> None:
    """Run one strategic AI turn for a faction."""
    faction = gs.factions[faction_id]
    owned = [p for p in gs.planets.values() if p.owner == faction_id]
    if not owned:
        faction.alive = False
        return

    _build_structures(gs, faction_id, owned)
    _move_armies(gs, faction_id)
    _recruit_units(gs, faction_id, owned)


def _build_structures(gs: GameState, faction_id: str, owned_planets) -> None:
    faction = gs.factions[faction_id]
    for planet in owned_planets:
        if len(planet.buildings) >= planet.slots or faction.treasury <= 220:
            continue

        # Prefer order buildings when unstable; otherwise pick weighted economic/military options.
        options = [b for b in gs.buildings_db.keys() if b not in planet.buildings]
        if not options:
            continue
        if planet.stability < 45 and "Security Bureau" in options:
            selected = "Security Bureau"
        else:
            weighted = [b for b in options if b in ("Trade Port", "Factory", "Barracks", "Vehicle Depot")]
            selected = random.choice(weighted or options)

        cost = gs.buildings_db[selected]["cost"]
        if faction.treasury >= cost and random.random() < 0.35:
            faction.treasury -= cost
            planet.buildings.append(selected)


def _move_armies(gs: GameState, faction_id: str) -> None:
    faction = gs.factions[faction_id]
    for army in [a for a in gs.armies.values() if a.faction_id == faction_id and a.movement > 0]:
        planet = gs.planets[army.planet]
        if not planet.connections:
            continue

        enemy_neighbors = [
            n for n in planet.connections if gs.planets[n].owner not in (faction_id, "neutral")
        ]
        neutral_neighbors = [n for n in planet.connections if gs.planets[n].owner == "neutral"]

        target = random.choice(enemy_neighbors or neutral_neighbors or list(planet.connections))
        army.planet = target
        army.movement -= 1

        if gs.planets[target].owner == "neutral":
            gs.planets[target].owner = faction_id
            gs.message = f"{faction.name} peacefully claims {target}."
        elif gs.planets[target].owner != faction_id:
            gs.message = f"{faction.name} attacks {target}!"


def _recruit_units(gs: GameState, faction_id: str, owned_planets) -> None:
    faction = gs.factions[faction_id]
    roster = gs.unit_db[faction_id]

    for planet in owned_planets:
        military_level = planet.military + sum(
            gs.buildings_db[b].get("military", 0) for b in planet.buildings
        )
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
        for army in stationed:
            if len(army.units) >= 10 or faction.treasury <= 120 or random.random() >= 0.4:
                continue

            template = random.choice(recruit_pool)
            if faction.treasury >= template["cost"]:
                faction.treasury -= template["cost"]
                army.units.append(UnitCard.from_template(template))


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
