# 决赛前版本固化提案（待用户授权）

核查时间：2026-08-15 19:24 CST
当前分支：`dev-v23-mega-lucario`
当前 HEAD：`93b98189c72a540d46e0f42696b3227049d823e5`

## 为什么不能直接 `git add -A`

工作树当前含32个 tracked 修改、4个 tracked 删除和310个 untracked 条目，混有旧 NN、
数据集、备份、临时目录和历史实验。全量提交会把与收官无关甚至被淘汰的资产一起固化，
也可能误收大文件。exact-v22 candidate/artifact 的53个文件已经在 Git 中，冻结归档 SHA
另由 manifest 保证，无需靠 `add -A` 冒险。

## 推荐的窄固化

授权后只做一次显式路径 commit，不纳入47MB Route-A 原始批、11MB replay 压缩包、临时
目录或历史备份：

1. 收官状态：`HANDOFF.md`、`memory/project-planner/tasks.md`、
   `experiments/ledger.jsonl`、`reports/20260816_收官runbook.md`。
2. 测量修复：`scripts/candidate_h2h.py`、`scripts/safe_json_output.py`。
3. Route-A 可复算代码与报告：`experiments/routeA_*.py`、本轮 matchup 审计脚本、
   Route-A 预注册/裁决/赛后方向报告。
4. 决赛机制网页核查报告与 matchup 可行性报告。

建议 commit message：

`chore(final): freeze exact-v22 runbook and route-A postmortem`

commit 成功且 `git show --stat` 人工复核后，再创建 annotated tag：

`pre-final-submission-20260816`

## 明确排除

- `.kaggle_stage_*`、`.playwright-mcp/`、`.trae/`、任何 `*.bak-*`；
- 旧 inference dataset/model、历史 arena JSON、已淘汰候选目录；
- `experiments/runs/routeA_collect_formal36432_20260815.json` 与 replay tar.gz；
- 任何未逐项列出的删除。

当前未执行 `git add`、`git commit` 或 `git tag`。需用户明确授权后再按显式路径清单执行。
