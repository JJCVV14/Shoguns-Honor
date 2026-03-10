from __future__ import annotations

import json
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class UnitCard:
    name: str
    stats: dict
    hp: float
    soldiers: int

    @classmethod
    def from_template(cls, template: dict):
        return cls(template["name"], template, float(template["health"]), int(template["squad"]))


@dataclass
class General:
    name: str
    rank: int = 1
    aura: int = 120
    cooldowns: Dict[str, int] = field(default_factory=lambda: {"rally": 0, "orbital": 0})


@dataclass
class Army:
    id: int
    faction_id: str
    planet: str
    general: General
    units: List[UnitCard] = field(default_factory=list)
    movement: int = 1
    is_planet_garrison: bool = False
    can_move: bool = True

    def strength(self) -> float:
        return sum(u.hp + u.soldiers * (u.stats["damage"] + u.stats["armor"]) for u in self.units if u.hp > 0)


@dataclass
class Planet:
    name: str
    x: int
    y: int
    owner: str
    population: int
    stability: int
    base_income: int
    industry: int
    military: int
    trade: int
    slots: int
    connections: List[str]
    buildings: List[str] = field(default_factory=list)
    unrest: int = 0

    def income(self, tax_rate: float, econ_bonus: float = 0.0) -> int:
        building_income = 0
        order_bonus = 0
        for b in self.buildings:
            building_income += self._b_def(b).get("income", 0)
            order_bonus += self._b_def(b).get("order", 0)
        stability_mod = max(0.5, min(1.25, (self.stability + order_bonus - self.unrest) / 100))
        raw = (self.base_income + self.trade + self.industry * 1.2 + building_income) * tax_rate
        return int(raw * stability_mod * (1 + econ_bonus))

    @staticmethod
    def _b_def(name: str) -> dict:
        with Path("data/buildings.json").open("r", encoding="utf-8") as f:
            return json.load(f)[name]


@dataclass
class Faction:
    id: str
    name: str
    color: List[int]
    economy_mod: float
    research_mod: float
    personality: str
    capital: str
    treasury: int = 900
    tax_rate: float = 1.0
    diplomacy: Dict[str, str] = field(default_factory=dict)
    unlocked_techs: List[str] = field(default_factory=list)
    research_target: Optional[str] = None
    research_left: int = 0
    alive: bool = True


@dataclass
class GameState:
    turn: int
    current_faction: str
    player_faction: str
    factions: Dict[str, Faction]
    planets: Dict[str, Planet]
    armies: Dict[int, Army]
    unit_db: Dict[str, list]
    buildings_db: Dict[str, dict]
    tech_db: List[dict]
    leaders_db: Dict[str, list]
    selected_planet: Optional[str] = None
    selected_army: Optional[int] = None
    message: str = ""
    next_army_id: int = 100
    recruit_queue: List[dict] = field(default_factory=list)


def opposing_factions(player_faction: str) -> tuple[str, str]:
    if player_faction in ("empire", "rebels"):
        return "empire", "rebels"
    return "republic", "separatists"


def load_game_data() -> tuple:
    base = Path("data")
    factions = json.loads((base / "factions.json").read_text(encoding="utf-8"))
    planets = json.loads((base / "planets.json").read_text(encoding="utf-8"))
    units = json.loads((base / "units.json").read_text(encoding="utf-8"))
    for faction_units in units.values():
        for unit in faction_units:
            unit["morale"] = unit["morale"] * 1.5

    buildings = json.loads((base / "buildings.json").read_text(encoding="utf-8"))
    tech = json.loads((base / "tech_tree.json").read_text(encoding="utf-8"))
    leaders = json.loads((base / "leaders.json").read_text(encoding="utf-8"))
    return factions, planets, units, buildings, tech, leaders


def new_campaign(player_faction: str) -> GameState:
    f_data, p_data, unit_db, building_db, tech_db, leaders_db = load_game_data()
    allowed = opposing_factions(player_faction)

    factions = {f["id"]: Faction(**f) for f in f_data if f["id"] in (*allowed, "revolutionaries")}
    planets = {p["name"]: Planet(**p) for p in p_data}

    for planet in planets.values():
        if planet.owner not in allowed:
            planet.owner = "neutral"

    for fid, faction in factions.items():
        if fid == "revolutionaries":
            continue
        for other in factions:
            if fid != other and other != "revolutionaries":
                faction.diplomacy[other] = "war"

    armies: Dict[int, Army] = {}
    a_id = 1
    for fid, faction in factions.items():
        if fid == "revolutionaries":
            continue
        capital = planets[faction.capital]
        capital.buildings = ["Barracks", "Trade Port"]
        general = General(name=random.choice(leaders_db[fid]))
        starter = [UnitCard.from_template(unit_db[fid][0]), UnitCard.from_template(unit_db[fid][1])]
        armies[a_id] = Army(id=a_id, faction_id=fid, planet=capital.name, general=general, units=starter)
        a_id += 1

    return GameState(
        1,
        player_faction,
        player_faction,
        factions,
        planets,
        armies,
        unit_db,
        building_db,
        tech_db,
        leaders_db,
        next_army_id=a_id,
    )


def serialize(gs: GameState) -> dict:
    return {
        "turn": gs.turn,
        "current_faction": gs.current_faction,
        "player_faction": gs.player_faction,
        "next_army_id": gs.next_army_id,
        "factions": {k: asdict(v) for k, v in gs.factions.items()},
        "planets": {k: asdict(v) for k, v in gs.planets.items()},
        "armies": {
            str(k): {
                "id": a.id,
                "faction_id": a.faction_id,
                "planet": a.planet,
                "general": asdict(a.general),
                "units": [asdict(u) for u in a.units],
                "movement": a.movement,
                "is_planet_garrison": a.is_planet_garrison,
                "can_move": a.can_move,
            }
            for k, a in gs.armies.items()
        },
        "recruit_queue": gs.recruit_queue,
    }


def deserialize(payload: dict) -> GameState:
    _, _, unit_db, building_db, tech_db, leaders_db = load_game_data()
    factions = {k: Faction(**v) for k, v in payload["factions"].items()}
    planets = {k: Planet(**v) for k, v in payload["planets"].items()}

    armies = {}
    for k, a in payload["armies"].items():
        armies[int(k)] = Army(
            id=a["id"],
            faction_id=a["faction_id"],
            planet=a["planet"],
            general=General(**a["general"]),
            units=[UnitCard(**u) for u in a["units"]],
            movement=a["movement"],
            is_planet_garrison=a.get("is_planet_garrison", False),
            can_move=a.get("can_move", True),
        )

    return GameState(
        payload["turn"],
        payload["current_faction"],
        payload["player_faction"],
        factions,
        planets,
        armies,
        unit_db,
        building_db,
        tech_db,
        leaders_db,
        next_army_id=payload.get("next_army_id", 100),
        recruit_queue=payload.get("recruit_queue", []),
    )
