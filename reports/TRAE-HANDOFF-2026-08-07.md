# Trae 交接说明：本轮 teacher→distill 训练与提交流程（2026-08-07）

> 目的：让 Trae 的每日自动化（`kernel_poll` / `kaggle_artifact` / `auto_submit`）
> 在继续盯训练的同时，**遵守本轮修复后的提交纪律**，不要用旧逻辑/污染产物提交。
> 下面全部为 2026-08-07 22:40 的实时状态，训练/配额/自动化状态均已核实。

---

## 1. 当前训练状态（关键）

- kernel: `daniel1547/ptcg-gpu-train-teacher-distill`
- 阶段：**teacher**（`--stage teacher`，BC 8 + AWR 5），**尚未 distill**
- 启动：14:02（session 340722927）；GPU = **P100**（T4 配额已耗尽，
  `timeUsed 5300s` 新窗口在爬 = 确认在跑，非卡死）
- 12h 硬线：**02:02 明天**。若到点未 COMPLETE → 按 TLE 处置，不要自行改训练代码。
- 数据：**干净版 ptcg-tensors**（8/7 11:51 生效，deck 归属已修复）。
- 代码数据集 ptcg-code：**已更新为优化版**（8/7 19:41，uint8-on-GPU + batch prefetch，
  数值与旧版位级一致，已对照验证 loss 相同）。

## 2. 自动化状态（已改，勿回退）

| 任务 | 状态 | 说明 |
|---|---|---|
| `kernel_poll.sh`（10min） | **运行中** | 保留：distill COMPLETE 后自动把 `model_student.npz` 拷到项目根 |
| `kaggle_artifact.sh`（30min） | 运行中 | 保留，但注意它只会打 READY 报告、**不提交** |
| `auto_submit.sh`（每小时） | **已 PAUSE**（job `724e8900748f`） | 本轮不允许自动提交，由人工/agent 主导 |
| `redraw_tensors.sh`（10min） | 幂等锁定 | `tensor_redraw_done` 已存在，不会再重抽 |

**禁止**：resume 这些被改状态的自动化；不要 `resume` auto_submit job，除非本文件被后续明确更新。

## 3. 污染产物已隔离（勿恢复）

8/6 污染轮（deck 归属 bug）的产物已移出项目根：
- 位置：`reports/quarantine-polluted-2026-08-07/`
- 内含：`submission.tar.gz`（12:00 污染版）、`model_student.npz`（11:52）、
  `artifact-ready-2026-08-07.md`（12:00 READY 报告）
- 说明：隔离原因详见该目录 `README.md`
- 项目根当前**无** `submission.tar.gz` / `model_student.npz` → 自动化无物可提

## 4. 提交纪律（distill 完成后由人工/agent 主导，不走 auto_submit）

**验收双门（都要过）：**
1. hybrid（main.py + 新 npz）总胜率 > 纯规则基线（基线参考：总 WR **0.628**）
2. vs `v23_2_rules` 镜像 ≥ 基线 **0.520**

**流程：**
1. `kaggle kernels output daniel1547/ptcg-gpu-train-teacher-distill -p reports/kerr_distill`
2. 确认 `reports/kerr_distill/output/model_student.npz` 存在
3. 拷贝新 npz 到项目根 → 本地 arena（2000 局 × v23_2_rules / v22_5_rules / first / random）
4. 双门判定：
   - **过** → `bash pack.sh` → `python3 submit.py`（有新鲜度守卫，过期 tar 会被拦，属正常）
   - **不过** → 不提交，贴 arena 数据
5. 报告格式：teacher/distill session 时长、GPU 型号（日志 Tesla 行）、末轮 canary_top1、
   npz 大小、四门对阵表、双门判定

## 5. 其他注意事项

- 不要重抽张量、不要动 `inference/dataset/data/`
- 不要运行 `scripts/redraw_tensors.sh` / `scripts/resume_kernel.sh`
- 不要修改 `inference/dataset/` 训练代码；发现疑似 bug 停下汇报
- GPU 周配额：本周剩余紧张，**任何新训练/重推都先汇报确认**，不要自行 `--shape` 重推

## 6. 闭环守护（2026-08-08 06:32 上线）

- 脚本：`scripts/closed_loop_train.py`，后台 PID（`ps aux | grep closed_loop_train`）
- 状态：`~/.hermes/state/closed_loop_state.json`；日志 `reports/closed-loop.log`
- 职责：自动推进 teacher→distill→arena→双门→提交，无需人工盯守
- **重要**：此守护是当前唯一允许的提交者（auto_submit cron 已 pause）。
  它只会在双门（总 WR>0.628 且 vs v23_2_rules≥0.520）通过后 pack+submit。
- 若 Trae 看到 `closed_loop_state.json` 的 state 为 `DONE`/`GATE_BLOCKED`/`FAILED`，
  表示闭环已到终态：**不要再重推/重跑**，直接汇报状态即可。
- 实测：teacher session 超 12h 未被 Kaggle 砍杀（06:48 已 16.8h 仍 RUNNING 且
  GPU 配额持续消耗），守护会一直等 COMPLETE/ERROR/CANCEL，不会因超时误判。

