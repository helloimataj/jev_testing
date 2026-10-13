import unittest

from buckshot.live.controller import Controller
from buckshot.live.observe import ConsoleObserver, parse_dealer_turn
from buckshot.live.screen import POINTS, Config, Mouse
from buckshot.live.tracker import Mismatch, Tracker
from buckshot.rules import DEALER, IDX, PLAYER


class ParseTests(unittest.TestCase):
    def test_dealer_turn(self):
        moves = parse_dealer_turn("glass saw you:l")
        self.assertEqual(moves, [
            (("item", "glass"), {}),
            (("item", "saw"), {}),
            (("shoot", PLAYER), {"fired": "L"}),
        ])

    def test_adrenaline_and_outcomes(self):
        moves = parse_dealer_turn("adr:beer:b@3 med+ self:b")
        self.assertEqual(moves[0], (("adrenaline", "beer"), {"fired": "B", "slot": 2}))
        self.assertEqual(moves[1], (("item", "medicine"), {"healed": True}))
        self.assertEqual(moves[2], (("shoot", DEALER), {"fired": "B"}))

    def test_rejects_missing_outcome(self):
        for text in ("you", "beer", "med", "banana", ""):
            with self.assertRaises(ValueError, msg=text):
                parse_dealer_turn(text)


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.t = Tracker()
        self.t.new_round(4)
        self.t.new_load(2, 2)

    def test_places_items_in_free_slots(self):
        self.assertEqual(self.t.place_item(PLAYER, "glass"), 0)
        self.assertEqual(self.t.place_item(PLAYER, "saw"), 1)
        self.assertEqual(self.t.state.items[PLAYER][IDX["saw"]], 1)

    def test_tracks_a_shot(self):
        self.t.apply(("shoot", DEALER), fired="L")
        s = self.t.state
        self.assertEqual((s.hp, s.live, s.blank, s.turn), ((4, 3), 1, 2, DEALER))

    def test_rejects_impossible_outcome(self):
        self.t.new_load(0, 2)
        with self.assertRaises(Mismatch):
            self.t.apply(("shoot", DEALER), fired="L")

    def test_dealer_glass_stays_private(self):
        self.t.set_items(DEALER, ["glass"])
        self.t.state = self.t.state._replace(turn=DEALER)
        self.t.apply(("item", "glass"))
        self.assertEqual(self.t.state.dk, "")
        self.assertEqual(self.t.state.known, "????")

    def test_dealer_adrenaline_takes_the_named_slot(self):
        self.t.place_item(PLAYER, "beer")
        self.t.place_item(PLAYER, "beer")
        self.t.set_items(DEALER, ["adrenaline"])
        self.t.state = self.t.state._replace(turn=DEALER)
        self.t.apply(("adrenaline", "beer"), fired="B", slot=1)
        self.assertEqual(self.t.slots[PLAYER][:2], ["beer", None])
        self.assertEqual(self.t.state.blank, 1)

    def test_items_carry_over_to_the_next_load(self):
        self.t.place_item(PLAYER, "cigs")
        self.t.new_load(1, 1)
        self.assertEqual(self.t.state.items[PLAYER][IDX["cigs"]], 1)


class ScriptedObserver(ConsoleObserver):
    def __init__(self, answers):
        self.answers = list(answers)
        self.log = []
        super().__init__(ask=self._ask, say=self.log.append)

    def _ask(self, prompt):
        self.log.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)


class ControllerTests(unittest.TestCase):
    def make(self, answers):
        config = Config(points={p: [i, i] for i, p in enumerate(POINTS)})
        out = []
        obs = ScriptedObserver(answers)
        mouse = Mouse(config, dry_run=True, say=out.append)
        return Controller(mouse, obs, config, say=out.append), out

    def test_round_one_from_start_to_win(self):
        answers = [
            "2",          # max HP
            "1", "1", "", # load: 1 live, 1 blank, you first
            "0",          # no items
            "b",          # bot's shot: blank
            "you:l",      # dealer shoots you with the last (live) shell
            "1", "2", "", # next load
            "0",
            "l",          # bot's shot was live
        ]
        ctl, out = self.make(answers)
        ctl.start_round()
        with self.assertRaises(EOFError):
            while True:
                ctl.start_load()
                while ctl.tracker.state.shells and not ctl.round_over():
                    (ctl.player_turn if ctl.tracker.state.turn == PLAYER else ctl.dealer_turn)()
        clicks = [line for line in out if line.strip().startswith("[click")]
        self.assertTrue(any("shotgun" in c for c in clicks))
        self.assertEqual(ctl.tracker.state.hp[PLAYER], 1)

    def test_item_pickup_clicks_free_slots(self):
        ctl, out = self.make(["4", "2", "2", "", "2", "glass", "saw", "beer, cigs"])
        ctl.start_round()
        ctl.start_load()
        self.assertEqual(ctl.tracker.slots[PLAYER][:3], ["glass", "saw", None])
        clicks = [line for line in out if "[click" in line]
        self.assertIn("item_box", clicks[0])
        self.assertIn("you_1", clicks[1])
        self.assertIn("you_2", clicks[2])
        self.assertEqual(ctl.tracker.state.items[DEALER][IDX["beer"]], 1)

    def test_bad_dealer_turn_is_asked_again(self):
        ctl, out = self.make(["2", "1", "1", "d", "0", "you:l self:l", "you:b"])
        ctl.start_round()
        ctl.start_load()
        ctl.dealer_turn()  # first entry fires two lives from a gun with one
        self.assertTrue(any("again" in line for line in out))
        self.assertEqual(ctl.tracker.state.turn, PLAYER)
        self.assertEqual(ctl.tracker.state.blank, 0)


if __name__ == "__main__":
    unittest.main()
