"""Mouse, keyboard and screenshots on the player's PC.

Uses pynput (mouse clicks and the calibration hotkey) and mss (screenshots).
Both are imported only when used, so the rest of the bot runs without them.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..rules import MAX_ITEMS

CONFIG_PATH = Path("buckshot_live.json")

# Points to calibrate, with what to hover over for each.
POINTS = {
    "shotgun": "the shotgun on the table, when you can pick it up",
    "aim_dealer": "where you click to shoot the DEALER after picking up the gun",
    "aim_self": "where you click to shoot YOURSELF after picking up the gun",
    "item_box": "the item box you open at the start of a load",
    **{f"you_{i}": f"YOUR item slot {i}" for i in range(1, MAX_ITEMS + 1)},
    **{f"dealer_{i}": f"the DEALER's item slot {i}" for i in range(1, MAX_ITEMS + 1)},
}


@dataclass
class Config:
    points: dict = field(default_factory=dict)
    # Seconds to wait after each kind of click for the game's animations.
    after_pickup: float = 1.2
    after_shot: float = 3.5
    after_item: float = 2.5
    after_box: float = 2.0
    after_place: float = 1.2

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Config":
        if not path.exists():
            raise SystemExit(f"No {path} found. Run `python -m buckshot calibrate` first.")
        data = json.loads(path.read_text())
        missing = [p for p in POINTS if p not in data.get("points", {})]
        if missing:
            raise SystemExit(f"{path} is missing points: {', '.join(missing)}. Run calibrate again.")
        return cls(**data)

    def save(self, path: Path = CONFIG_PATH):
        path.write_text(json.dumps(asdict(self), indent=2))


class Mouse:
    """Clicks in the game. With dry_run, prints the clicks instead."""

    def __init__(self, config: Config, dry_run: bool = False, say=print):
        self.config = config
        self.dry_run = dry_run
        self.say = say
        if not dry_run:
            from pynput.mouse import Button, Controller
            self._mouse, self._left = Controller(), Button.left

    def click(self, point: str, wait: float):
        x, y = self.config.points[point]
        if self.dry_run:
            self.say(f"   [click {point} at ({x}, {y}), wait {wait:.1f}s]")
            return
        self._mouse.position = (x, y)
        time.sleep(0.15)  # let the game register the hover before the click
        self._mouse.click(self._left)
        time.sleep(wait)


def wait_for_key(keys=("f8", "esc")):
    """Blocks until one of `keys` is pressed anywhere; returns its name."""
    from pynput import keyboard

    pressed = {}

    def on_press(key):
        name = getattr(key, "name", None) or getattr(key, "char", None)
        if name in keys:
            pressed["key"] = name
            return False

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()
    return pressed["key"]


def calibrate(path: Path = CONFIG_PATH):
    from pynput.mouse import Controller

    mouse = Controller()
    config = Config.load(path) if path.exists() else Config()
    print("Calibration. Start a game and get to a point where you can see the table.")
    print("For each point, hover the mouse over it in the game and press F8.")
    print("Press Esc to keep the saved value for that point.\n")
    for name, what in POINTS.items():
        saved = config.points.get(name)
        print(f"{name}: hover over {what}" + (f" (saved: {tuple(saved)})" if saved else ""))
        if wait_for_key() == "f8":
            config.points[name] = list(mouse.position)
            print(f"  -> {tuple(config.points[name])}")
        elif not saved:
            print("  This point has no saved value yet; it's needed. Hover and press F8.")
            wait_for_key(("f8",))
            config.points[name] = list(mouse.position)
            print(f"  -> {tuple(config.points[name])}")
    config.save(path)
    print(f"\nSaved to {path}.")


def capture(out: Path):
    """Saves a full-screen screenshot each time F9 is pressed, until Esc."""
    import mss
    import mss.tools

    out.mkdir(parents=True, exist_ok=True)
    print(f"Press F9 in the game to save a screenshot to {out}/, Esc to stop.")
    n = len(list(out.glob("shot_*.png")))
    with mss.mss() as sct:
        while wait_for_key(("f9", "esc")) == "f9":
            n += 1
            path = out / f"shot_{n:03d}.png"
            img = sct.grab(sct.monitors[1])
            mss.tools.to_png(img.rgb, img.size, output=str(path))
            print(f"  saved {path}")
