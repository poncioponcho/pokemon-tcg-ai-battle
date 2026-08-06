# Competition Intelligence

Use this reference when a Kaggle competition slug, URL, title, or search phrase is available and public notebook solutions or discussion activity may inform the plan.

Before using results, read `information-sharing-policy.md`. Public notebooks and discussions are scouting signals, not permission to copy code, text, data, or private strategy.

## Primary Tools

If the `kaggle-competition-intel` MCP server is installed and callable, use its tools before major modeling decisions.

Use `top_open_solutions` for public notebook intelligence.

Tool input:

```json
{
  "competition": "Kaggle competition URL, slug, title, or search phrase",
  "top_score_x": 5,
  "latest_y": 5,
  "min_latest_votes": 30
}
```

Inputs are required by the MCP tool:

- `top_score_x`: number of public solutions by public score, 1 to 20.
- `latest_y`: number of latest high-vote public notebooks, 1 to 50.
- `min_latest_votes`: latest notebooks are included only when `totalVotes` is strictly greater than this threshold.

For proactive scouting inside this skill, use `top_score_x: 5`, `latest_y: 5`, and `min_latest_votes: 30` when the user has not specified values, and state that this was the scouting depth and vote threshold.

The tool returns competition metadata, metric direction, `score_ranked_solutions`, `latest_high_vote_solutions`, a de-duplicated `solutions` union, public resource URLs, last run time, vote count, selection source, and numeric `bestPublicScore` when Kaggle exposes it.

Use `competition_discussions` for discussion intelligence.

Tool input:

```json
{
  "competition": "Kaggle competition URL, slug, title, or search phrase",
  "top_votes_x": 5,
  "latest_replies_y": 5
}
```

Inputs are required by the MCP tool:

- `top_votes_x`: number of top-voted discussion topics, 1 to 50.
- `latest_replies_y`: number of latest-replied discussion topics, 1 to 50.

For proactive scouting inside this skill, use `top_votes_x: 5` and `latest_replies_y: 5` when discussion activity may reveal data issues, rule clarifications, leakage warnings, notebook updates, or fast-moving techniques.

The tool returns competition metadata, `top_voted_discussions`, `latest_replied_discussions`, topic URLs, votes, comment counts, post dates, latest reply dates, sticky status, and topic IDs.

## How To Use Results

Extract actionable patterns:

- Validation scheme hints: folds, time split, group split, leakage controls.
- Data processing: cleaning, resizing, text preprocessing, feature stores, artifact datasets.
- Model families: tree boosting, CatBoost, transformer, CNN, segmentation model, retrieval/reranker, ensembling.
- Training details: loss, metric surrogate, augmentation, class imbalance handling, thresholding, inference tricks.
- Pipeline shape: single notebook, producer/consumer notebooks, dataset artifacts, Kaggle GPU use.
- Leaderboard risk: suspicious public-only tricks, overly tuned thresholds, or public LB chasing.
- Discussion signals: rule clarifications, data bugs, leakage warnings, metric traps, resource constraints, high-signal Q&A, and newly shared techniques.

Do not blindly copy a notebook. Use top solutions as scouting data, then adapt ideas into the local validation and artifact discipline.

Do not publish participant names, handles, or private links in generic reports unless the user explicitly needs source attribution for a public resource. Prefer technique summaries and public URLs.

## Fallbacks

If the MCP tool is not available:

- Use the separate `$kaggle-competition-intel` skill if installed.
- Use Kaggle UI/API/notebook search manually when browsing or Kaggle CLI is available.
- Use existing local competition notes, public writeups, or user-provided links.
- Proceed with the baseline workflow and note that live solution/discussion intelligence was unavailable.

## Reporting

When summarizing intel, include:

- Competition slug/title and metric.
- Score-ranked notebook title, public score, votes, last run time, selection source, and URL.
- Latest high-vote notebook title, votes, last run time, public score if available, selection source, and URL.
- Top-voted and latest-replied discussion title, votes, comment count, latest reply time, and URL.
- Common technique themes.
- Which ideas are worth testing locally.
- Which ideas look risky because they may depend on public leaderboard overfitting or leakage.
