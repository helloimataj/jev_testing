# Buckshot Roulette bot

A bot that plays [Buckshot Roulette](https://store.steampowered.com/app/2835570/Buckshot_Roulette/)
against the dealer. It has three modes:

- `play`: watch the bot play a full run (three rounds) in a simulated game.
- `sim`: play many runs and report win rates for the bot and a simple baseline.
- `advise`: describe a position from your own game and get every move ranked
  by its chance of winning.

It needs Python 3.10+ and has no dependencies.

```sh
python3 -m buckshot play --seed 1
python3 -m buckshot sim --games 200
python3 -m buckshot advise --hp 2 --dealer-hp 3 --max-hp 4 --live 2 --blank 2 \
    --items glass,saw,cigs --dealer-items beer,cuffs
```

`advise` takes `--known L??B` for what you've seen of the shell order, current
shell first (from the magnifying glass or burner phone). It also takes `--saw`,
`--inverted` and `--dealer-cuffed` for effects that are already active. Item
names are `glass cigs beer saw cuffs phone inverter adrenaline medicine`.

## How it decides

`buckshot/solver.py` runs an expectimax search over the player's information
state:

- On the player's turns it takes the move with the highest win chance.
- On the dealer's turns it averages over a model of the dealer.
- For hidden shells it averages over every shell order that fits the shell
  counts and what the player has seen.

All item effects are modelled, including the inverter, adrenaline steals,
handcuff skips and the 40/60 odds of expired medicine.

The search deepens one shell at a time. It stops when it reaches the end of
the load or when a search visits more than 5,000 new states, which happens
with large item hands. Past that point, and after the last shell of a load, a
heuristic estimates the win chance from the HP difference and item counts.

`buckshot/rules.py` holds the rules as pure state transitions. Each transition
returns every outcome with its probability. The solver averages over those
outcomes; the game engine (`buckshot/engine.py`) picks the one that matches
the real shotgun. Both share the same rules code, so they can't drift apart.

## Results

From `python3 -m buckshot sim --games 200`, against the dealer model:

| policy | round 1 | round 2 | round 3 | full run |
| --- | --- | --- | --- | --- |
| solver | 73.5% | 91.0% | 98.0% | 65.5% |
| naive (no items, shoot by the odds) | 51.0% | 22.0% | 11.0% | 1.5% |

Round 1 has no items and only 2 HP, so luck decides most of it. The solver's
edge there comes from exploiting the dealer's habit of shooting itself when
blanks are more likely. A full run must win all three rounds.

## Simplifications

This is a model of the game, not a copy of it:

- **Dealer behaviour is approximated** (`dealer_policy` in `rules.py`). The
  dealer heals when hurt, checks the shell with the glass, saws and cuffs when
  it knows the shell is live, shoots itself when it knows it's blank, and
  otherwise plays the odds, flipping a coin when they're even. The dealer
  never acts on what its burner phone shows. Against the real dealer, the
  bot's moves are only as good as this model.
- **Load sizes are approximate.** Each load has 2–8 shells with at least one
  live and one blank, and items are drawn uniformly at random. Rounds use 2, 4
  and 6 HP with 0, 2 and 4 items per load.
- **Some rules are left out:** the round-3 defibrillator rule (no healing at
  low HP) and the Double or Nothing items.

## Playing the real game (Windows)

`live` mode plays the actual game on your PC: the bot decides each move and
clicks it in the game window. It can't read the screen yet, so it asks in the
console for what it needs to know: the shells at each load, the items you pick
up, what each of your shots and items revealed, and what the dealer did on its
turn. When the answer is certain (say, only blanks are left), it doesn't ask.

```sh
pip install -r requirements.txt
python -m buckshot calibrate     # once: hover over each spot in the game and press F8
python -m buckshot live          # play; add --dry-run to print clicks instead
```

Calibration records 20 points: the shotgun, where you click to aim at the
dealer and at yourself, the item box, and the 8 item slots on each side. Number
the slots however you like, but use the same numbers when the bot asks. Points
are saved to `buckshot_live.json` and only work at the resolution you
calibrated at. If clicks land before the game is ready, raise the
`after_*` wait times (in seconds) in that file.

On the dealer's turn, type what it did, in order. For example,
`glass saw you:l` means it used the glass, then the saw, then shot you with a
live. Type `?` at that prompt for the full list. If what you type can't happen
from the state the bot has tracked (for example, a live shell when none are
left), it asks again.

You handle the menus, the waiver, and the start and end of rounds yourself; the
bot plays from the first load of a round. Close the game or press Ctrl+C in the
console to stop.

### Screen reading (next step)

To drop most of the typing, the bot needs to recognise the shells, items and HP
display from screenshots. `python -m buckshot capture` saves a full-screen
screenshot each time you press F9 (Esc stops). Take screenshots that cover:

- the shells laid out at the start of a load, with a few different live/blank mixes
- your and the dealer's item slots with a variety of items in them
- the HP display at a few different HP values
- an item in your hand after opening the item box
- the magnifying glass, beer and burner phone results

## Tests

```sh
python3 -m unittest -v
```
