"""Plays full games of Buckshot Roulette against the dealer model."""

from __future__ import annotations

import random
from dataclasses import dataclass

from .rules import (
    DEALER, ITEMS, MAX_ITEMS, MEDICINE_HEAL_CHANCE, PLAYER,
    State, dealer_policy, describe, item_names, new_load, p_current_live, transitions,
)
from .solver import best_action


@dataclass(frozen=True)
class RoundConfig:
    hp: int
    items_per_load: int


# The three rounds of a standard run.
ROUNDS = (RoundConfig(hp=2, items_per_load=0), RoundConfig(hp=4, items_per_load=2), RoundConfig(hp=6, items_per_load=4))


def solver_policy(s: State):
    return best_action(s)


def naive_policy(s: State):
    """Baseline: no items, shoot the dealer when live is at least as likely."""
    return ("shoot", DEALER) if p_current_live(s) >= 0.5 else ("shoot", PLAYER)


POLICIES = {"solver": solver_policy, "naive": naive_policy}


def _draw_items(rng: random.Random, counts, k: int):
    counts = list(counts)
    for _ in range(k):
        if sum(counts) >= MAX_ITEMS:
            break
        counts[rng.randrange(len(ITEMS))] += 1
    return tuple(counts)


def _load_shells(rng: random.Random):
    total = rng.randint(2, 8)
    live = rng.randint(max(1, total // 3), min(total - 1, total - total // 3))
    shells = ["L"] * live + ["B"] * (total - live)
    rng.shuffle(shells)
    return shells


def _matches(label, shells, phone_pos, med) -> bool:
    if label is None:
        return True
    if label[0] == "shell":
        return shells[0] == label[1]
    if label[0] == "phone":
        return label[1] == phone_pos and shells[label[1]] == label[2]
    return label[1] == med


def _narrate(s: State, action, label, actor: int) -> str:
    who = "You" if actor == PLAYER else "Dealer"
    line = f"{who}: {describe(action, actor)}"
    if label and label[0] == "shell":
        fired = label[1] if not s.inverted else ("B" if label[1] == "L" else "L")
        if action[0] == "shoot":
            line += f" -> {'LIVE' if fired == 'L' else 'blank'}" + (" (sawed-off)" if s.saw and fired == "L" else "")
        elif action[1] == "beer":
            line += f" -> ejected a {'live' if fired == 'L' else 'blank'}"
        elif actor == PLAYER:
            line += f" -> it's {'live' if fired == 'L' else 'blank'}"
    elif label and label[0] == "phone":
        line += f" -> shell #{label[1] + 1} is {'live' if label[2] == 'L' else 'blank'}"
    elif label and label[0] == "med":
        line += " -> +2 HP" if label[1] else " -> -1 HP"
    return line


def play_round(cfg: RoundConfig, policy, rng: random.Random, log=None) -> bool:
    """Plays one round; returns True if the player wins."""
    hp = (cfg.hp, cfg.hp)
    items = (tuple([0] * len(ITEMS)), tuple([0] * len(ITEMS)))
    while True:
        shells = _load_shells(rng)
        items = (_draw_items(rng, items[0], cfg.items_per_load), _draw_items(rng, items[1], cfg.items_per_load))
        s = new_load(hp, cfg.hp, shells.count("L"), shells.count("B"), items)
        if log:
            log(f"-- Load: {s.live} live, {s.blank} blank | HP you {hp[0]} / dealer {hp[1]}")
            if cfg.items_per_load:
                log(f"   Your items: {', '.join(item_names(items[0])) or 'none'}")
                log(f"   Dealer items: {', '.join(item_names(items[1])) or 'none'}")
        while s.shells and min(s.hp) > 0:
            actor = s.turn
            if actor == PLAYER:
                action = policy(s)
            else:
                options = dealer_policy(s)
                action = rng.choices([a for _, a in options], weights=[q for q, _ in options])[0]
            phone_pos = rng.randint(1, s.shells - 1) if s.shells > 1 else None
            med = rng.random() < MEDICINE_HEAL_CHANCE
            outcomes = [(label, ns) for _, label, ns in transitions(s, action) if _matches(label, shells, phone_pos, med)]
            assert len(outcomes) == 1, (s, action, outcomes)
            label, ns = outcomes[0]
            if log:
                log("   " + _narrate(s, action, label, actor))
            del shells[: s.shells - ns.shells]
            s = ns
        hp, items = s.hp, s.items
        if hp[PLAYER] <= 0:
            if log:
                log("You died.")
            return False
        if hp[DEALER] <= 0:
            if log:
                log("The dealer is dead. Round won.")
            return True


def play_game(policy, rng: random.Random, log=None) -> int:
    """Plays a full run; returns how many rounds the player won before dying (3 = beat the game)."""
    for i, cfg in enumerate(ROUNDS):
        if log:
            log(f"=== Round {i + 1}: {cfg.hp} HP, {cfg.items_per_load} items per load ===")
        if not play_round(cfg, policy, rng, log):
            return i
    return len(ROUNDS)
