"""Keeps the solver's state in step with a real game.

The real game doesn't expose its state, so the tracker replays what was seen:
each move is applied through the same `transitions` the solver uses, keeping
only the outcome that matches what happened. A move that has no matching
outcome means the observation contradicts the tracked state, and is rejected
before anything changes.

It also remembers which table slot holds which item, since using an item in
the real game means clicking its slot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..rules import DEALER, ITEMS, MAX_ITEMS, PLAYER, State, flip, item_counts, new_load, transitions


class Mismatch(ValueError):
    """An observation that can't happen from the tracked state."""


def _fired(s: State, orig: str) -> str:
    return flip(orig) if s.inverted else orig


@dataclass
class Tracker:
    max_hp: int = 2
    state: State | None = None
    # slots[side][i] is the item in slot i (0-based), or None.
    slots: list = field(default_factory=lambda: [[None] * MAX_ITEMS, [None] * MAX_ITEMS])
    hp: tuple = (2, 2)

    def new_round(self, max_hp: int):
        self.max_hp = max_hp
        self.hp = (max_hp, max_hp)
        self.slots = [[None] * MAX_ITEMS, [None] * MAX_ITEMS]
        self.state = None

    def new_load(self, live: int, blank: int, first: int = PLAYER):
        if self.state is not None:
            self.hp = self.state.hp
        items = tuple(item_counts(n for n in side if n) for side in self.slots)
        self.state = new_load(self.hp, self.max_hp, live, blank, items, turn=first)

    def free_slot(self, side: int) -> int:
        try:
            return self.slots[side].index(None)
        except ValueError:
            raise Mismatch("no free item slot") from None

    def place_item(self, side: int, name: str, slot: int | None = None) -> int:
        """Records an item put on the table; returns the slot it went in."""
        if name not in ITEMS:
            raise Mismatch(f"unknown item {name!r}")
        slot = self.free_slot(side) if slot is None else slot
        if self.slots[side][slot] is not None:
            raise Mismatch(f"slot {slot + 1} is already holding {self.slots[side][slot]}")
        self.slots[side][slot] = name
        if self.state is not None:
            counts = list(self.state.items[side])
            counts[ITEMS.index(name)] += 1
            items = (tuple(counts), self.state.items[1]) if side == PLAYER else (self.state.items[0], tuple(counts))
            self.state = self.state._replace(items=items)
        return slot

    def set_items(self, side: int, names):
        """Replaces one side's items. Slots are assigned in order, so use this
        only for the dealer, whose slots the bot never needs to know."""
        self.slots[side] = [None] * MAX_ITEMS
        if self.state is not None:
            items = list(self.state.items)
            items[side] = item_counts([])
            self.state = self.state._replace(items=tuple(items))
        for name in names:
            self.place_item(side, name)

    def slot_of(self, side: int, name: str, slot: int | None = None) -> int:
        if slot is not None:
            if self.slots[side][slot] != name:
                raise Mismatch(f"slot {slot + 1} holds {self.slots[side][slot]}, not {name}")
            return slot
        try:
            return self.slots[side].index(name)
        except ValueError:
            raise Mismatch(f"{'you have' if side == PLAYER else 'the dealer has'} no {name}") from None

    def apply(self, action, *, fired: str | None = None, phone: tuple | None = None,
              healed: bool | None = None, slot: int | None = None) -> State:
        """Applies a move by whoever's turn it is, given what was observed.

        fired:  'L' or 'B', how the current shell came out (shots, beer, glass).
        phone:  (position, 'L'/'B') read from a burner phone, 0-based.
        healed: whether expired medicine healed.
        slot:   which slot the item came from, when it matters.
        Observations that aren't needed are ignored; the dealer's own glass
        reading is never needed, because the dealer always fires that shell
        before the player moves again.
        """
        s = self.state
        actor = s.turn
        kind, name = action
        dealer_glass = actor == DEALER and name == "glass" and kind != "shoot"

        def matches(label):
            if label is None or dealer_glass:
                return True
            if label[0] == "shell":
                if fired is None:
                    raise Mismatch("need to know whether the shell was live or blank")
                return _fired(s, label[1]) == fired
            if label[0] == "phone":
                if phone is None:
                    raise Mismatch("need what the burner phone said")
                return (label[1], label[2]) == phone
            if healed is None:
                raise Mismatch("need whether the medicine healed")
            return label[1] == healed

        outcomes = [ns for _, label, ns in transitions(s, action) if matches(label)]
        if not outcomes:
            raise Mismatch(f"that can't happen here: {action} with {fired or phone or healed}")
        ns = outcomes[0]
        if dealer_glass:
            ns = ns._replace(dk="")  # the dealer's private reading isn't known
        if kind == "item":
            self.slots[actor][self.slot_of(actor, name, slot)] = None
        elif kind == "adrenaline":
            self.slots[actor][self.slot_of(actor, "adrenaline")] = None
            self.slots[1 - actor][self.slot_of(1 - actor, name, slot)] = None
        self.state = ns
        return ns

    def needs_fired(self) -> bool:
        """Whether the current shell's outcome is uncertain to the player."""
        s = self.state
        unknown = s.known[0] == "?"
        live_left = s.live - s.known.count("L")
        return unknown and 0 < live_left < s.known.count("?")

    def certain_fired(self) -> str:
        s = self.state
        if s.known[0] != "?":
            return _fired(s, s.known[0])
        return _fired(s, "L" if s.live - s.known.count("L") > 0 else "B")
