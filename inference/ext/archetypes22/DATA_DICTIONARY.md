# Data dictionary

All CSV files are UTF-8 with a header row, except files under `decklists/`, which intentionally contain one integer Card ID per line and no header.

## `archetypes.csv`

One row per deck. Stable key: `deck_id`.

| Field | Meaning |
|---|---|
| `deck_id` | Stable identifier from `EX_01` to `EX_22`. |
| `deck_name` | Human-readable headline name. |
| `archetype` | Short machine-friendly archetype label. |
| `validation_status` | `validated`, `invalid`, or `pending_validation`. |
| `source_kind` | Canonical CSV or named-list transcription. |
| `source_confidence` | Provenance confidence: `high`, `medium`, or `pending`. |
| `tempo` | `aggressive`, `midrange`, `control`, `toolbox`, or `combo`. |
| `prize_profile` | `mostly_single`, `mixed`, or `mostly_multi`. |
| `setup_complexity` | Setup burden: `low`, `medium`, or `high`. |
| `pilot_complexity` | Decision burden: `low`, `medium`, or `high`. |
| `pokemon_count`, `trainer_count`, `energy_count` | Physical card counts by broad class. |
| `unique_card_count` | Number of distinct Card IDs. |
| `damage_engine` | Curated description of how damage is generated. |
| `resource_engine` | Curated description of draw, search, acceleration, or recycling. |
| `primary_win_condition` | Board-level route to winning. |
| `key_decisions` | Semicolon-separated decisions that matter for an agent. |
| `suggested_training_role` | Recommended use in a training or evaluation curriculum. |
| `strengths`, `risks` | Structural strengths and failure modes, not win-rate claims. |

## `decks_long.csv`

One row per unique `(deck_id, card_id)` pair. `quantity` is the number of copies. Card identity fields are included for direct analysis without publishing bulk card-effect text.

## `decks_expanded.csv`

One row per physical card copy. `slot` runs from 1 to 60 within each deck and preserves the input order. Grouping by `deck_id` reconstructs every machine-ready list.

## `validation_report.csv`

One row per archetype. `errors` is blank for validated lists. Legality status and source confidence answer different questions and should not be merged.

## `card_usage.csv`

One row per Card ID used anywhere in the collection.

| Field | Meaning |
|---|---|
| `deck_count` | Number of decks containing the card. |
| `deck_share` | `deck_count` divided by the 22 validated decks. |
| `total_copies` | Total copies across all decks. |
| `average_copies_when_used` | Mean quantity among decks that use the card. |

## `deck_similarity.csv`

An ordered 22 × 22 matrix (484 rows).

| Field | Meaning |
|---|---|
| `shared_unique_cards` | Size of the Card ID intersection. |
| `shared_copies` | Sum of the minimum quantities over all Card IDs. |
| `weighted_jaccard` | `sum(min(a_i,b_i)) / sum(max(a_i,b_i))`. |
| `cosine_similarity` | Cosine similarity of the Card ID quantity vectors. |

The diagonal is 1.0. Both similarity metrics are symmetric.
