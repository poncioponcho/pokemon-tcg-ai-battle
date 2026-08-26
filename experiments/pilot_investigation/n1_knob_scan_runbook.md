# N1 旋钮可达区间扫描 runbook（冻结扫描协议 2026-08-13）

> **口径唯一权威** = `experiments/pilot_investigation/signature_caliber_spec.md`（冻结 2026-08-13）。
> 本 runbook 只冻「扫什么、怎么判」（§1–§4、§6），**harness 调用 = §5 占位**，advisor N0 落地后回填并回链 spec。
> 被测对象 = **签名对手变体**（旋钮化对手模型，非 config A）；量测**读对手侧**决策（spec §3.2）；
> 目标 = spec §2 真人带（R2 1.06–2.07/局、E1 6.2–10.9%）。旧数字（1.5-2.1、0.42/2.14、6-11% 旧称）已作废。

---

## §0 输入 / 产物 / 预算

- 输入：advisor N0 双实例 harness（§5 占位）+ `experiments/arena_pool/meta/*.csv` 8 个 meta 牌组
- 产物：`experiments/runs/n1_knob_scan.json` + §4 判读表（stdout + 落盘）
- 预算：11 格 × 8 腿 × 400 局 ≈ 3.5 万局，3 workers 约 15–20 分钟（merge-gate 实测速率外推）

## §1 扫描网格（frozen）

**轴 R 旋钮（retreat）**：③ prize 保护范围 × ⑤ KO 射程 buffer，6 格：

| 格 id | ③ prize 范围 | ⑤ buffer |
|---|---|---|
| R-00 | 3奖身 only（=baseline 地板） | 0（=baseline） |
| R-01 | 3奖身 | +1 |
| R-02 | 3奖身 | +2 |
| R-10 | 2奖身+ | 0 |
| R-11 | 2奖身+ | +1 |
| R-12 | 2奖身+ | +2 |

**轴 E 旋钮（nrg active 灌注罚分）**，5 格：

| 格 id | 罚分 |
|---|---|
| E-0 | 0（=baseline 地板） |
| E-1 | −200 |
| E-2 | −400 |
| E-3 | −800 |
| E-4 | −1600 |

- **单轴扫描**：扫 R 时 E 旋钮钉 baseline，反之亦然。两轴近似可分的假设由 N2 的 both 格验证（§6）。
- 每格每腿 **n ≥ 400**；引擎不可播种 → **同批交错**跑各格（#111 纪律），抵消批内漂移。
- 每格**两轴都测**：主轴判读、副轴监控交叉干扰（retreat 旋钮可能经局长改变 E1 分母）。

## §2 量测口径（frozen，逐字照 spec §3）

- **R2** = post-KO 自愿换位/局 = `sw8_vol − sw8_vol_pre`（type8 自愿子集，剔 Boss gust 受害；5→4 不算）。
- **E1** = pre_act%（首 KO/丢奖界前 type11 落 active；**分母含 serial 未定位事件**）。
- obs 侧若全量可定位：分母可比性**二选一**（折算 replay 口径 / 全量口径+重导真人目标值），不许静默混用（spec §3.2）。
- 禁等价简化；pre 界用事件界不用回合数近似。

## §3 判读模板（frozen）—— 含 K0「多数腿」钉死

**腿权重**（live 配比 `experiments/runs/live_pool_mix.json`，对 8 meta 腿归一化；Gardevoir live 权重≈0 不计，「other」2.4% 无法被对手驾驶，归一化剔除）：

| 腿 | 权重 | 属性 |
|---|---|---|
| Alakazam | 27.4% | 大腿（≥15%） |
| Lucario | 17.5% | 大腿 |
| Crustle | 17.5% | 大腿 |
| Cornerstone | 10.0% | 普通（悬崖=equal-pilot artifact，live 4-0，**仪器不复现悬崖**） |
| Grimmsnarl | 10.0% | **残差浓腿**（live 1/3） |
| Archaludon | 10.0% | **残差浓腿**（live 1/3） |
| Dragapult | 7.5% | **残差浓腿**（live 0/3） |

**腿 pass** = 该腿 R2 可达区间**上限 ≥1.5/局**（= spec R2 真人带 1.06–2.07 的带内中高位；
判读用区间上限不用点估计，防旋钮非单调——若扫描显示非单调按实测区间报）。

**K0 判定（互斥三分支，08-13 13:30 修正——旧版 KILL 与 FLAG 在「加权 ≥50% 且大腿也 fail」时撞车、PASS 与 FLAG 重叠，已钉优先级）：**
- **KILL（无条件优先）**：加权失败份额（fail 腿权重和）**≥50%**（端点 50% 归 KILL）→ 签名不可达 → 仪器轨关闭、归档、退守成（照 A 轨计划，非加旋钮、非转 beam）。**无论 fail 集里有无大腿/残差腿，KILL 优先于 FLAG。**
- **FLAG（仅当加权 <50%）**：加权失败 **<50%** 且（大腿 ≥15% 任一 fail，或残差浓三腿任一 fail）→ 不 kill、进 N2 但记限制：对手在这些腿 under-retreat → 模拟腿偏易 → 仪器 WR 在该腿**方向性偏高**；N3 必须并报「全池校准 + 剔 fail 腿校准」两行，K1/K2 判读带此偏差注记。
- **PASS**：加权 <50% 且无 FLAG 条件 → 进 N2；FLAG 状态随产物落盘。

**K0 pass → N2 旋钮取值**：落带格中 R2≈1.5、E1 落 6.2–10.9% 的组合，组 2×2 四格（retreat-only / nrg-only / both / neither）。

## §4 报告模板（frozen）

逐行（腿×格）：

| leg | live权重 | 格id | 旋钮值 | n | R2±SE | E1±SE | 落带 | 腿判定 | flag |
|---|---|---|---|---|---|---|---|---|---|

JSON schema（key 名冻结）：`{ts, grid, per_cell: [{leg, live_w, cell, knobs, n, r2, r2_se, e1, e1_se}], per_leg: [{leg, live_w, r2_reach:[lo,hi], e1_reach:[lo,hi], leg_pass, flag}], k0: {weighted_fail_share, verdict, flagged_legs}}`

## §5 harness 调用（plug-in 占位，advisor N0 落地后回填）

- 对手变体模块路径 / 旋钮常量名 / 覆写方式：【占位】
- 双实例 harness 入口 / 对手侧决策日志抽取：【占位——须回链 spec §3.2 映射实现】
- 跑批命令 / 输出落盘：【占位】

## §6 已知假设与边界

- 单轴扫描假设 R/E 两轴近似可分；交叉项由 N2 both 格验证，本扫描不下交互结论。
- 可达性 ≠ 校准：N1 只证「对手能演出真人签名率」，WR 校准是 N3 的事（目标 0.476±5pp，软锚 0.744 见 cheat sheet ①）。
- Cornerstone 悬崖是 equal-pilot artifact（live 4-0），扫描若在该腿见异常低 WR 不追修。
- 本 runbook 修订 = 新版本 + ledger + cheat sheet 引用更新三件套（同 spec §4-3）。
