"""Expectimax solver: the player's chance of winning the round from a state.

Player turns take the best action, dealer turns average over the dealer model,
and hidden shells average over every order consistent with what the player
knows. The search looks `depth` shells ahead (a shell is spent when it is fired
or ejected); past that, or once the shotgun is empty and the next load's shells
and items are unknown, a heuristic estimates the round.

Big item hands make the tree grow fast, so `rank_actions` deepens one shell at
a time and stops when the last search grew past a state budget.
"""

from __future__ import annotations

import math
from functools import lru_cache

from .rules import DEALER, PLAYER, State, dealer_policy, player_actions, transitions

# Item value, in HP, for the heuristic estimate.
ITEM_WEIGHT = 0.35
HP_SCALE = 1.1
DEFAULT_BUDGET = 5_000


def estimate(s: State) -> float:
    """Heuristic win chance from HP and item counts alone."""
    edge = (s.hp[PLAYER] - s.hp[DEALER]) + ITEM_WEIGHT * (sum(s.items[PLAYER]) - sum(s.items[DEALER]))
    # Being low on HP makes every shell count for more.
    edge /= min(s.hp) ** 0.5
    return 1.0 / (1.0 + math.exp(-HP_SCALE * edge))


@lru_cache(maxsize=1_000_000)
def value(s: State, depth: int) -> float:
    if s.hp[PLAYER] <= 0:
        return 0.0
    if s.hp[DEALER] <= 0:
        return 1.0
    if s.shells == 0 or depth == 0:
        return estimate(s)
    if s.turn == PLAYER:
        return max(action_value(s, a, depth) for a in player_actions(s))
    return sum(q * action_value(s, a, depth) for q, a in dealer_policy(s))


def action_value(s: State, action, depth: int) -> float:
    return sum(q * value(ns, depth - (ns.shells < s.shells)) for q, _, ns in transitions(s, action))


def rank_actions(s: State, budget: int = DEFAULT_BUDGET):
    """Player actions with their win chances, best first.

    Searches one shell deeper at a time until it sees the whole load or a
    search visits more than `budget` new states.
    """
    if value.cache_info().currsize > 800_000:
        value.cache_clear()
    for depth in range(1, s.shells + 1):
        before = value.cache_info().misses
        scored = [(action_value(s, a, depth), a) for a in player_actions(s)]
        if value.cache_info().misses - before > budget:
            break
    # Prefer shooting over item use on ties so items are kept for later.
    scored.sort(key=lambda va: (-round(va[0], 12), va[1][0] != "shoot"))
    return scored


def best_action(s: State, budget: int = DEFAULT_BUDGET):
    return rank_actions(s, budget)[0][1]
