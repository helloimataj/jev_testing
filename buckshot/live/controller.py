"""Plays a real game: decides with the solver, clicks with the mouse.

The loop runs one round at a time. For each load it records the shells and
items, then on the player's turns it clicks the best move and records the
outcome, and on the dealer's turns it records what the dealer did. Whatever
the bot can't see yet comes from the observer.
"""

from __future__ import annotations

from ..rules import DEALER, PLAYER, describe, item_names, p_current_live
from ..solver import rank_actions
from .observe import ConsoleObserver
from .screen import Config, Mouse
from .tracker import Mismatch, Tracker

ROUND_ITEMS = {2: 0, 4: 2, 6: 4}  # usual items per load for each round's HP


class Controller:
    def __init__(self, mouse: Mouse, observer: ConsoleObserver, config: Config, say=print, budget: int = 5_000):
        self.mouse = mouse
        self.obs = observer
        self.config = config
        self.say = say
        self.budget = budget
        self.tracker = Tracker()

    # -- setup ------------------------------------------------------------

    def start_round(self, default_hp: int = 2):
        hp = self.obs.round_hp(default_hp)
        self.tracker.new_round(hp)
        return hp

    def start_load(self):
        live, blank, first = self.obs.load()
        self.tracker.new_load(live, blank, first)
        default_items = ROUND_ITEMS.get(self.tracker.max_hp, 0)
        n = self.obs.items_this_load(default_items)
        if n:
            self.pick_items(n)
            current = item_names(self.tracker.state.items[DEALER])
            self.tracker.set_items(DEALER, self.obs.dealer_items(current))
        self.show()

    def pick_items(self, n: int):
        """Opens the item box and puts each item in the next free slot."""
        self.mouse.click("item_box", self.config.after_box)
        for i in range(1, n + 1):
            name = self.obs.picked_item(i, n)
            try:
                slot = self.tracker.free_slot(PLAYER)
            except Mismatch:
                self.say("  Your slots are full; the game discards this item.")
                continue
            self.mouse.click(f"you_{slot + 1}", self.config.after_place)
            self.tracker.place_item(PLAYER, name, slot)

    def show(self):
        s = self.tracker.state
        self.say(f"   HP you {s.hp[PLAYER]} / dealer {s.hp[DEALER]} | {s.live} live, {s.blank} blank left"
                 f" | live chance {p_current_live(s):.0%}")
        mine = [f"{i + 1}:{n}" for i, n in enumerate(self.tracker.slots[PLAYER]) if n]
        self.say(f"   Your slots: {' '.join(mine) or 'none'} | dealer: {', '.join(item_names(s.items[DEALER])) or 'none'}")

    # -- turns ------------------------------------------------------------

    def player_turn(self):
        ranked = rank_actions(self.tracker.state, self.budget)
        value, action = ranked[0]
        self.say(f"> {describe(action)}  (win chance {value:.0%})")
        extra = self.execute(action)
        while True:
            try:
                self.tracker.apply(action, **extra, **self._result(action))
                return
            except Mismatch as e:
                self.say(f"  {e}. Try again.")

    def execute(self, action) -> dict:
        """Clicks `action` in the game; returns the slot used, if any."""
        kind, name = action
        cfg = self.config
        if kind == "shoot":
            self.mouse.click("shotgun", cfg.after_pickup)
            self.mouse.click("aim_dealer" if name == DEALER else "aim_self", cfg.after_shot)
            return {}
        if kind == "item":
            slot = self.tracker.slot_of(PLAYER, name)
            self.mouse.click(f"you_{slot + 1}", cfg.after_item)
            return {"slot": slot}
        own = self.tracker.slot_of(PLAYER, "adrenaline")
        self.mouse.click(f"you_{own + 1}", cfg.after_item)
        self.mouse.click(f"dealer_{self.obs.dealer_slot(name) + 1}", cfg.after_item)
        return {}

    def _result(self, action) -> dict:
        """Asks for whatever the move revealed that the bot can't infer."""
        kind, name = action
        if kind == "shoot":
            return {"fired": self._fired("The shot")}
        if name == "glass":
            return {"fired": self._fired("The magnifying glass shows")}
        if name == "beer":
            return {"fired": self._fired("The racked shell")}
        if name == "medicine":
            return {"healed": self.obs.healed()}
        if name == "phone":
            return {"phone": self.obs.phone(self.tracker.state.shells)}
        return {}

    def _fired(self, what: str) -> str:
        t = self.tracker
        if t.needs_fired():
            return self.obs.fired(what)
        fired = t.certain_fired()
        self.say(f"   ({what.lower()} must be {'live' if fired == 'L' else 'blank'})")
        return fired

    def dealer_turn(self):
        while True:
            moves = self.obs.dealer_turn()
            saved = (self.tracker.state, [list(s) for s in self.tracker.slots])
            try:
                for action, obs in moves:
                    if self.tracker.state.turn != DEALER:
                        raise Mismatch("that's more than the dealer could do in one turn")
                    self.tracker.apply(action, **obs)
                    if self.round_over() or not self.tracker.state.shells:
                        break
                return
            except Mismatch as e:
                self.tracker.state, self.tracker.slots = saved
                self.say(f"  {e}. Enter the whole dealer turn again.")

    # -- main loop --------------------------------------------------------

    def round_over(self):
        s = self.tracker.state
        if s.hp[PLAYER] <= 0:
            return "lost"
        if s.hp[DEALER] <= 0:
            return "won"
        return None

    def play_round(self, default_hp: int = 2) -> bool:
        self.start_round(default_hp)
        while True:
            self.start_load()
            while self.tracker.state.shells and not self.round_over():
                if self.tracker.state.turn == PLAYER:
                    self.player_turn()
                else:
                    self.dealer_turn()
                if self.tracker.state.shells and not self.round_over():
                    self.show()
            result = self.round_over()
            if result:
                self.say("Round won!" if result == "won" else "Round lost.")
                return result == "won"
            self.say("-- Shotgun empty, reloading.")

    def play(self):
        hp = 2
        while True:
            self.play_round(hp)
            hp = {2: 4, 4: 6}.get(self.tracker.max_hp, self.tracker.max_hp)


def run(dry_run: bool = False, budget: int = 5_000):
    config = Config.load()
    controller = Controller(Mouse(config, dry_run), ConsoleObserver(), config, budget=budget)
    print("Live mode. Keep this window beside the game; the bot clicks in the game")
    print("and asks here for anything it can't see. Ctrl+C to stop.\n")
    try:
        controller.play()
    except (KeyboardInterrupt, EOFError):
        print("\nStopped.")
