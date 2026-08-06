# Submission Endgame

Use this reference before stopping any Kaggle competition task. The skill's end-to-end expectation is a scored Kaggle submission, not just a local model, remote run, or notebook architecture.

Before publishing final code, reports, models, or artifacts outside the team, read `information-sharing-policy.md`.

## End Condition

Continue working until one of these states is reached:

- `scored`: Kaggle accepted and processed a submission, and the submission status plus public score or visible scoring result has been retrieved.
- `blocked`: an external condition prevents scoring, such as missing Kaggle credentials, competition rules not accepted, submission quota exhausted, competition closed, scoring disabled, required manual UI-only action, missing kernel version, or Kaggle service failure.

If a code-competition submission fails with a vague scoring/runtime error, do not mark it blocked immediately. Read `code-competition-debugging.md`, patch the final kernel defensively, rerun/resubmit, and only mark blocked after retry attempts are exhausted by an external condition.

If blocked, record the exact error text, command attempted, competition slug, next command/action, retry count, and whether any local/remote artifacts are ready.

## Classic Submission Flow

For ordinary competitions where a prediction file is accepted:

```bash
kaggle competitions submit COMPETITION_SLUG -f SUBMISSION_FILE -m "RUN_ID_OR_MESSAGE"
kaggle competitions submissions COMPETITION_SLUG -v -q
```

Before submitting:

- Verify rules have been accepted and credentials work.
- Verify the file exists, row count matches sample submission, IDs and order are correct, required columns exist, labels/probabilities are in the expected format, and values are clipped/rounded only when the metric or competition requires it.
- Compare local CV and OOF diagnostics against the submission being sent.

After submitting:

- Poll or re-run `kaggle competitions submissions` until the submission is processed or a failure is visible.
- Save the latest submission table or parsed record to `submission_receipt.json`.
- Add the public score/status to the experiment log and final response.

## Code Competition Or Final Notebook Flow

For code competitions or notebook-scored workflows:

1. Ensure all producer notebooks/scripts have completed successfully.
2. Promote durable producer notebook outputs to private datasets, especially trained model/checkpoint outputs; attach those datasets to downstream notebooks through `dataset_sources`, and use `kernel_sources` only for short-lived output chains.
3. Push/run the final consumer notebook/script.
4. Poll the final consumer until complete.
5. Retrieve outputs and verify `submission.csv`, logs, and manifests.
6. Submit the final consumer kernel/version for scoring.
7. Retrieve the submission status/score.
8. If scoring fails, retrieve available kernel/submission logs, apply the code-competition debugging loop, rerun the final consumer, and resubmit until scored or blocked.

Command pattern:

```bash
kaggle kernels push -p kaggle_kernels/FINAL_CONSUMER
kaggle kernels status USER/FINAL_CONSUMER
kaggle kernels output USER/FINAL_CONSUMER -p remote_outputs/RUN_ID -o
kaggle competitions submit COMPETITION_SLUG -f submission.csv -k USER/FINAL_CONSUMER -v KERNEL_VERSION -m "RUN_ID_OR_MESSAGE"
kaggle competitions submissions COMPETITION_SLUG -v -q
```

Determine `KERNEL_VERSION` from the Kaggle kernel status/output metadata, Kaggle UI/API, or the CLI output available in the environment. If the version cannot be determined programmatically, record that as a blocker with the final kernel ref and ready submission artifact.

The final consumer must not depend on rerunning producer notebooks during scoring. For a complicated architecture, it should attach the producer-created model/artifact datasets, load model files from `/kaggle/input/...`, validate manifests, and submit only after all required upstream datasets are present and versioned.

## Final Response Requirements

A completed run summary must include:

- Competition slug.
- Run ID and final artifact/kernel reference.
- Local CV/OOF score.
- Kaggle submission status and public score if processed.
- Error/debug loop summary if a scoring failure occurred.
- Submitted file path or kernel/version.
- Producer dataset/kernel refs for complicated architectures.
- Any remaining private-LB or validation-risk caveats.
