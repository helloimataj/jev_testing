"""Buckshot Roulette rules as pure state transitions.

The state is the *player's* information state: shell counts are public, but the
order of the shells is only known where the player has seen it (magnifying
glass, burner phone). Every random event is an explicit outcome with a
probability, so the same transition function drives both the solver (which
averages over all outcomes) and the game engine (which picks the outcome that
matches the real shotgun).
"""

from __future__ import annotations

from typing import NamedTuple

PLAYER, DEALER = 0, 1

ITEMS = (
    "glass",       # magnifying glass: see the current shell
    "cigs",        # cigarette pack: +1 HP
    "beer",        # rack the shotgun, ejecting the current shell
    "saw",         # hand saw: next shot deals 2 damage
    "cuffs",       # handcuffs: opponent skips their next turn
    "phone",       # burner phone: reveals one random future shell
    "inverter",    # flips the current shell live <-> blank
    "adrenaline",  # steal an opponent's item and use it immediately
    "medicine",    # expired medicine: 40% +2 HP, 60% -1 HP
)
IDX = {name: i for i, name in enumerate(ITEMS)}
MAX_ITEMS = 8
MEDICINE_HEAL_CHANCE = 0.4

# Handcuff states, per side.
FREE, CUFFED, JUST_FREED = 0, 1, 2


class State(NamedTuple):
    hp: tuple[int, int]          # (player, dealer)
    max_hp: int
    live: int                    # remaining live shells (original polarity)
    blank: int                   # remaining blank shells (original polarity)
    known: str                   # player's knowledge per remaining shell: '?', 'L' or 'B'
    inverted: bool               # the current shell's polarity has been flipped
    dk: str                      # dealer's private read of the current shell this turn: '', 'L', 'B'
    saw: bool                    # the current shooter's next shot deals double damage
    items: tuple[tuple[int, ...], tuple[int, ...]]
    cuffs: tuple[int, int]
    turn: int

    @property
    def shells(self) -> int:
        return self.live + self.blank


def new_load(hp, max_hp, live, blank, items, turn=PLAYER) -> State:
    return State(
        hp=tuple(hp), max_hp=max_hp, live=live, blank=blank,
        known="?" * (live + blank), inverted=False, dk="", saw=False,
        items=(tuple(items[0]), tuple(items[1])), cuffs=(FREE, FREE), turn=turn,
    )


def item_counts(names) -> tuple[int, ...]:
    counts = [0] * len(ITEMS)
    for name in names:
        counts[IDX[name]] += 1
    return tuple(counts)


def item_names(counts) -> list[str]:
    return [name for name, n in zip(ITEMS, counts) for _ in range(n)]


def flip(t: str) -> str:
    return "B" if t == "L" else "L"


def _set(pair, side, value):
    return (value, pair[1]) if side == 0 else (pair[0], value)


def p_live(s: State, pos: int) -> float:
    """Probability, from the player's view, that shell `pos` was loaded live."""
    k = s.known[pos]
    if k != "?":
        return 1.0 if k == "L" else 0.0
    unknown = s.known.count("?")
    return (s.live - s.known.count("L")) / unknown


def p_current_live(s: State) -> float:
    """Probability the current shell fires live, including any inversion."""
    p = p_live(s, 0)
    return 1.0 - p if s.inverted else p


def _resolve_current(s: State):
    """Possible original types of the current shell, as (prob, type)."""
    if s.dk:
        return [(1.0, flip(s.dk) if s.inverted else s.dk)]
    p = p_live(s, 0)
    return [(q, t) for q, t in ((p, "L"), (1.0 - p, "B")) if q > 0]


def _consume(s: State, orig: str) -> State:
    return s._replace(
        live=s.live - (orig == "L"), blank=s.blank - (orig == "B"),
        known=s.known[1:], inverted=False, dk="",
    )


def _pass_turn(s: State) -> State:
    s = s._replace(saw=False, dk="")
    other = 1 - s.turn
    if s.cuffs[other] == CUFFED:
        return s._replace(cuffs=_set(s.cuffs, other, JUST_FREED))
    return s._replace(cuffs=_set(s.cuffs, other, FREE), turn=other)


def _heal(s: State, side: int, amount: int) -> State:
    hp = min(s.max_hp, s.hp[side] + amount) if amount > 0 else s.hp[side] + amount
    return s._replace(hp=_set(s.hp, side, hp))


def _remove_item(s: State, side: int, name: str) -> State:
    counts = list(s.items[side])
    counts[IDX[name]] -= 1
    return s._replace(items=_set(s.items, side, tuple(counts)))


def _shoot(s: State, target: int):
    out = []
    for q, orig in _resolve_current(s):
        fired = flip(orig) if s.inverted else orig
        ns = _consume(s, orig)
        if fired == "L":
            ns = _heal(ns, target, -(2 if s.saw else 1))
        ns = ns._replace(saw=False)
        if not (fired == "B" and target == s.turn):
            ns = _pass_turn(ns)
        out.append((q, ("shell", orig), ns))
    return out


def _effect(s: State, name: str, actor: int):
    """Apply an item's effect for `actor`; the item is already removed."""
    if name == "glass":
        out = []
        for q, orig in _resolve_current(s):
            if actor == PLAYER:
                ns = s._replace(known=orig + s.known[1:])
            else:
                ns = s._replace(dk=flip(orig) if s.inverted else orig)
            out.append((q, ("shell", orig), ns))
        return out
    if name == "cigs":
        return [(1.0, None, _heal(s, actor, 1))]
    if name == "beer":
        return [(q, ("shell", orig), _consume(s, orig)) for q, orig in _resolve_current(s)]
    if name == "saw":
        return [(1.0, None, s._replace(saw=True))]
    if name == "cuffs":
        return [(1.0, None, s._replace(cuffs=_set(s.cuffs, 1 - actor, CUFFED)))]
    if name == "phone":
        n = s.shells
        if n <= 1 or actor == DEALER:  # the dealer model ignores what its phone says
            return [(1.0, None, s)]
        out = []
        for pos in range(1, n):
            p = p_live(s, pos)
            for q, orig in ((p, "L"), (1.0 - p, "B")):
                if q > 0:
                    known = s.known[:pos] + orig + s.known[pos + 1:]
                    out.append((q / (n - 1), ("phone", pos, orig), s._replace(known=known)))
        return out
    if name == "inverter":
        return [(1.0, None, s._replace(inverted=not s.inverted, dk=flip(s.dk) if s.dk else ""))]
    if name == "medicine":
        return [
            (MEDICINE_HEAL_CHANCE, ("med", True), _heal(s, actor, 2)),
            (1 - MEDICINE_HEAL_CHANCE, ("med", False), _heal(s, actor, -1)),
        ]
    raise ValueError(f"unknown item {name!r}")


def transitions(s: State, action):
    """All outcomes of `action` taken by the side whose turn it is.

    Actions: ("shoot", target), ("item", name), ("adrenaline", stolen_name).
    Returns a list of (probability, outcome_label, next_state).
    """
    kind, arg = action
    actor = s.turn
    if kind == "shoot":
        return _shoot(s, arg)
    if kind == "item":
        return _effect(_remove_item(s, actor, arg), arg, actor)
    if kind == "adrenaline":
        ns = _remove_item(_remove_item(s, actor, "adrenaline"), 1 - actor, arg)
        return _effect(ns, arg, actor)
    raise ValueError(f"unknown action {action!r}")


def _useful(s: State, name: str, actor: int) -> bool:
    """Prunes item uses that can never help, to keep the search small."""
    if name == "glass":
        return 0.0 < p_live(s, 0) < 1.0
    if name in ("cigs", "medicine"):
        return s.hp[actor] < s.max_hp
    if name == "saw":
        return not s.saw
    if name == "cuffs":
        return s.cuffs[1 - actor] == FREE
    if name == "phone":
        return s.shells > 1 and "?" in s.known[1:] and 0.0 < p_live(s, s.known.index("?", 1)) < 1.0
    return name in ("beer", "inverter")


def player_actions(s: State):
    actions = [("shoot", DEALER), ("shoot", PLAYER)]
    mine, theirs = s.items
    for name, n in zip(ITEMS, mine):
        if n and name != "adrenaline" and _useful(s, name, PLAYER):
            actions.append(("item", name))
    if mine[IDX["adrenaline"]]:
        for name, n in zip(ITEMS, theirs):
            if n and name != "adrenaline" and _useful(s, name, PLAYER):
                actions.append(("adrenaline", name))
    return actions


def dealer_view(s: State) -> str:
    """What the dealer believes the current shell will fire as: 'L', 'B' or ''."""
    if s.dk:
        return s.dk
    if s.live == 0 or s.blank == 0:
        orig = "B" if s.live == 0 else "L"
        return flip(orig) if s.inverted else orig
    return ""


def dealer_policy(s: State):
    """A heuristic model of the game's dealer, as a list of (prob, action).

    Mirrors the dealer's known habits: heal when hurt, check the shell when it
    can, saw and cuff on a known live, shoot itself on a known blank, and
    otherwise play the odds (coin flip when they are even).
    """
    have = dict(zip(ITEMS, s.items[DEALER]))
    hp = s.hp[DEALER]
    if have["cigs"] and hp < s.max_hp:
        return [(1.0, ("item", "cigs"))]
    if have["medicine"] and 1 < hp <= s.max_hp - 2:
        return [(1.0, ("item", "medicine"))]
    view = dealer_view(s)
    if view == "L":
        if have["saw"] and not s.saw:
            return [(1.0, ("item", "saw"))]
        if have["cuffs"] and s.cuffs[PLAYER] == FREE:
            return [(1.0, ("item", "cuffs"))]
        return [(1.0, ("shoot", PLAYER))]
    if view == "B":
        if have["inverter"]:
            return [(1.0, ("item", "inverter"))]
        return [(1.0, ("shoot", DEALER))]
    if have["glass"]:
        return [(1.0, ("item", "glass"))]
    if have["adrenaline"] and s.items[PLAYER][IDX["glass"]]:
        return [(1.0, ("adrenaline", "glass"))]
    p = s.live / s.shells
    if s.inverted:
        p = 1.0 - p
    if p == 0.5 and have["beer"]:
        return [(1.0, ("item", "beer"))]
    if p > 0.5:
        return [(1.0, ("shoot", PLAYER))]
    if p < 0.5:
        return [(1.0, ("shoot", DEALER))]
    return [(0.5, ("shoot", PLAYER)), (0.5, ("shoot", DEALER))]


def describe(action, actor: int = PLAYER) -> str:
    kind, arg = action
    if kind == "shoot":
        if arg == actor:
            return "shoot yourself" if actor == PLAYER else "shoot itself"
        return "shoot the dealer" if arg == DEALER else "shoot you"
    if kind == "item":
        return f"use {arg}"
    return f"adrenaline -> steal and use {arg}"
