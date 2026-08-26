# 8/15 会师判读 Cheat Sheet（一页纸，零思考照单执行）

> 用途：8/15 20:00 探针判读会话（提醒 `automation_dd5afa22` 拉起的 fresh session）的判读口径。
> 铁律：8/17 07:59 截止前一切分数是**瞬读不记账**（#98）；ledger **#135 为收官预留**，勿占用；收官记账只走 `reports/2026-08-17_收官checklist.md`。
>
> **【A 轨状态更新 08-13 15:36：N1/K0=KILL，仪器轨已关闭】** N1 全量（7 腿×11 格×n=400=30800 局，零 fault）加权 fail 0.649≥0.50 → **KILL**：Alakazam 1.060 / Crustle 1.385 / Cornerstone 0.690 / Archaludon 0.975 四腿 R2 不可达 1.5 线（仅 Lucario/Grimmsnarl/Dragapult 可达）；E1 带仅 Grimmsnarl 一腿可达。N2/N3/N4 不执行 → **本件 ①②节、③ 表的「仪器 Δ」列、④ 的候选重排行全部 moot（留档备查，勿照跑）**。8/15 会师实际议程缩水为两项：**①探针 live WR 判读（⑤ 命令仍有效；判读简化：Δ≥15pp→探针留并记，<15pp→retroactive NO-GO 归档，仪器列不存在故无 2×2 落格）②dying_674 翻牌三条件（④ 第二行仍有效：探针 flat/NO-GO + 当日额度余≥1 + 用户点头）**。⑥ 背景数字仍有效。详见 HANDOFF A 轨条（CLOSED）+ ledger `n0_built_and_n1_k0_kill`。

## ① 校准目标（A 轨仪器，N3 判读用）

| 量 | 值 | 性质 |
|---|---|---|
| equal-pilot 基线（live 配比加权） | **0.744** | **软锚 ±3-5pp**（n=41 配比推得，逐族 n=1-11 CI 宽） |
| live 实测 WR（config A，#132） | **0.476**（判读带 ±5pp） | 软锚 σ≈7.7pp（n=42） |
| 签名对手需解释的缺口 | **26.8pp**（0.744→0.476） | 软数，**非** 36.4pp（9.6pp 权重错配已由重加权消掉，不占旋钮预算） |

**口径：K1 命中判据按 0.476±5pp 宽松带执行；0.744/26.8pp 是软锚，软锚上不做硬卡。**

**签名轴定义/目标值/量测口径的唯一权威源：`experiments/pilot_investigation/signature_caliber_spec.md`（冻结 2026-08-13）。凡引用签名数字（retreat 带、能量 pre_act% 带、K0 的 ≥1.5/局读法）一律从 spec 冻结表取，禁止凭记忆用旧数字（0.42/2.14、5.7%/11% 等已作废）。**

## ② K1 三分支（仪器 WR 判读）

> K0 判读口径（如需回溯 N1 可达性判定）：`experiments/pilot_investigation/n1_knob_scan_runbook.md` §3（互斥三分支：KILL=加权失败≥50%（无条件优先，端点 50% 归 KILL）、FLAG=加权<50% 且大腿/残差腿 fail、PASS=加权<50% 且无 FLAG 条件）。
> N3 校准报告模板（8/14 下午填数后 = 本判读的输入件）：`experiments/pilot_investigation/n3_calibration_report_template.md`（双校准并报+K1 判读行+FLAG 复核位）。

**互斥三支（08-13 12:40 修正，替代旧四行——旧 kill 分支文字含 <0.426 与跌破撞车、处置相反，已排他；跌破独占下沿）：**

- WR **< 0.426**（跌破=旋钮过头，对手强于真人=签名承重的好事）→ **回调**重校（回 N1/N2 降档）；**独占下沿，永不判 kill**
- WR ∈ **[0.426, 0.526]**（命中）→ **仪器毕业**，可进候选重排（N4）
- WR **> 0.526**（出带 under-fire）→ 落 **0.6–0.7 或卡边界**（±σ_WR≈1pp）→ **触发重拉 68 局 replay 做 per-archetype 签名目标再校**（`experiments/pilot_investigation/top_pilot_pull.py` 断点续拉）；否则 **2×2 分项全亚阈 → kill**（签名轴榨干，仪器轨关闭归档，非加旋钮、非转 beam——Level 2 时间不可行）；**2×2 有显著且非中间带 → 记录+会师裁决**（不直升 Level 2，时间冻结）

## ③ Layer 2 斜率校验 2×2（探针 live Δ × retreat 仪器 Δ）

| | 仪器 Δ 显著（≥3×σ_Δ） | 仪器 Δ 不显著（<3×σ_Δ） |
|---|---|---|
| **live Δ 显著**（≥15pp） | 斜率方向确认，仪器可排序 | 仪器**漏 retreat 轴** → 警告 |
| **live Δ 不显著**（<15pp） | 仪器**高估** → 警告 | 双轴 no-op：**无斜率信息**，retreat_pivot 判死（与 first-pilot −0.50pp 一致） |

**预期管理：最可能落右下格。斜率本 campaign 大概率悬而未决 → 探针终审是默认分支。σ_Δ≈1.4pp（n=2500，√2 修正后），门槛 3×σ_Δ≈4.2pp。（08-13 13:30 端点约定：「≥ 归行动/显著侧」三闸统一，与本表 ≥ 一致。）**

## ④ K2 + dying_674 翻牌三条件

- 候选重排（retreat_pivot / nrg_bench / dying_674 过仪器）：**全亚阈（Δ < 3×σ_Δ）→ closure 不提交；有超阈（Δ ≥ 3×σ_Δ，端点归行动侧）→ 零下行 final bet**（证无害 + 正点估计，live 榜当裁判），**不是「终审」**——8/15 提交到截止只攒 ~40 局（σ≈8pp），<5pp 效应判不出，别拿噪声当结论。（08-13 13:30 端点约定：「≥ 归行动/显著侧」，与 ③ 表、K0 的 ≥50% 一致；候选集「全 <」与「有 ≥」互斥且穷尽，无第三态。）
- dying_674 翻牌**仅当三条全满足**：探针判 flat/NO-GO + 当日额度余 ≥1 + 用户明确点头。执行照 `experiments/pilot_investigation/retreat_probe_plan.md` 铁律：grep 三 flag 态 → pack.sh 打包 → 净环境解包 import 冒烟两座位真执行 → deck.csv 硬断言 == `dsh._baseline_deck()` → 提交，ledger 记「live 翻牌，非闸过候选」。

## ⑤ #132 管线命令（探针判读）

```bash
/opt/homebrew/bin/kaggle competitions submissions pokemon-tcg-ai-battle   # 瞬读分（不记账）
# Kaggle API list_submission_episodes(55468450) 直读累计局数；<35 → 接力 8/16 晚
# 拉 replay：experiments/live_loss_pull.py 或 pilot_investigation/top_pilot_pull.py（5s 限速）
/opt/homebrew/bin/python3 experiments/pilot_investigation/top_pilot_analyze.py --source ours   # live WR
```

## ⑥ 残差重点腿与悬崖澄清（live 配比加权判读背景）

- **残差最浓三腿**（pilot 缺口的 26.8pp 主要住这）：Dragapult live 0/3 vs equal-pilot 0.973、Grimmsnarl 1/3 vs 0.949、Archaludon 1/3 vs 0.887。校准/判读优先看这三腿。
- **Cornerstone 悬崖 = equal-pilot artifact**：equal-pilot 0.352 是 config A 自驾 Cornerstone 的产物，live 实测 4-0。**仪器不要试图复现该悬崖。**
- **live 池实测配比**（n=41 去镜像，`experiments/runs/live_pool_mix.json`）：Alakazam 26.8% / Lucario 17.1% / Crustle 17.1% / Cornerstone 9.8% / Grimmsnarl 9.8% / Archaludon 9.8% / Dragapult 7.3% / other 2.4%。「80% Grimmsnarl」轶闻已证伪。
- 缺口分解：36.4pp = 权重错配 9.6pp（other 19.7%→2.4% 主因）+ pilot 残差 26.8pp。
