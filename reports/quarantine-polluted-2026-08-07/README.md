# 污染版产物隔离说明（2026-08-07）

## 背景

8/6 训练轮使用的 `ptcg-tensors` 张量受 `extract.py` deck 归属 bug 污染
（"my deck" 槽位填入了对手牌组）。该轮训练于 8/7 10:50 被 12h TLE 砍掉，
其产物无任何提交价值。

## 隔离内容

- `submission.tar.gz`（12:00 打包，内含污染版 `model_student.npz`）
- `model_student.npz`（11:52，污染版）
- `artifact-ready-2026-08-07.md`（12:00 产物闭环 READY 报告）

## 处理

- 上述文件已移入 `reports/quarantine-polluted-2026-08-07/`，不再位于
  项目根 / `reports/`，确保 `auto_submit.sh` / `kaggle_artifact.sh`
  不会把它们当作可提交产物。
- `auto_submit.sh` cron（job 724e8900748f「午夜自动提交」）已 **pause**，
  本轮训练（teacher→distill）期间不自动提交，提交由人工/agent 主导。

## 后续

干净数据（8/7 11:51 生效的 ptcg-tensors）训练产出的新 `model_student.npz`
会由 `kernel_poll.sh` 在 distill COMPLETE 后拷到项目根，届时走正常验收：
双门（总 WR > 0.628 且 vs v23_2_rules ≥ 0.520）→ `bash pack.sh` → 人工提交。
