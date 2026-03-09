import json
from pathlib import Path
from game.state import GameState, serialize, deserialize


def save_campaign(gs: GameState, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(serialize(gs), indent=2), encoding="utf-8")


def load_campaign(path: str) -> GameState | None:
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return deserialize(data)
