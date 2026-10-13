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

## Tests

```sh
python3 -m unittest -v
```
