import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import streamlit as st

Side = str
Hex = Tuple[int, int]

EMPIRE: Side = "Empire"
REBELS: Side = "Rebels"

MAP_W = 12
MAP_H = 12
BATTLE_W = 6
BATTLE_H = 10
SETTLEMENT_COUNT = 8

UNIT_TEMPLATES = {
    EMPIRE: {"name": "Stormtrooper Squad", "hp": 3, "dmg": 1},
    REBELS: {"name": "Rebel Squad", "hp": 3, "dmg": 1},
}


def hex_distance(a: Hex, b: Hex) -> int:
    aq, ar = a
    bq, br = b
    ax, az = aq, ar
    ay = -ax - az
    bx, bz = bq, br
    by = -bx - bz
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


def neighbors(h: Hex) -> List[Hex]:
    q, r = h
    return [
        (q + 1, r),
        (q - 1, r),
        (q, r + 1),
        (q, r - 1),
        (q + 1, r - 1),
        (q - 1, r + 1),
    ]


def in_bounds(h: Hex, w: int, hh: int) -> bool:
    return 0 <= h[0] < w and 0 <= h[1] < hh


def key(h: Hex) -> str:
    return f"{h[0]},{h[1]}"


def parse_hex(k: str) -> Hex:
    q, r = k.split(",")
    return int(q), int(r)


def side_dot(side: Side) -> str:
    return "⚫" if side == EMPIRE else "🔴"


def side_label(side: Side) -> str:
    return f"{side_dot(side)} {side}"


def load_symbol(side: Side) -> Optional[Path]:
    # Tries common names if the user drops files into /assets.
    candidates = {
        REBELS: [
            "assets/rebel_symbol.svg",
            "assets/rebel.png",
            "assets/rebels.png",
            "assets/rebel_symbol.png",
        ],
        EMPIRE: [
            "assets/empire_symbol.svg",
            "assets/empire.png",
            "assets/empire_symbol.png",
            "assets/imperial.png",
        ],
    }
    for item in candidates[side]:
        p = Path(item)
        if p.exists():
            return p
    return None


@dataclass
class Unit:
    id: str
    side: Side
    name: str
    hp: int
    dmg: int
    pos: Hex
    moved: bool = False


# ---------- world setup ----------
def island_land() -> Set[Hex]:
    land: Set[Hex] = set()
    center = (5, 6)
    for q in range(MAP_W):
        for r in range(MAP_H):
            if hex_distance((q, r), center) <= 5:
                land.add((q, r))

    # cut a few edge tiles to make a rough island silhouette
    coast_cuts = {
        (0, 6),
        (11, 6),
        (1, 2),
        (2, 1),
        (9, 1),
        (10, 2),
        (1, 9),
        (2, 10),
        (9, 10),
        (10, 9),
    }
    return {h for h in land if h not in coast_cuts}


def pick_settlements(land: Set[Hex], count: int = SETTLEMENT_COUNT) -> List[Hex]:
    pool = list(land)
    random.shuffle(pool)
    settlements: List[Hex] = []

    # minimum of two hexes between settlements => hex distance >= 3
    for spot in pool:
        if all(hex_distance(spot, existing) >= 3 for existing in settlements):
            settlements.append(spot)
        if len(settlements) == count:
            return settlements

    raise RuntimeError("Could not place all settlements with spacing constraints.")


def unit_at(units: List[dict], pos: Hex) -> Optional[dict]:
    for u in units:
        if u["hp"] > 0 and tuple(u["pos"]) == pos:
            return u
    return None


def living_units(units: List[dict], side: Optional[Side] = None) -> List[dict]:
    return [u for u in units if u["hp"] > 0 and (side is None or u["side"] == side)]


def population_cap(game: dict, side: Side) -> int:
    owned = sum(1 for owner in game["ownership"].values() if owner == side)
    return 3 + owned


def population_used(game: dict, side: Side) -> int:
    return len(living_units(game["units"], side))


def can_recruit(game: dict, side: Side) -> bool:
    return population_used(game, side) < population_cap(game, side)


def recruit_unit(game: dict, side: Side) -> bool:
    if not can_recruit(game, side):
        return False

    settlements = [parse_hex(k) for k, owner in game["ownership"].items() if owner == side]
    random.shuffle(settlements)
    for s in settlements:
        if unit_at(game["units"], s) is None:
            idx = 1 + sum(1 for u in game["units"] if u["side"] == side)
            t = UNIT_TEMPLATES[side]
            game["units"].append(
                asdict(
                    Unit(
                        id=f"{side[:3]}-{idx}",
                        side=side,
                        name=t["name"],
                        hp=t["hp"],
                        dmg=t["dmg"],
                        pos=s,
                    )
                )
            )
            return True
    return False


def capture_if_applicable(game: dict, mover: dict) -> None:
    pos = tuple(mover["pos"])
    k = key(pos)
    if k not in game["ownership"]:
        return

    owner = game["ownership"][k]
    if owner is None:
        game["ownership"][k] = mover["side"]
        return

    if owner != mover["side"]:
        enemy_defender = any(
            tuple(u["pos"]) == pos and u["side"] == owner and u["hp"] > 0 for u in game["units"]
        )
        if not enemy_defender:
            game["ownership"][k] = mover["side"]


def touching_enemy(units: List[dict]) -> bool:
    alive = living_units(units)
    for u in alive:
        for n in neighbors(tuple(u["pos"])):
            other = unit_at(alive, n)
            if other and other["side"] != u["side"]:
                return True
    return False


def all_settlements_controlled_by_one_side(game: dict) -> Optional[Side]:
    owners = list(game["ownership"].values())
    if any(o is None for o in owners):
        return None
    unique = set(owners)
    return next(iter(unique)) if len(unique) == 1 else None


def setup_game(player_side: Side) -> None:
    land = island_land()
    settlements = pick_settlements(land)
    a, b = random.sample(settlements, 2)

    ownership: Dict[str, Optional[Side]] = {key(s): None for s in settlements}
    ownership[key(a)] = EMPIRE
    ownership[key(b)] = REBELS

    empire_t = UNIT_TEMPLATES[EMPIRE]
    rebels_t = UNIT_TEMPLATES[REBELS]

    units = [
        asdict(Unit("Emp-1", EMPIRE, empire_t["name"], empire_t["hp"], empire_t["dmg"], a)),
        asdict(Unit("Reb-1", REBELS, rebels_t["name"], rebels_t["hp"], rebels_t["dmg"], b)),
    ]

    st.session_state.game = {
        "phase": "map",
        "player_side": player_side,
        "active_side": EMPIRE,
        "turn": 1,
        "winner": None,
        "land": [list(h) for h in sorted(land)],
        "ownership": ownership,
        "units": units,
        "selected_unit": None,
        "battle": None,
    }


# ---------- battle ----------
def start_battle(game: dict) -> None:
    battle_units: List[dict] = []
    occupied: Set[Hex] = set()

    for wu in living_units(game["units"]):
        while True:
            p = (random.randint(0, BATTLE_W - 1), random.randint(0, BATTLE_H - 1))
            if p not in occupied:
                occupied.add(p)
                break
        battle_units.append(
            {
                "id": wu["id"],
                "side": wu["side"],
                "name": wu["name"],
                "hp": wu["hp"],
                "dmg": wu["dmg"],
                "pos": [p[0], p[1]],
                "moved": False,
                "acted": False,
            }
        )

    game["phase"] = "battle"
    game["battle"] = {
        "turn": 1,
        "active_side": game["active_side"],
        "selected_unit": None,
        "units": battle_units,
    }


def finish_battle(game: dict) -> None:
    b_units = {u["id"]: u for u in game["battle"]["units"]}
    survivors = []
    for u in game["units"]:
        bu = b_units.get(u["id"])
        if bu and bu["hp"] > 0:
            u["hp"] = bu["hp"]
            survivors.append(u)
    game["units"] = survivors
    game["battle"] = None
    game["phase"] = "map"


def end_map_turn(game: dict) -> None:
    current = game["active_side"]
    for u in game["units"]:
        if u["side"] == current:
            u["moved"] = False
    game["active_side"] = REBELS if current == EMPIRE else EMPIRE
    game["turn"] += 1

    winner = all_settlements_controlled_by_one_side(game)
    if winner:
        game["winner"] = winner
        game["phase"] = "game_over"


def end_battle_turn(game: dict) -> None:
    battle = game["battle"]
    current = battle["active_side"]
    for u in battle["units"]:
        if u["side"] == current and u["hp"] > 0:
            u["moved"] = False
            u["acted"] = False
    battle["active_side"] = REBELS if current == EMPIRE else EMPIRE
    battle["turn"] += 1
    battle["selected_unit"] = None


def ai_map_turn(game: dict) -> None:
    side = game["active_side"]
    land = {tuple(h) for h in game["land"]}
    for u in living_units(game["units"], side):
        options = [
            n
            for n in neighbors(tuple(u["pos"]))
            if n in land and unit_at(game["units"], n) is None
        ]
        if options and not u["moved"]:
            u["pos"] = list(random.choice(options))
            u["moved"] = True
            capture_if_applicable(game, u)

    if touching_enemy(game["units"]):
        start_battle(game)
        return

    recruit_unit(game, side)
    end_map_turn(game)


def ai_battle_turn(game: dict) -> None:
    battle = game["battle"]
    side = battle["active_side"]
    my_units = [u for u in battle["units"] if u["side"] == side and u["hp"] > 0]

    for u in my_units:
        pos = tuple(u["pos"])
        adjacent_enemies = [
            e
            for e in battle["units"]
            if e["hp"] > 0 and e["side"] != side and tuple(e["pos"]) in neighbors(pos)
        ]
        if adjacent_enemies and not u["acted"]:
            target = random.choice(adjacent_enemies)
            target["hp"] -= u["dmg"]
            u["acted"] = True
            continue

        if not u["moved"]:
            options = [
                n
                for n in neighbors(pos)
                if in_bounds(n, BATTLE_W, BATTLE_H) and unit_at(battle["units"], n) is None
            ]
            if options:
                u["pos"] = list(random.choice(options))
            u["moved"] = True

            pos = tuple(u["pos"])
            adjacent_enemies = [
                e
                for e in battle["units"]
                if e["hp"] > 0 and e["side"] != side and tuple(e["pos"]) in neighbors(pos)
            ]
            if adjacent_enemies and not u["acted"]:
                target = random.choice(adjacent_enemies)
                target["hp"] -= u["dmg"]
                u["acted"] = True

    alive_sides = {u["side"] for u in battle["units"] if u["hp"] > 0}
    if len(alive_sides) <= 1:
        finish_battle(game)
        return

    end_battle_turn(game)


# ---------- rendering ----------
def tile_button(label: str, enabled: bool, button_key: str) -> bool:
    if enabled:
        return st.button(label, key=button_key, use_container_width=True)
    st.markdown(
        f"<div style='padding:0.38rem 0.5rem;background:#f5f5f5;border-radius:0.35rem;text-align:center'>{label}</div>",
        unsafe_allow_html=True,
    )
    return False


def render_world(game: dict) -> None:
    st.subheader("World Map")
    st.caption("Move one hex per turn. Capture neutral or undefended enemy settlements.")

    st.write(
        f"Turn **{game['turn']}** | Active: **{side_label(game['active_side'])}** | You: **{side_label(game['player_side'])}**"
    )

    c1, c2 = st.columns(2)
    with c1:
        st.write(
            f"Empire Population: {population_used(game, EMPIRE)} / {population_cap(game, EMPIRE)}"
        )
    with c2:
        st.write(
            f"Rebel Population: {population_used(game, REBELS)} / {population_cap(game, REBELS)}"
        )

    land = {tuple(h) for h in game["land"]}
    settlement_hexes = {parse_hex(hk) for hk in game["ownership"].keys()}

    selected_id = game["selected_unit"]
    selected = next((u for u in game["units"] if u["id"] == selected_id and u["hp"] > 0), None)

    for r in range(MAP_H):
        cols = st.columns(MAP_W + 1)
        offset = 1 if r % 2 == 1 else 0
        if offset:
            cols[0].markdown("&nbsp;", unsafe_allow_html=True)

        for q in range(MAP_W):
            h = (q, r)
            with cols[q + offset]:
                if h not in land:
                    st.markdown("🌊")
                    continue

                occupant = unit_at(game["units"], h)
                owner = game["ownership"].get(key(h))

                if occupant:
                    label = f"{side_dot(occupant['side'])}{occupant['hp']}"
                elif h in settlement_hexes:
                    label = "🏘️"
                    if owner == EMPIRE:
                        label = "🏘️⚫"
                    elif owner == REBELS:
                        label = "🏘️🔴"
                else:
                    label = "⬡"

                my_turn = game["active_side"] == game["player_side"]
                clickable = False
                if my_turn:
                    if occupant and occupant["side"] == game["active_side"]:
                        clickable = True
                    elif (
                        selected
                        and not selected["moved"]
                        and h in neighbors(tuple(selected["pos"]))
                        and unit_at(game["units"], h) is None
                    ):
                        clickable = True

                if tile_button(label, clickable, f"map-{q}-{r}-{game['turn']}"):
                    if occupant and occupant["side"] == game["active_side"]:
                        game["selected_unit"] = occupant["id"]
                    elif selected:
                        selected["pos"] = [q, r]
                        selected["moved"] = True
                        game["selected_unit"] = None
                        capture_if_applicable(game, selected)
                        if touching_enemy(game["units"]):
                            start_battle(game)
                            st.rerun()

    left, right = st.columns([1, 2])
    with left:
        if game["active_side"] == game["player_side"] and st.button(
            "End Turn", use_container_width=True
        ):
            recruit_unit(game, game["active_side"])
            end_map_turn(game)
            game["selected_unit"] = None
            st.rerun()
    with right:
        st.info("Select your unit, then click an adjacent empty hex.")


def render_battle(game: dict) -> None:
    battle = game["battle"]
    st.subheader("Battlefield (6 x 10 Hexes)")
    st.caption("Each unit may move once and attack once per turn; attacks require adjacency.")
    st.write(f"Battle Turn **{battle['turn']}** | Active: **{side_label(battle['active_side'])}**")

    selected_id = battle["selected_unit"]
    selected = next((u for u in battle["units"] if u["id"] == selected_id and u["hp"] > 0), None)

    for r in range(BATTLE_H):
        cols = st.columns(BATTLE_W + 1)
        offset = 1 if r % 2 == 1 else 0
        if offset:
            cols[0].markdown("&nbsp;", unsafe_allow_html=True)

        for q in range(BATTLE_W):
            h = (q, r)
            with cols[q + offset]:
                u = unit_at(battle["units"], h)
                label = "⬡" if not u else f"{side_dot(u['side'])}{u['hp']}"

                my_turn = battle["active_side"] == game["player_side"]
                clickable = False
                if my_turn:
                    if u and u["side"] == battle["active_side"]:
                        clickable = True
                    elif selected:
                        empty_move = (
                            not selected["moved"]
                            and h in neighbors(tuple(selected["pos"]))
                            and in_bounds(h, BATTLE_W, BATTLE_H)
                            and unit_at(battle["units"], h) is None
                        )
                        attack = (
                            u
                            and u["side"] != selected["side"]
                            and not selected["acted"]
                            and h in neighbors(tuple(selected["pos"]))
                        )
                        clickable = bool(empty_move or attack)

                if tile_button(label, clickable, f"bat-{q}-{r}-{battle['turn']}"):
                    if u and u["side"] == battle["active_side"]:
                        battle["selected_unit"] = u["id"]
                    elif selected:
                        target = unit_at(battle["units"], h)
                        if (
                            target
                            and target["side"] != selected["side"]
                            and not selected["acted"]
                            and h in neighbors(tuple(selected["pos"]))
                        ):
                            target["hp"] -= selected["dmg"]
                            selected["acted"] = True
                        elif (
                            not selected["moved"]
                            and h in neighbors(tuple(selected["pos"]))
                            and in_bounds(h, BATTLE_W, BATTLE_H)
                            and unit_at(battle["units"], h) is None
                        ):
                            selected["pos"] = [q, r]
                            selected["moved"] = True

    alive_sides = {u["side"] for u in battle["units"] if u["hp"] > 0}
    if len(alive_sides) <= 1:
        finish_battle(game)
        st.success("Battle resolved. Returning to map.")
        st.rerun()

    if battle["active_side"] == game["player_side"] and st.button(
        "End Battle Turn", use_container_width=True
    ):
        end_battle_turn(game)
        st.rerun()


def render_side_picker() -> None:
    st.subheader("Choose Your Side")

    rebel_symbol = load_symbol(REBELS)
    empire_symbol = load_symbol(EMPIRE)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### 🔴 Rebels")
        if rebel_symbol:
            st.image(str(rebel_symbol), width=140)
        st.write("Unit: Rebel Squad — 3 HP, 1 DMG")
        if st.button("Play Rebels", use_container_width=True):
            setup_game(REBELS)
            st.rerun()
    with c2:
        st.markdown("### ⚫ Empire")
        if empire_symbol:
            st.image(str(empire_symbol), width=140)
        st.write("Unit: Stormtrooper Squad — 3 HP, 1 DMG")
        if st.button("Play Empire", use_container_width=True):
            setup_game(EMPIRE)
            st.rerun()

    if not rebel_symbol or not empire_symbol:
        st.info(
            "Faction symbol files can be replaced at assets/rebel_symbol.svg and "
            "assets/empire_symbol.svg (or use rebel.png/empire.png)."
        )


def main() -> None:
    st.set_page_config(page_title="Empire vs Rebels", layout="wide")
    st.title("Empire vs Rebels - Hex Strategy")

    if "game" not in st.session_state:
        st.session_state.game = {"phase": "choose_side"}

    game = st.session_state.game

    if game["phase"] == "choose_side":
        render_side_picker()
        return

    if game["phase"] == "game_over":
        st.success(f"Game Over! {side_label(game['winner'])} controls all settlements.")
        if st.button("Start New Game"):
            st.session_state.clear()
            st.rerun()
        return

    if game["phase"] == "map" and game["active_side"] != game["player_side"]:
        st.info("AI is taking map turn...")
        ai_map_turn(game)
        st.rerun()

    if game["phase"] == "battle" and game["battle"]["active_side"] != game["player_side"]:
        st.info("AI is taking battle turn...")
        ai_battle_turn(game)
        st.rerun()

    if game["phase"] == "map":
        render_world(game)
    elif game["phase"] == "battle":
        render_battle(game)


if __name__ == "__main__":
    main()
