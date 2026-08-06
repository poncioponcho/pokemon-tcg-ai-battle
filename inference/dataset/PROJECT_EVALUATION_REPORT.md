# Project Evaluation Report — NN Policy vs Rule Agent

Date: 2026-08-05
Data basis: 4432 leaderboard replays / 525371 decisions / card_vocab_v1

## 1. Training Result (current data)

| Stage | Fixed-test top1 | Fixed-test recall | Canary top1 | Canary recall |
|---|---:|---:|---:|---:|
| BC (6 epochs) | 0.5207 | 0.3758 | - | - |
| AWR extension (best canary epoch 10) | **0.5332** | **0.4026** | **0.5432** | **0.3995** |

Primary model: `inference/dataset/data/model_awr.pt`
PSI on scalars: 0.018 (no drift)

## 2. Per-Context NN Weakness Profile (fixed test)

| Context | Share | NN top1 | Assessment |
|---|---:|---:|---|
| Main action choice (0) | 59.5% | 0.451 | Weakest large block |
| Attack (7) | 17.9% | 0.587 | Decent |
| Play card (21/22) | 6.0% | 0.71-0.78 | Strong |
| Simple select (1/2/3/40/43) | 7.9% | 0.72-0.96 | Strong |
| Numeric (13/14) | 2.8% | 0.43-0.65 | Weak |

## 3. NN vs Rule Agent on Real Replay Observations

`eval_project.py` ran both policies on 5479 real decision observations.

| Metric | Rule agent v23.1 | NN policy |
|---|---:|---:|
| Legal rate | 1.000 | 1.000 |
| Exact match with top-player action | 0.218 | **0.377** |
| Chosen action contains top-player action | 0.260 | **0.438** |
| Attack context exact match | 0.118 | **0.388** |
| Main context exact match | 0.237 | **0.382** |
| Context 13 exact match | 0.043 | **0.522** |

Conclusion: the trained NN policy matches elite decisions substantially better
than the current rule agent in every major decision class. The rule agent's
biggest weakness is attack selection (11.8% agreement), where the NN is 3.3x
closer to elite play.

## 4. Project Adjustment Decision

Evidence-driven conclusions and actions:

1. The NN policy is the stronger decision engine and the primary reason to keep
   investing in the BC+AWR line. Submission runtime cannot yet be assumed to
   provide torch, so the submission remains the rule agent v23.1 for this cycle.
2. The rule agent's attack-selection gap is not patched heuristically this
   cycle; a heuristic change without a local engine cannot be validated safely
   and would risk regression (replay regression protects legality, not strategy).
3. Next data round (expected 18:00): extract with captured-team metadata, run
   the quality-filtered AWR sweep (`quality_subset.py` + `awr_sweep.py`), select
   the best model by canary, and reassess NN integration after verifying torch
   availability in the Kaggle agent runtime.
4. If torch is unavailable in the runtime, distill the NN's attack-selection
   policy into rule refinements using the per-context analysis above.

## 5. Artifacts

- Comparison script: `inference/dataset/eval_project.py`
- Comparison JSON: `inference/dataset/logs/nn_vs_rule_eval.json`
- Canary metrics: `inference/dataset/logs/canary_metrics_submit.json`
- Models: `model_awr.pt` (primary), `model_awr_before_awr20.pt`,
  `model_awr_before_submit.pt` (backups)
