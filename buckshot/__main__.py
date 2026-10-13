"""Command line: watch the bot play, benchmark it, or ask it for advice."""

from __future__ import annotations

import argparse
import random
import sys
import time

from .engine import POLICIES, ROUNDS, play_game, play_round
from .rules import DEALER, ITEMS, PLAYER, State, describe, item_counts, p_current_live
from .solver import rank_actions


def _items(text: str):
    names = [n.strip().lower() for n in text.split(",") if n.strip()]
    for n in names:
        if n not in ITEMS:
            raise argparse.ArgumentTypeError(f"unknown item {n!r}; choose from {', '.join(ITEMS)}")
    return item_counts(names)


def cmd_play(args):
    rng = random.Random(args.seed)
    rounds = play_game(POLICIES[args.policy], rng, log=print)
    print(f"\nResult: won {rounds}/{len(ROUNDS)} rounds" + (" - beat the game!" if rounds == len(ROUNDS) else ""))


def cmd_sim(args):
    rng = random.Random(args.seed)
    print(f"{args.games} games per policy (seed {args.seed})\n")
    print(f"{'policy':<8} {'round 1':>8} {'round 2':>8} {'round 3':>8} {'full run':>9} {'time':>7}")
    for name in args.policies:
        policy = POLICIES[name]
        start = time.perf_counter()
        wins = [sum(play_round(cfg, policy, rng) for _ in range(args.games)) for cfg in ROUNDS]
        runs = sum(play_game(policy, rng) == len(ROUNDS) for _ in range(args.games))
        cells = " ".join(f"{w / args.games:>8.1%}" for w in wins)
        print(f"{name:<8} {cells} {runs / args.games:>9.1%} {time.perf_counter() - start:>6.1f}s")


def cmd_advise(args):
    n = args.live + args.blank
    known = (args.known or "").upper().ljust(n, "?")
    if len(known) != n or set(known) - set("LB?"):
        sys.exit(f"--known must be up to {n} characters of L, B or ?")
    if known.count("L") > args.live or known.count("B") > args.blank:
        sys.exit("--known has more live or blank shells than are loaded")
    s = State(
        hp=(args.hp, args.dealer_hp), max_hp=args.max_hp or max(args.hp, args.dealer_hp),
        live=args.live, blank=args.blank, known=known, inverted=args.inverted, dk="",
        saw=args.saw, items=(args.items, args.dealer_items),
        cuffs=(0, 1 if args.dealer_cuffed else 0), turn=PLAYER,
    )
    print(f"Current shell is live with probability {p_current_live(s):.0%}\n")
    print("Win chance  Action")
    for v, action in rank_actions(s):
        print(f"{v:>9.1%}   {describe(action)}")


def cmd_calibrate(args):
    from .live.screen import calibrate
    calibrate()


def cmd_capture(args):
    from pathlib import Path
    from .live.screen import capture
    capture(Path(args.out))


def cmd_live(args):
    from .live.controller import run
    run(dry_run=args.dry_run, budget=args.budget)


def main(argv=None):
    p = argparse.ArgumentParser(prog="buckshot", description="A bot that plays Buckshot Roulette.")
    sub = p.add_subparsers(dest="cmd", required=True)

    play = sub.add_parser("play", help="watch the bot play one full run against the dealer")
    play.add_argument("--seed", type=int)
    play.add_argument("--policy", choices=POLICIES, default="solver")
    play.set_defaults(func=cmd_play)

    sim = sub.add_parser("sim", help="benchmark policies over many games")
    sim.add_argument("--games", type=int, default=100)
    sim.add_argument("--seed", type=int, default=0)
    sim.add_argument("--policies", nargs="+", choices=POLICIES, default=list(POLICIES))
    sim.set_defaults(func=cmd_sim)

    adv = sub.add_parser("advise", help="rank your options for a position from a real game")
    adv.add_argument("--hp", type=int, required=True, help="your HP")
    adv.add_argument("--dealer-hp", type=int, required=True)
    adv.add_argument("--max-hp", type=int, help="round's max HP (default: the higher HP)")
    adv.add_argument("--live", type=int, required=True, help="live shells left in the gun")
    adv.add_argument("--blank", type=int, required=True, help="blank shells left in the gun")
    adv.add_argument("--known", help="what you know of the shell order, e.g. 'L??B' (current shell first)")
    adv.add_argument("--items", type=_items, default=item_counts([]), help="your items, comma-separated")
    adv.add_argument("--dealer-items", type=_items, default=item_counts([]))
    adv.add_argument("--saw", action="store_true", help="you already used the hand saw this turn")
    adv.add_argument("--inverted", action="store_true", help="you already used the inverter on this shell")
    adv.add_argument("--dealer-cuffed", action="store_true", help="the dealer will skip their next turn")
    adv.set_defaults(func=cmd_advise)

    cal = sub.add_parser("calibrate", help="record where to click in the real game (Windows)")
    cal.set_defaults(func=cmd_calibrate)

    cap = sub.add_parser("capture", help="save screenshots of the real game with F9")
    cap.add_argument("--out", default="screenshots")
    cap.set_defaults(func=cmd_capture)

    live = sub.add_parser("live", help="play the real game: the bot clicks, you report what it can't see")
    live.add_argument("--dry-run", action="store_true", help="print clicks instead of making them")
    live.add_argument("--budget", type=int, default=5_000, help="search size per move")
    live.set_defaults(func=cmd_live)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
