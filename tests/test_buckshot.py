import random
import unittest

from buckshot import engine
from buckshot.rules import (
    CUFFED, DEALER, FREE, JUST_FREED, PLAYER, dealer_policy, item_counts, new_load,
    p_current_live, player_actions, transitions,
)
from buckshot.solver import best_action, rank_actions, value


def load(hp=(2, 2), live=1, blank=1, mine=(), theirs=(), **kw):
    s = new_load(hp, max(hp), live, blank, (item_counts(mine), item_counts(theirs)))
    return s._replace(**kw)


class TransitionTests(unittest.TestCase):
    def test_outcome_probabilities_sum_to_one(self):
        s = load(hp=(4, 4), live=2, blank=3, mine=["glass", "beer", "phone", "medicine", "inverter", "adrenaline"],
                 theirs=["saw", "cuffs"], known="?L???")
        for action in player_actions(s):
            total = sum(q for q, _, _ in transitions(s, action))
            self.assertAlmostEqual(total, 1.0, msg=action)

    def test_blank_on_self_keeps_turn(self):
        s = load(live=0, blank=2)
        [(_, _, ns)] = transitions(s, ("shoot", PLAYER))
        self.assertEqual(ns.turn, PLAYER)
        self.assertEqual((ns.live, ns.blank), (0, 1))

    def test_sawed_live_does_double_damage(self):
        s = load(hp=(4, 4), live=1, blank=0, saw=True)
        [(_, _, ns)] = transitions(s, ("shoot", DEALER))
        self.assertEqual(ns.hp, (4, 2))
        self.assertFalse(ns.saw)

    def test_inverter_flips_the_fired_shell(self):
        s = load(live=0, blank=2, inverted=True)
        [(_, label, ns)] = transitions(s, ("shoot", DEALER))
        self.assertEqual(label, ("shell", "B"))  # labels carry the loaded type
        self.assertEqual(ns.hp, (2, 1))           # but it fired live

    def test_handcuffs_skip_one_dealer_turn(self):
        s = load(live=2, blank=2, mine=["cuffs"])
        [(_, _, s)] = transitions(s, ("item", "cuffs"))
        self.assertEqual(s.cuffs[DEALER], CUFFED)
        self.assertNotIn(("item", "cuffs"), player_actions(s._replace(items=(item_counts(["cuffs"]), s.items[1]))))
        s = [ns for _, label, ns in transitions(s, ("shoot", DEALER)) if label == ("shell", "B")][0]
        self.assertEqual((s.turn, s.cuffs[DEALER]), (PLAYER, JUST_FREED))
        s = [ns for _, label, ns in transitions(s, ("shoot", DEALER)) if label == ("shell", "B")][0]
        self.assertEqual((s.turn, s.cuffs[DEALER]), (DEALER, FREE))

    def test_phone_reveals_a_future_shell(self):
        s = load(live=1, blank=2, mine=["phone"])
        outcomes = transitions(s, ("item", "phone"))
        self.assertEqual(len(outcomes), 4)  # 2 positions x live/blank
        for _, (_, pos, t), ns in outcomes:
            self.assertEqual(ns.known[pos], t)

    def test_known_shells_update_probability(self):
        s = load(live=1, blank=2, known="?B?")
        self.assertAlmostEqual(p_current_live(s), 0.5)

    def test_adrenaline_steals_and_uses(self):
        s = load(hp=(1, 2), live=1, blank=1, mine=["adrenaline"], theirs=["cigs"])
        [(_, _, ns)] = transitions(s, ("adrenaline", "cigs"))
        self.assertEqual(ns.hp, (2, 2))
        self.assertEqual(sum(ns.items[PLAYER]) + sum(ns.items[DEALER]), 0)


class DealerTests(unittest.TestCase):
    def test_dealer_shoots_player_on_known_live(self):
        s = load(live=1, blank=0, turn=DEALER)
        self.assertEqual(dealer_policy(s), [(1.0, ("shoot", PLAYER))])

    def test_dealer_flips_a_coin_on_even_odds(self):
        s = load(live=1, blank=1, turn=DEALER)
        self.assertEqual(sorted(a for _, a in dealer_policy(s)), [("shoot", PLAYER), ("shoot", DEALER)])


class SolverTests(unittest.TestCase):
    def test_certain_blank_shoots_self(self):
        self.assertEqual(best_action(load(live=1, blank=1, known="B?")), ("shoot", PLAYER))

    def test_certain_live_shoots_dealer(self):
        self.assertEqual(best_action(load(live=1, blank=1, known="L?")), ("shoot", DEALER))

    def test_lethal_with_saw(self):
        s = load(hp=(4, 2), live=1, blank=0, mine=["saw"])
        self.assertEqual(rank_actions(s)[0][0], 1.0)

    def test_glass_beats_a_coin_flip(self):
        s = load(hp=(1, 1), live=1, blank=1, mine=["glass"])
        self.assertEqual(best_action(s), ("item", "glass"))
        self.assertEqual(value(s, 2), 1.0)


class EngineTests(unittest.TestCase):
    def test_games_finish(self):
        rng = random.Random(7)
        for policy in engine.POLICIES.values():
            for _ in range(5):
                self.assertIn(engine.play_game(policy, rng), range(4))

    def test_solver_beats_naive(self):
        rng = random.Random(3)
        cfg = engine.ROUNDS[1]
        solver_wins = sum(engine.play_round(cfg, engine.solver_policy, rng) for _ in range(150))
        naive_wins = sum(engine.play_round(cfg, engine.naive_policy, rng) for _ in range(150))
        self.assertGreater(solver_wins, naive_wins)


if __name__ == "__main__":
    unittest.main()
