import math
import random
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional, Tuple

import streamlit as st

Side = str
Pos = Tuple[int, int]

EMPIRE: Side = "Empire"
REBELS: Side = "Rebels"
SIDES = (EMPIRE, REBELS)

MAP_W = 20
MAP_H = 14


UNIT_DEFS: Dict[Side, Dict[str, dict]] = {
    EMPIRE: {
        "Conscripts": {"hp": 40, "dmg": 8, "range": 1, "speed": 1, "cost": 90, "time": 2, "icon": "⚫"},
        "Bike Squad": {"hp": 55, "dmg": 10, "range": 1, "speed": 2, "cost": 140, "time": 3, "icon": "🏍️"},
        "Siege Walker": {"hp": 120, "dmg": 20, "range": 3, "speed": 1, "cost": 280, "time": 5, "icon": "🕷️"},
    },
    REBELS: {
        "Militia": {"hp": 35, "dmg": 9, "range": 1, "speed": 1, "cost": 80, "time": 2, "icon": "🔴"},
        "Skimmer": {"hp": 50, "dmg": 11, "range": 1, "speed": 2, "cost": 135, "time": 3, "icon": "🛵"},
        "Rocket Truck": {"hp": 95, "dmg": 22, "range": 3, "speed": 1, "cost": 260, "time": 5, "icon": "🚚"},
    },
}

STRUCTURE_DEFS = {
    "Command": {"hp": 420, "cost": 0, "income": 8, "icon": "🏰", "queue": ["core"]},
    "Barracks": {"hp": 220, "cost": 180, "income": 0, "icon": "🏢", "queue": ["infantry", "fast"]},
    "War Factory": {"hp": 260, "cost": 260, "income": 0, "icon": "🏭", "queue": ["heavy"]},
    "Outpost": {"hp": 170, "cost": 120, "income": 2, "icon": "🛰️", "queue": []},
}

RESOURCE_ICON = "💠"


@dataclass
class Unit:
    id: str
    side: Side
    kind: str
    hp: int
    pos: Pos
    order: str = "idle"  # idle, move, attack
    target: Optional[Pos] = None


@dataclass
class Structure:
    id: str
    side: Side
    kind: str
    hp: int
    pos: Pos
    queue: List[dict]


def in_bounds(p: Pos) -> bool:
    return 0 <= p[0] < MAP_W and 0 <= p[1] < MAP_H


def chebyshev(a: Pos, b: Pos) -> int:
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def neighbors8(p: Pos) -> List[Pos]:
    x, y = p
    out = []
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            np = (x + dx, y + dy)
            if in_bounds(np):
                out.append(np)
    return out


def side_color(side: Side) -> str:
    return "⚫" if side == EMPIRE else "🔴"


def side_name(side: Side) -> str:
    return f"{side_color(side)} {side}"


def unit_stats(side: Side, kind: str) -> dict:
    return UNIT_DEFS[side][kind]


def get_unit(game: dict, uid: str) -> Optional[dict]:
    return next((u for u in game["units"] if u["id"] == uid and u["hp"] > 0), None)


def unit_at(game: dict, p: Pos) -> Optional[dict]:
    return next((u for u in game["units"] if u["hp"] > 0 and tuple(u["pos"]) == p), None)


def structure_at(game: dict, p: Pos) -> Optional[dict]:
    return next((s for s in game["structures"] if s["hp"] > 0 and tuple(s["pos"]) == p), None)


def occupied(game: dict, p: Pos) -> bool:
    return unit_at(game, p) is not None or structure_at(game, p) is not None


def closest_enemy(game: dict, side: Side, pos: Pos) -> Optional[Pos]:
    targets = []
    for u in game["units"]:
        if u["hp"] > 0 and u["side"] != side:
            targets.append(tuple(u["pos"]))
    for s in game["structures"]:
        if s["hp"] > 0 and s["side"] != side:
            targets.append(tuple(s["pos"]))
    if not targets:
        return None
    return min(targets, key=lambda t: chebyshev(pos, t))


def move_step_towards(src: Pos, dst: Pos) -> Pos:
    sx, sy = src
    dx = 0 if dst[0] == sx else (1 if dst[0] > sx else -1)
    dy = 0 if dst[1] == sy else (1 if dst[1] > sy else -1)
    return sx + dx, sy + dy


def make_initial_game(player_side: Side) -> dict:
    empire_base = (2, MAP_H // 2)
    rebel_base = (MAP_W - 3, MAP_H // 2)

    nodes = [(MAP_W // 2, 2), (MAP_W // 2, MAP_H - 3), (MAP_W // 2, MAP_H // 2)]

    structures = [
        asdict(Structure("emp-cmd", EMPIRE, "Command", STRUCTURE_DEFS["Command"]["hp"], empire_base, [])),
        asdict(Structure("reb-cmd", REBELS, "Command", STRUCTURE_DEFS["Command"]["hp"], rebel_base, [])),
        asdict(Structure("emp-barr", EMPIRE, "Barracks", STRUCTURE_DEFS["Barracks"]["hp"], (4, MAP_H // 2 - 2), [])),
        asdict(Structure("reb-barr", REBELS, "Barracks", STRUCTURE_DEFS["Barracks"]["hp"], (MAP_W - 5, MAP_H // 2 + 2), [])),
    ]

    units = [
        asdict(Unit("emp-1", EMPIRE, "Conscripts", unit_stats(EMPIRE, "Conscripts")["hp"], (3, MAP_H // 2))),
        asdict(Unit("emp-2", EMPIRE, "Bike Squad", unit_stats(EMPIRE, "Bike Squad")["hp"], (4, MAP_H // 2))),
        asdict(Unit("reb-1", REBELS, "Militia", unit_stats(REBELS, "Militia")["hp"], (MAP_W - 4, MAP_H // 2))),
        asdict(Unit("reb-2", REBELS, "Skimmer", unit_stats(REBELS, "Skimmer")["hp"], (MAP_W - 5, MAP_H // 2))),
    ]

    return {
        "phase": "playing",
        "tick": 1,
        "player_side": player_side,
        "resources": {EMPIRE: 350, REBELS: 350},
        "selected": None,
        "nodes": [list(n) for n in nodes],
        "node_owner": {f"{x},{y}": None for (x, y) in nodes},
        "units": units,
        "structures": structures,
        "winner": None,
    }


def structure_income(game: dict, side: Side) -> int:
    total = 0
    for s in game["structures"]:
        if s["hp"] > 0 and s["side"] == side:
            total += STRUCTURE_DEFS[s["kind"]]["income"]
    return total


def update_node_control(game: dict) -> None:
    for node in [tuple(n) for n in game["nodes"]]:
        owner = None
        for u in game["units"]:
            if u["hp"] > 0 and tuple(u["pos"]) == node:
                owner = u["side"]
                break
        if owner is None:
            for s in game["structures"]:
                if s["hp"] > 0 and tuple(s["pos"]) == node:
                    owner = s["side"]
                    break
        game["node_owner"][f"{node[0]},{node[1]}"] = owner


def apply_income(game: dict) -> None:
    for side in SIDES:
        node_income = sum(12 for owner in game["node_owner"].values() if owner == side)
        game["resources"][side] += structure_income(game, side) + node_income


def produce_units(game: dict) -> None:
    for s in game["structures"]:
        if s["hp"] <= 0 or not s["queue"]:
            continue
        s["queue"][0]["remaining"] -= 1
        if s["queue"][0]["remaining"] > 0:
            continue

        order = s["queue"].pop(0)
        kind = order["kind"]
        spawn = None
        for n in neighbors8(tuple(s["pos"])) + [tuple(s["pos"])]:
            if not occupied(game, n):
                spawn = n
                break
        if not spawn:
            continue

        idx = 1 + sum(1 for u in game["units"] if u["side"] == s["side"])
        hp = unit_stats(s["side"], kind)["hp"]
        game["units"].append(asdict(Unit(f"{s['side'][:3]}-{idx}", s["side"], kind, hp, spawn)))


def unit_attack_phase(game: dict) -> None:
    for u in [u for u in game["units"] if u["hp"] > 0]:
        stats = unit_stats(u["side"], u["kind"])
        pos = tuple(u["pos"])
        enemies: List[Tuple[int, dict]] = []

        for eu in game["units"]:
            if eu["hp"] > 0 and eu["side"] != u["side"]:
                d = chebyshev(pos, tuple(eu["pos"]))
                if d <= stats["range"]:
                    enemies.append((d, eu))

        for es in game["structures"]:
            if es["hp"] > 0 and es["side"] != u["side"]:
                d = chebyshev(pos, tuple(es["pos"]))
                if d <= stats["range"]:
                    enemies.append((d, es))

        if enemies:
            enemies.sort(key=lambda x: x[0])
            enemies[0][1]["hp"] -= stats["dmg"]


def unit_move_phase(game: dict) -> None:
    for u in [u for u in game["units"] if u["hp"] > 0]:
        stats = unit_stats(u["side"], u["kind"])
        current = tuple(u["pos"])

        target = tuple(u["target"]) if u.get("target") else None
        if u["order"] in ("attack", "move") and target:
            for _ in range(stats["speed"]):
                if current == target:
                    break
                nxt = move_step_towards(current, target)
                if occupied(game, nxt):
                    break
                u["pos"] = [nxt[0], nxt[1]]
                current = nxt

        if u["order"] == "attack":
            if not target:
                enemy = closest_enemy(game, u["side"], tuple(u["pos"]))
                if enemy:
                    u["target"] = [enemy[0], enemy[1]]
            elif chebyshev(tuple(u["pos"]), target) <= 1:
                enemy = closest_enemy(game, u["side"], tuple(u["pos"]))
                if enemy:
                    u["target"] = [enemy[0], enemy[1]]


def cleanup(game: dict) -> None:
    game["units"] = [u for u in game["units"] if u["hp"] > 0]
    game["structures"] = [s for s in game["structures"] if s["hp"] > 0]


def queue_unit(game: dict, structure_id: str, kind: str) -> bool:
    s = next((x for x in game["structures"] if x["id"] == structure_id and x["hp"] > 0), None)
    if not s:
        return False
    cost = unit_stats(s["side"], kind)["cost"]
    if game["resources"][s["side"]] < cost:
        return False
    game["resources"][s["side"]] -= cost
    s["queue"].append({"kind": kind, "remaining": unit_stats(s["side"], kind)["time"]})
    return True


def ai_build(game: dict, side: Side) -> None:
    my_structs = [s for s in game["structures"] if s["hp"] > 0 and s["side"] == side]
    if not my_structs:
        return

    has_factory = any(s["kind"] == "War Factory" for s in my_structs)
    cmd = next((s for s in my_structs if s["kind"] == "Command"), None)

    if not has_factory and cmd and game["resources"][side] >= STRUCTURE_DEFS["War Factory"]["cost"]:
        for n in neighbors8(tuple(cmd["pos"])):
            if not occupied(game, n):
                game["resources"][side] -= STRUCTURE_DEFS["War Factory"]["cost"]
                idx = 1 + sum(1 for s in game["structures"] if s["side"] == side)
                game["structures"].append(
                    asdict(Structure(f"{side[:3]}-wf-{idx}", side, "War Factory", STRUCTURE_DEFS["War Factory"]["hp"], n, []))
                )
                break

    for s in my_structs:
        if s["kind"] == "Barracks" and len(s["queue"]) < 2:
            queue_unit(game, s["id"], random.choice(["Conscripts", "Bike Squad"]) if side == EMPIRE else random.choice(["Militia", "Skimmer"]))
        if s["kind"] == "War Factory" and len(s["queue"]) < 1:
            queue_unit(game, s["id"], "Siege Walker" if side == EMPIRE else "Rocket Truck")


def ai_orders(game: dict, side: Side) -> None:
    enemy_cmd = next((s for s in game["structures"] if s["side"] != side and s["kind"] == "Command"), None)
    if not enemy_cmd:
        return
    target = tuple(enemy_cmd["pos"])
    for u in game["units"]:
        if u["hp"] > 0 and u["side"] == side and u["order"] == "idle":
            u["order"] = "attack"
            u["target"] = [target[0], target[1]]


def check_winner(game: dict) -> Optional[Side]:
    for side in SIDES:
        enemy = REBELS if side == EMPIRE else EMPIRE
        enemy_cmd_alive = any(s for s in game["structures"] if s["side"] == enemy and s["kind"] == "Command")
        if not enemy_cmd_alive:
            return side
    return None


def simulate_tick(game: dict) -> None:
    update_node_control(game)
    apply_income(game)
    produce_units(game)
    ai_build(game, REBELS if game["player_side"] == EMPIRE else EMPIRE)
    ai_orders(game, REBELS if game["player_side"] == EMPIRE else EMPIRE)
    unit_move_phase(game)
    unit_attack_phase(game)
    cleanup(game)
    update_node_control(game)
    game["tick"] += 1
    game["winner"] = check_winner(game)
    if game["winner"]:
        game["phase"] = "game_over"


def tile_label(game: dict, p: Pos) -> str:
    u = unit_at(game, p)
    if u:
        hp = max(1, math.ceil(u["hp"] / 10))
        return f"{UNIT_DEFS[u['side']][u['kind']]['icon']}{hp}"
    s = structure_at(game, p)
    if s:
        return f"{STRUCTURE_DEFS[s['kind']]['icon']}{side_color(s['side'])}"
    if f"{p[0]},{p[1]}" in game["node_owner"]:
        owner = game["node_owner"][f"{p[0]},{p[1]}"]
        return RESOURCE_ICON if owner is None else f"{RESOURCE_ICON}{side_color(owner)}"
    return "·"


def draw_map(game: dict) -> None:
    st.subheader("Battlefield")
    st.caption("Select your unit/structure, then issue orders. Advance simulation with Step 1 Tick.")

    for y in range(MAP_H):
        cols = st.columns(MAP_W)
        for x in range(MAP_W):
            with cols[x]:
                if st.button(tile_label(game, (x, y)), key=f"tile-{x}-{y}-{game['tick']}", use_container_width=True):
                    game["selected"] = [x, y]


def render_selection_panel(game: dict) -> None:
    st.subheader("Command Panel")
    sel = tuple(game["selected"]) if game.get("selected") else None
    if not sel:
        st.info("Nothing selected.")
        return

    u = unit_at(game, sel)
    s = structure_at(game, sel)

    if u:
        st.write(f"**Unit:** {u['kind']} ({side_name(u['side'])}) HP: {u['hp']}")
        if u["side"] == game["player_side"]:
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Move Order", use_container_width=True):
                    u["order"] = "move"
            with c2:
                if st.button("Attack-Move", use_container_width=True):
                    u["order"] = "attack"
            tx = st.number_input("Target X", 0, MAP_W - 1, int(u["pos"][0]), key="ux")
            ty = st.number_input("Target Y", 0, MAP_H - 1, int(u["pos"][1]), key="uy")
            if st.button("Set Target", use_container_width=True):
                u["target"] = [int(tx), int(ty)]
        return

    if s:
        st.write(f"**Structure:** {s['kind']} ({side_name(s['side'])}) HP: {s['hp']}")
        if s["side"] != game["player_side"]:
            return

        if s["kind"] in ("Barracks", "Command", "War Factory"):
            choices = list(UNIT_DEFS[s["side"]].keys())
            if s["kind"] == "Barracks":
                allowed = [choices[0], choices[1]]
            elif s["kind"] == "War Factory":
                allowed = [choices[2]]
            else:
                allowed = [choices[0]]

            for kind in allowed:
                cost = unit_stats(s["side"], kind)["cost"]
                if st.button(f"Train {kind} (${cost})", key=f"build-{s['id']}-{kind}", use_container_width=True):
                    if not queue_unit(game, s["id"], kind):
                        st.warning("Not enough credits.")

        if s["kind"] == "Command" and game["resources"][s["side"]] >= STRUCTURE_DEFS["Outpost"]["cost"]:
            if st.button("Deploy Outpost (adjacent)", use_container_width=True):
                for n in neighbors8(tuple(s["pos"])):
                    if not occupied(game, n):
                        game["resources"][s["side"]] -= STRUCTURE_DEFS["Outpost"]["cost"]
                        idx = 1 + sum(1 for x in game["structures"] if x["side"] == s["side"])
                        game["structures"].append(
                            asdict(Structure(f"{s['side'][:3]}-op-{idx}", s["side"], "Outpost", STRUCTURE_DEFS["Outpost"]["hp"], n, []))
                        )
                        break
        return

    if f"{sel[0]},{sel[1]}" in game["node_owner"]:
        owner = game["node_owner"][f"{sel[0]},{sel[1]}"]
        st.write(f"Resource Node owner: {owner or 'Neutral'}")


def render_header(game: dict) -> None:
    st.title("Shogun's Honor: Rebel Uprising RTS")
    st.write(
        f"Tick **{game['tick']}** | You: **{side_name(game['player_side'])}** | "
        f"Empire Credits: **{game['resources'][EMPIRE]}** | Rebels Credits: **{game['resources'][REBELS]}**"
    )


def render_side_picker() -> None:
    st.title("Shogun's Honor RTS")
    st.subheader("Pick your faction")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### ⚫ Empire")
        st.write("Disciplined armor and superior siege platforms.")
        if st.button("Command the Empire", use_container_width=True):
            st.session_state.game = make_initial_game(EMPIRE)
            st.rerun()
    with c2:
        st.markdown("### 🔴 Rebels")
        st.write("Fast raids, cheap militia, and high-pressure rockets.")
        if st.button("Lead the Rebels", use_container_width=True):
            st.session_state.game = make_initial_game(REBELS)
            st.rerun()


def main() -> None:
    st.set_page_config(layout="wide", page_title="Shogun's Honor RTS")
    if "game" not in st.session_state:
        st.session_state.game = {"phase": "choose_side"}

    game = st.session_state.game
    if game["phase"] == "choose_side":
        render_side_picker()
        return

    if game["phase"] == "game_over":
        st.success(f"Victory: {side_name(game['winner'])}")
        if st.button("Start New Campaign"):
            st.session_state.clear()
            st.rerun()
        return

    render_header(game)
    left, right = st.columns([3, 1])
    with left:
        draw_map(game)
    with right:
        render_selection_panel(game)
        st.markdown("---")
        if st.button("Step 1 Tick", use_container_width=True):
            simulate_tick(game)
            st.rerun()
        if st.button("Step 5 Ticks", use_container_width=True):
            for _ in range(5):
                if game["phase"] != "playing":
                    break
                simulate_tick(game)
            st.rerun()


if __name__ == "__main__":
    main()
