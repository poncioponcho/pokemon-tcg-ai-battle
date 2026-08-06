# Information Sharing Policy

Use this reference before sharing competition-related code, notebooks, datasets, models, artifacts, reports, or repository contents outside the active team or local workspace.

## Policy Checkpoint

Kaggle competition rules vary by competition. Always inspect the target competition's rules, data tab, code/notebook requirements, and any competition-specific terms before publishing or privately sharing work.

Default to these guardrails:

- Do not privately share competition code, data, generated features, trained models, notebook outputs, or submissions outside the active team unless the competition rules explicitly allow it.
- Public sharing of competition code is acceptable only when the target rules allow public sharing, the code is available to all participants on equal terms, and third-party IP/license obligations are satisfied.
- Do not publish, commit, redistribute, or attach competition data outside allowed Kaggle surfaces unless the data license explicitly allows redistribution.
- Do not publish data-derived artifacts such as feature tables, embeddings, pseudo labels, checkpoints, OOF/test predictions, or submissions when they could expose restricted data or create an unfair private advantage.
- Keep Kaggle API credentials, tokens, cookies, private dataset handles, unreleased competition data, and downloaded outputs out of Git.
- Treat public notebooks and discussions as scouting signals. Adapt ideas into the local validation workflow; do not copy code or text without checking license and attribution requirements.
- For active competitions, prefer Kaggle-native public sharing surfaces such as public notebooks or discussion posts when the goal is to make code visible to all participants.
- Keep producer kernels, artifact datasets, model datasets, and final consumer kernels private by default. Make them public only after an explicit rules and license check.
- If rules are ambiguous, keep materials private and record the uncertainty in the run log.

## GitHub Sharing Checklist

Before pushing a competition repository to public GitHub:

1. Verify the target competition allows the intended public sharing.
2. Remove raw data, private data, generated data-derived artifacts, downloaded Kaggle outputs, model checkpoints, submissions, and score receipts when they are not allowed for redistribution.
3. Remove secrets: `kaggle.json`, `.env`, API tokens, cookies, service credentials, and private URLs.
4. Check all third-party packages, pretrained weights, notebooks, snippets, and copied assets for compatible licenses.
5. Include only generic workflow code, competition-safe training/inference code, config templates, and documentation that does not expose restricted data or private team strategy.
6. If sharing active competition solution code publicly, ensure it is genuinely public and not selectively shared outside the team.

## Remote Artifact Defaults

- Use private Kaggle kernels for experiments unless public visibility is intentional and rules-safe.
- Use private Kaggle datasets for intermediate features, model checkpoints, predictions, and notebook outputs.
- Use `kernel_sources` only for short-lived notebook-output chains; use private datasets for durable artifacts.
- Record dataset and kernel handles in manifests, but avoid exposing private handles in public GitHub documentation when they are not intended for external access.
