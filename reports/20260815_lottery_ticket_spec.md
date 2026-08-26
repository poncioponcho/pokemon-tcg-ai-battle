# 彩票件构建规格：matchup 条件 manual-only router（slot-2 lottery ticket）

委托方：Kimi → codex
时间：2026-08-15 19:45 CST
定位：**final-2 第二槽位的零下行彩票，不是 v22 的替代候选**。它不过 +3pp 晋级闸，也不需要在今晚证明收益；它必须证明的只有"不会坏"（零 fault、可打包、可验证）。

## 证据基础（全部来自已落盘实验，不得重新解释）

1. 结构 2×2 消融（`experiments/runs/v22_structural_factorial_20260815.json`，ledger #173）：
   manual-only 臂（manual guards 保留、hierarchy 移除）对本地 Alakazam 腿约 +6~7pp、Lucario 腿约 +6pp，对 Grim/v22 腿 −13.4pp，加权 −3.46pp。**整体 EV 为负，本件的期权价值来自"只在正收益 matchup 切换"。**
2. matchup 识别审计（`experiments/runs/live_matchup_recognition_audit_20260815.json`，ledger #182 前）：
   严格签名（等待 archetype 签名卡公开出现）turn 4 覆盖 27/82、精度 27/27；turn 6 覆盖 50/82、精度 50/50；新 ref 盲验 turn 2 覆盖 20/32、20/20 正确，Alakazam 6/6 + Lucario 6/6。

## 行为规格

1. 默认且回退：exact v22（`candidates/grim_v22_final/`，tree SHA `0319fee3…ecc`）。
2. 切换触发：**仅当**严格签名把对手识别为 **Alakazam 或 Lucario**（两个正收益腿）时，从识别成功的下一决策起锁存为 manual-only 行为（复用 `experiments/v22_structural_factorial.py` 的 manual_only 臂开关机制），本局内不回切。
3. **只切这两个 archetype**。识别为 Grimmsnarl / Dragapult / 其他 / unknown / 签名冲突 → 永远保持 exact v22。Crustle 明确排除（2-3 负样本且历史诊断指向结构性奖品交换）。
4. 不可破坏的不变量：硬合法性 guard 不绕过；select/protocol 流程不打断；`select-none-before-every-game-v1` reset 保留；识别只使用当回合可见信息（与审计的 visible_information_contract 一致）。

## 已知且接受的方法学缺口（写进提交描述，不掩饰）

- +6~7pp 证据是"整局 manual-only"测得；本件是"识别后中途切换"的杂交行为，其效应未测量。
- 本地 Alakazam/Lucario 腿是 live meta 的代理；live 同名 deck 与本地腿存在分布差。
- 本件是彩票：预期收敛 μ 大概率仍 ≤ v22，靠 max() 机制保证零下行。

## 今晚验收闸（与晋级无关的工程闸，全过才允许提交）

1. **零 fault**：本地四腿 ≥500 局（含 v22 镜像），candidate fault = 0、内部异常 = 0。
2. **dormant 复现**：mode=exact（不触发识别）时在 82 场冻结 replay 上 0 mismatch（复用 `routeA_wrapper_replay_selftest` 的模式）。
3. **行为 canary**：在 82 场 replay 状态上，切换发生率应与审计覆盖同量级（turn≤6 约 1/4–1/2 局发生识别，其中仅 Alakazam/Lucario 子集真正切换）；若切换率 >50% 或对 Grim/unknown 发生切换 → BEHAVIOR_KILL，不交。
4. **时延**：单步决策 p99 与 v22 同量级（<1ms 量级），不引入超时风险。
5. **打包**：独立候选目录 + 归档双 SHA + manifest；archive 与候选树 SHA 记录进 ledger。

## 提交编排（今晚）

1. 全闸过后**只交一发**，提交描述注明 lottery-ticket 性质与上述缺口。
2. 交后确认 API 状态 COMPLETE（validation 通过）；若 Error，用今天剩余额度修一次，仍 Error 则今晚放弃彩票，明天双 v22 收官。
3. 今晚交完后 latest-2 = {v22(55516725), 彩票}。**今晚之后不再交任何件。**
4. 明早读彩票过夜轨迹（对照 v22 的 600→815/10h 曲线），明天收官编排按 `reports/20260816_收官runbook.md` 执行，final-2 目标 = {v22, 最好的一张票}。

## Kill criteria（任一触发即放弃彩票，不硬撑）

- 构建+验收超过今晚 ~23:30 仍未完成；
- 零 fault 闸或 dormant 复现闸失败且 30 分钟内修不好；
- 行为 canary 显示对非目标 archetype 发生切换。

## 明确禁止

- 不得为今晚提交而降低上述工程闸；
- 不得调识别阈值去"优化"覆盖（阈值来自已冻结审计）；
- 不得动 exact v22、submission_baseline、既有 Automation；
- 不得把本件包装成"改进版 v22"——它是独立候选，提交描述必须如实。
