"""Reading the game: what happened, and what's on the table.

Until screen reading is calibrated from real screenshots, every observation
comes from the person at the keyboard through `ConsoleObserver`. The prompts
are short and skipped whenever the answer is already certain.
"""

from __future__ import annotations

import re

from ..rules import DEALER, ITEMS, PLAYER

ALIASES = {
    "med": "medicine", "meds": "medicine", "pills": "medicine",
    "magnifier": "glass", "mag": "glass", "cig": "cigs", "cigarettes": "cigs",
    "handsaw": "saw", "cuff": "cuffs", "handcuffs": "cuffs", "inv": "inverter",
    "adr": "adrenaline", "beers": "beer",
}

DEALER_TURN_HELP = """\
Type what the dealer did, in order, separated by spaces:
  you:l  you:b     shot you, live / blank
  self:l self:b    shot itself, live / blank
  beer:l beer:b    racked out a live / blank
  med+   med-      expired medicine healed / hurt
  cigs saw cuffs glass phone inverter
  adr:<item>       adrenaline, stealing your <item> (add @3 for your slot 3,
                   and :l/:b or +/- for beer or medicine, e.g. adr:beer:l)
Example: glass saw you:l"""

_TOKEN = re.compile(r"^(adr:)?([a-z]+)(?::([lb]))?([+-])?(?:@([1-8]))?$")


def item_name(text: str) -> str:
    name = ALIASES.get(text.strip().lower(), text.strip().lower())
    if name not in ITEMS:
        raise ValueError(f"unknown item {text!r}")
    return name


def parse_dealer_turn(text: str):
    """Parses the dealer's moves into (action, observations) pairs."""
    moves = []
    for token in text.lower().split():
        m = _TOKEN.match(token)
        if not m:
            raise ValueError(f"can't read {token!r}")
        adr, word, shell, sign, slot = m.groups()
        obs = {}
        if shell:
            obs["fired"] = shell.upper()
        if sign:
            obs["healed"] = sign == "+"
        if word in ("you", "self"):
            if adr or not shell:
                raise ValueError(f"{token!r}: a shot needs :l or :b")
            moves.append((("shoot", PLAYER if word == "you" else DEALER), obs))
            continue
        name = item_name(word)
        if name == "beer" and not shell:
            raise ValueError(f"{token!r}: beer needs :l or :b")
        if name == "medicine" and not sign:
            raise ValueError(f"{token!r}: medicine needs + or -")
        if adr:
            if slot:
                obs["slot"] = int(slot) - 1
            moves.append((("adrenaline", name), obs))
        else:
            moves.append((("item", name), obs))
    if not moves:
        raise ValueError("nothing entered")
    return moves


class ConsoleObserver:
    """Asks the person at the keyboard for anything the bot can't see."""

    def __init__(self, ask=input, say=print):
        self.ask = ask
        self.say = say

    def _choice(self, prompt: str, options: dict, default=None):
        hint = "/".join(options) + (f" [{default}]" if default else "")
        while True:
            answer = self.ask(f"{prompt} ({hint}): ").strip().lower() or (default or "")
            if answer in options:
                return options[answer]
            self.say(f"  Please type one of: {', '.join(options)}")

    def _int(self, prompt: str, lo: int, hi: int, default=None) -> int:
        while True:
            answer = self.ask(f"{prompt}" + (f" [{default}]" if default is not None else "") + ": ").strip()
            if not answer and default is not None:
                return default
            if answer.isdigit() and lo <= int(answer) <= hi:
                return int(answer)
            self.say(f"  Please type a number from {lo} to {hi}")

    def round_hp(self, default: int) -> int:
        return self._int("New round. Max HP (charges)", 1, 10, default)

    def load(self):
        live = self._int("New load. Live (red) shells", 1, 8)
        blank = self._int("Blank shells", 1, 8)
        first = self._choice("Who shoots first?", {"y": PLAYER, "d": DEALER}, "y")
        return live, blank, first

    def items_this_load(self, default: int) -> int:
        return self._int("How many items does each side get this load?", 0, 8, default)

    def picked_item(self, n: int, total: int) -> str:
        while True:
            try:
                return item_name(self.ask(f"Item {n}/{total} in your hand: "))
            except ValueError as e:
                self.say(f"  {e}. Items: {', '.join(ITEMS)}")

    def dealer_items(self, current: list) -> list:
        shown = ", ".join(current) or "none"
        while True:
            answer = self.ask(f"Dealer's items now (comma-separated) [{shown}]: ").strip()
            if not answer:
                return list(current)
            try:
                return [item_name(n) for n in answer.split(",") if n.strip()]
            except ValueError as e:
                self.say(f"  {e}")

    def fired(self, what: str) -> str:
        return self._choice(f"{what}: live or blank?", {"l": "L", "b": "B"})

    def phone(self, shells: int):
        pos = self._int("Burner phone: which shell number? (0 if 'how unfortunate')", 0, shells)
        if pos == 0:
            return None
        return pos - 1, self._choice(f"Shell #{pos} is", {"l": "L", "b": "B"})

    def healed(self) -> bool:
        return self._choice("Did the medicine heal you?", {"y": True, "n": False})

    def dealer_slot(self, name: str) -> int:
        return self._int(f"Which dealer slot (1-8) holds the {name}?", 1, 8) - 1

    def dealer_turn(self):
        while True:
            text = self.ask("Dealer's turn (? for help): ")
            if text.strip() == "?":
                self.say(DEALER_TURN_HELP)
                continue
            try:
                return parse_dealer_turn(text)
            except ValueError as e:
                self.say(f"  {e}. Type ? for help.")
