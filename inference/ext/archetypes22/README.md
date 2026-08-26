# PTCG AI Battle: 22 Curated Deck Archetypes

Twenty-two exact, machine-ready 60-card deck lists for **The Pokémon Company - PTCG AI Battle Challenge Simulation**, plus strategy labels and structural analytics designed for agent training and evaluation.

## Why this is useful

A policy that looks strong on one familiar list can fail after the deck changes. This release turns a collection of deck lists into a small **deck-intelligence benchmark**:

1. Train against a diverse deck population instead of one or two public baselines.
2. Measure policy robustness by archetype, prize profile, setup complexity, and pilot complexity.
3. Select complementary opponents using the card-overlap similarity matrix.
4. Export any validated list directly in the competition's one-Card-ID-per-line format.

## What is included

- **22/22 validated decks**, EX_01 through EX_22.
- **1,320 physical card-copy rows** in `decks_expanded.csv`.
- A compact quantity table in `decks_long.csv`.
- Human-curated strategic labels in `archetypes.csv`.
- Transparent legality results in `validation_report.csv`.
- Cross-deck staples in `card_usage.csv`.
- A complete 22 × 22 ordered similarity matrix in `deck_similarity.csv`.
- Ready-to-use competition deck files in `decklists/` and `decklists.zip`.

## Recommended starting points

### Build a curriculum

Start with low-complexity tempo decks, then introduce toolbox, spread-damage, disruption, and multi-engine combo lists. The `suggested_training_role` column explains what each deck stresses.

### Create a diverse evaluation panel

Use low `weighted_jaccard` pairs to avoid evaluating on several near-duplicate lists. Report results by `tempo`, `prize_profile`, and complexity rather than only an overall average.

### Test deck-policy interaction

Hold the policy fixed and rotate all 22 lists. Large changes are evidence that deck representation, action selection, or long-horizon planning may be overfit to the original list.

## Minimal Python example

```python
import pandas as pd

archetypes = pd.read_csv("/kaggle/input/ptcg-ai-battle-22-curated-deck-archetypes/archetypes.csv")
cards = pd.read_csv("/kaggle/input/ptcg-ai-battle-22-curated-deck-archetypes/decks_long.csv")
similarity = pd.read_csv("/kaggle/input/ptcg-ai-battle-22-curated-deck-archetypes/deck_similarity.csv")

validated = archetypes.query("validation_status == 'validated'")
print(validated[["deck_id", "deck_name", "suggested_training_role"]])
```

## Validation and provenance

The 21 canonical CSV lists are preserved from the curated working set. EX_10 was transcribed from a named 60-card list, resolved against the competition card catalog, and structurally validated. Its `source_confidence` remains `medium` so provenance confidence is not confused with deck legality. Ambiguous names were resolved explicitly rather than by silently selecting the first Card ID.

Validation checks:

- exactly 60 cards;
- every Card ID exists in the supplied catalog;
- no more than four copies except Basic Energy;
- no more than one ACE SPEC;
- at least one Basic Pokémon.

## Important limitation

This is a **deck and metadata dataset**, not a strength ranking. V1 contains no simulated matchup win rates and makes no claim that one archetype is intrinsically stronger. Performance depends on policy quality, search budget, rules implementation, matchup distribution, and variance.

## Version

`v1.0.0` — released 2026-07-29. See `CHANGELOG.md` for details.
