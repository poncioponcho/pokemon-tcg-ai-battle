# Pokemon TCG AI Battle Challenge — 项目交接文档

> 版本：2026-08-09 17:10 CST（第二版，替代 08:30 版；旧版存档 `HANDOFF.md.bak-2026-08-09`）
> 编写目的：agent 切换交接
> 工作区：`/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge`
> ⚠️ Desktop 下存在一个带前导空格的同名目录 ` Pokemon TCG AI Battle Challenge`，是 symlink，操作一律用真实路径。

---

# 🏁 08-15 执行覆盖（优先于下方 08-14 全节）

- **08-17 20:12 收官记账推迟：决赛期仍在漂移，#135 保持预留，观测哨不关停。**
  8/17 晚例行采样（checklist "07:59 之后"§2 每日口径）：双 exact-v22 在截止后**继续获得新
  episode 且分数全天波动**——slot2 `55547740` 820.3→834.0→834.7→834.5、成熟件
  `55539446` 833.7→844.6→829.7。今日 11:37 lb_watch 据 03:35Z 的 QUIET_4H（双件停排
  4.69/5.69h、连续 4 样本极差 0）报的 "SETTLED/CLOSEOUT" 已被 15:35 新 episode **证伪**
  ——4h 静默只是 lull，匹配池未关，"截止后约两周 episodes 才定榜"的机制核查成立。按
  checklist §5（8/17 晚、8/18 晨均不得称最终分），最终成绩 ledger（#135）与观测哨
  disable（f6bd5dac）推迟到约两周决赛阶段结束（~8/31）且榜单明确停止变化后。
  20:07 样本：团队 **rank 752/6892 @834.5**（12:05Z 快照）；slot2 59 场 32-27
  （WR 0.5424、对手均分 815.46、校正 μ*854.81）、成熟件 57 场 31-26（WR 0.5439、
  对手均分 831.21、校正 μ*864.63），双件同 SHA 一致（WR 差 0.15pp，远小于 σ≈6.5pp）。
  ⚠️ 旧任务提示词里的 config A v2(55451759)/v1(55431232)、~647、1.4× 均系 8/13 前旧口径
  （config A 两件 8/13 已出 latest-2 不再更新）；最终以双 v22 实际结算为准，若现值结算
  跃迁约 833.7/467.9≈1.78×——但现值非最终分，不记账。详见 ledger #191。

- **08-16 20:52 封盘监视已启动，提交面保持冻结。** 新v22 ref `55547740` 已在4小时
  内从600爬到816.5，33局17-16；成熟ref `55539446` 为837.1，42局24-18。20:52
  smoke确认两件均COMPLETE、latest-2构成正确、零错误。只读监视器
  `scripts/final_predeadline_watch.py` 已以PID 95869/session 25575运行，固定在22:30、
  00:30、02:30、05:30采集状态/latest-2/逐局数据到
  `experiments/runs/final_predeadline_watch/`，结束后自动退出。脚本没有提交端点；任何
  波动只记录，只有确认ERROR/runtime失效才人工评估最后一发。见ledger #190/C-023。

- **08-16 16:25 最终槽位已切为双 exact-v22：`{55547740新件, 55539446成熟件}`，
  两件均 COMPLETE。** 16:00 新数据把分叉拉开：成熟v22 38局22-16（新增约7-2）、
  对手均分826.96、校正`mu*=891.83`；Roman 37局19-18（新增2-6）、对手均分757.07、
  校正`mu*=768.24`且对Grim累计4-8。用户明确批准用第二个v22独立实例替换Roman槽。
  仅上传冻结archive SHA=`599e19ae…b4c8bfcf`一发，返回ref `55547740`，validation
  COMPLETE、初始600.0；回读latest-2为`{55547740:600.0,55539446:841.5}`，成熟件
  地板完整保留。**禁止第二次成功提交**；余下一发只允许ERROR/失效时同SHA恢复。
  本条覆盖下方10:40的KEEP Roman裁决。见
  `reports/20260816_exact_v22_slot2_duplicate_submission.md`、ledger #189。

- **08-16 10:40 最终联合裁决：KEEP `{public Alakazam 55539395, exact-v22
  55539446}`，不执行 M Sato 回退、不再提交。** 同一 02:34Z 全榜快照中团队
  802.8/rank924，约 top-10% 线 839.3（差36.5）；Roman/Jazivxt件29局17-12、对手均分
  754.88、校正 `mu*=822.00`，v22为29局15-14、对手均分812.22、校正
  `mu*=829.58`，两者无法区分但具牌组互补；M Sato仅21局9-12、校正
  `mu*=677.43`，已排除回退。29场Roman回放显示vs Alakazam 4-1、Lucario 4-0、
  Grim 3-6，零runtime故障。源码审计确认策略主体实际为公开
  `jazivxt/codex-sol-eclipse-alakazam`，Roman仅公开复包/历史表现来源，我方只补
  `import sys`；官方规则§3.6(b-c)对本比赛公开notebook赋予OSI商业可用的deemed
  license，故可作为开源组件保留，但writeup必须双重署名且不得宣称策略或LB950原创。
  本条已被上方16:25双v22裁决覆盖；其合规与署名结论仍有效。详见
  `reports/20260816_final_slot_compliance_and_live_readout.md` 与
  `reports/20260816_public_code_attribution_ledger.md`。

- **08-16 08:31 当前收官槽位=`{Roman公开Alakazam彩票 55539395,
  exact-v22 55539446}`，两件均 COMPLETE。** Roman件来自208票公开 notebook
  `romanrozen/strong-start-baseline-agent-v10-lb-950`，是完整 Alakazam Courage v22
  源码而非回放模仿；只补了搜索异常回退路径缺失的 `import sys`。归档两次确定性打包
  SHA=`14dfb766…a53fc`，60卡/双入口/exact-archive均通过且零fault。它被Grim硬克：
  历史原件对exact-v22 n=128为16–112，本轮修复件n=32为3–28–1；但直接对当前M Sato
  v5小样本17–15，且公开件具有直接`LB950+`上限记录，故按用户“上限优先彩票”授权提交。
  随后原字节精确重交v22归档SHA=`599e19ae…b4c8bfcf`恢复托底。两件初始均600，短期榜分
  下落不作为裁决；该回退分支已被上方10:40同快照联合裁决关闭，今日余2发只保留为
  ERROR/失效应急恢复额度，07:30后不再改槽。

- **高分Grim调研已 completed-negative。** 157票公开Grim notebook只是exact-v22同牌表、
  同核心加旧wrapper（旧live约628）；近期Raihan refs `55494171/55510944`并非同牌表，
  真正同牌表专家为历史refs `55177269/55202823`。135场去重专家回放产生的残差模仿
  两轮均是n=32尖峰、n=128回落；最佳v14镜像累计约196–188（51.04%），对35场胡地
  replay安全回退2856次调用0 override，但同批Lucario/Crustle分别70–58/71–57，明显
  低于v22对照86–42/89–39。所有Grim-X因此KILL，未为了提交而降低闸。

- **22:59 用户已把收官策略切换为“exact-v22 托底 + 高上限彩票”，覆盖本节下方
  “8/16 只重交 v22”旧句。** M Sato 胡地 ref `55198468` 的 455 场正确口径为
  258–197、对手均分1032.84、隐含实力约1091.95；对 live Grim 65–65/130。
  胡地不是磨牌主胜法：258胜中253场靠奖品/清空Active，仅5场靠对手deck-out。
  冻结 v5 margin1 相对公开父策略对 exact-v22 从19.53%提升至独立确认32.81%，
  但仍未证明强于v22；定位仅为第二槽彩票。工程/H2H累计544局零fault，确定性归档
  SHA=`83372cfe…993a9`，解包归档对v22 13–19/32且零fault。用户已明确授权完成闭环后
  上传 v5，并授权后续若长毛巨魔调研形成有潜力且过最小工程闸的彩票则果断提交获取
  live反馈；最终锁定必须恢复 `{exact-v22, 最强彩票}`。详见
  `reports/20260815_msato_alakazam_lottery_final.md` 与
  `reports/20260816_lottery_branch_runbook.md`。

- **Final Evaluation 网页端已核实：自动取 latest-2、无需手动勾选，截止后继续约两周
  episodes 才定榜。** “8/16只重交一次v22”的旧动作已被用户后续“高上限彩票”授权
  覆盖；机制事实不变。当前实际序列与唯一剩余回退链以本节第一条和C-022为准。
  详见 `reports/20260815_决赛机制核查_kimi.md` 与
  `reports/20260816_lottery_branch_runbook.md`。
- **路线 A 已于 18:48 在正式训练闸 `TRAINING_KILL`，C-014=`completed-negative`**。
  完整多步 PPO 赛前 NO-GO；唯一可装入窗口的是每局最多一次随机干预、exact-v22
  永久回退的 contextual-bandit pilot 已完成 36,432 局健康采集：四腿各9,108、零 fault、
  23,458 eligible、2.95局/s。正式 opponent-held-out cross-fit 仅 `+0.20pp`（闸为
  `+3pp`），仅2/4 folds同向，Alakazam最差 `−3.89pp`，故不运行 live canary、四腿
  screen、n256、materialize 或提交。详见
  `reports/20260815_routeA_training_kill.md`、ledger #180、任务 C-014。8/16 唯一一发
  已确定为精确重交 v22；仍禁止同日先重交 v22 再交实验件。
- **赛后新方向已完成只读可行性核算。** Router 正腿主要集中于 turn>=9、gap=0 的
  same-type ability/attach 目标选择，只形成赛后 R1 预注册；不可翻案。matchup marker
  用旧ref设计、新ref32场盲验，在turn2达到20/32覆盖且20/20正确，A/L合计12/12；
  novel-deck子集仍10/18、10/10。赛后推荐高精度可弃权 router：只对A/L命中后锁存，
  unknown/conflict永远exact-v22。见 ledger #181 与两份 19:22 报告。
- **Q1 已受控实验证实为 `best-of-latest-2`**，不是下方 08-14 曾写的 latest-only。
  08:46 精确重交同一个 v22 包后，新 ref `55516725` 从 600.0→498.8→702.8，
  旧 ref `55499962` 保持 823.2，三次新鲜 leaderboard 均显示团队 823.2，且榜行日期
  已切到新件，排除“未刷新”。当前 latest-2=`{55516725,55499962}`，两件都是相同
  archive SHA `599e19ae…b4c8bfcf`；recovery 已出槽。证据见
  `reports/20260815_v22_exact_resubmit_Q1_observation.md`、ledger #167/#170。10:10 的迟到
  +84 分钟封口仍一致：新件 796.9、旧件 829.4、团队 829.4。
- **当前最强 baseline/incumbent = exact Grim v22**，不再是 retreat。
  后续任何候选必须以 `candidates/grim_v22_final/` 作主 H2H；`candidate_h2h.py` 的
  省略 `--opponent` 默认锁已同步到 exact v22（main `d80d33c5…`、deck `92b92bac…`、
  完整运行树 `0319fee3…ecc`）。
  冻结的 `submission_baseline/` 旧 retreat 目录未改，只是不再作为默认晋级闸。
- 用户授权区别于 replay BCRL 的 v22 自生成 on-policy 探索；第一轮保守残差 ES 已完成阴性。
  40-genome screen 唯一幸存者在 exact-v22 独立 n=256 为 133-123（51.95%），低于
  55% 预注册线，`winner=null`，不 materialize、不提交。见 ledger #168 与
  `reports/20260815_v22_onpolicy_residual_rl.md`。
- **触发级 follow-up 也已阴性封口**。2×2 四臂已修为按 candidate seat 分层；正式
  四腿 144 局每臂 36、seat 18/18、零 fault，但上述两个 guard 都是 0 次真实触发。
  单侧 95% 触发率上界 2.06%，远低于原 544 局要凑 apply/skip 各 30 次所需的
  11.03%；verdict=`INSUFFICIENT_OPPORTUNITIES`，不跑 544、不降闸、不生成候选。
  见 ledger #169 与 `reports/20260815_v22_guard_factorial_feasibility.md`。
- **测量仪器再修一处**：候选 runner 现在每局显式发送 `select=None`/deck reset，避免
  v22 的 `_HISTORY`/`StrategicMemory` 跨局泄漏；新报告必须带
  `episode_reset=select-none-before-every-game-v1`。此前报告不追溯改写。
- **live 校准与高暴露数值残差也已封口为阴性**。固定 10:45 快照共 82 个 PUBLIC
  replay，exact-v22 顺序重放 8,333 次 ACTIVE call、0 mismatch；两个目标 guard
  在线上仍为 0/82，单侧 95% 触发率上界 3.587%，不重开 C-010。乘法参数不是局部
  扰动（资源/手贴 ±2.5% 已让 57–70/82、58–68/82 局分叉）；分样本加性筛选虽让
  resource+25 与 attachment+50 通过行为暴露盲验，但四腿 W/L 相对 incumbent 分别
  为 −1.28pp/−2.68pp，均未进 n=256，winner=null。见 ledger #171 与
  reports/20260815_live_calibration_and_dense_residual.md。
- **剩余 live 决策面与完整结构删减也已封口**。82 场中相对 fallback 仅 44/8,251
  次选择被 manual/hierarchy 语义改写，job 级 `control:*@turn<=4` 无跨 ref 复现候选。
  预注册的 manual×hierarchy 2×2 四腿每臂144局、零 fault；hierarchy-only、manual-only、
  fallback-only 相对 exact 加权分别 −13.77/−3.46/−7.25pp，三臂 v22 主腿均低于53%，
  不进 n256。live 的早期 Dawn 3-8 异常也只在 penalty≥300 时改动2–3/82场，且替代
  全为 early Boss，行为闸 KILL。见 ledger #173/#174 与
  `reports/20260815_v22_remaining_surface_audit.md`。
- **native RNG 术语已纠正**：本地 ABI 没有 shuffle seed setter，seed0 只控制
  Python 侧随机。后续只称 blocked independent trial；ABBA/BAAB 仅平衡座位和粗
  时间块，禁止再称 paired/CRN。
- **8/16 默认动作**：精确重交测量最充分的 v22。残差 ES 的 screen 尖峰不是
  challenger；不得连续提交两个未过闸实验件顶掉 v22 保护槽。截止仍为
  8/17 07:59 CST。

# 🏁 最新状态（2026-08-14 执行覆盖）— 先读本节

## 用户硬约束优先级（2026-08-14）

比赛还剩三天，交付指标是**每天至少一次真实 Kaggle 提交并取得可见状态/分数反馈**。
旧的“提交冻结、WR≤0.62 自动归档、只写日报”收兵 doctrine 已失效；本地闸只能证明
无害，不能替代 live 测量。认知层仍使用 `WR>0.62` 作为“可宣称显著收益”的阈值，
但行动层必须按下面已经亲验的平台机制执行。

### 已亲验的平台机制（08-14 11:05，覆盖全文所有 last-2 锚叙事）

- **`max(last-2)` 假设已证伪。** 官方完整 leaderboard 02:58 UTC 的本队行是
  `score=600.1, LastSubmissionDate=02:55:41`，精确对应最新 Router；当时上一件 Grim
  提交页为 709.1，未形成榜分保护。最近两件只是继续匹配的活跃集，团队榜当前关联
  最新有效提交。以后每次提交都视为会覆盖当前团队榜件。
- 每天默认只发 **1 个主候选**，当天早段发射；第 2 发只用于 ERROR 修复或有证据的
  恢复。提交前必须只读打印 `team-submissions` 和完整 leaderboard 本队行。
- 当前活跃集：**55496363** retreat 精确恢复件（最新，首分 600.0，初始 2 局 1-1）
  + **55496233** Visible Router V3（次新，首分 600.0，初始 4 局 3-1）。旧 55468450
  的 700.3 是 **8/13 提交后的历史 public-score 快照**，不是 8/14 当日分数，
  已出活跃集；Grim 55495955 也已被恢复件顶出。每个 submission 都是独立
  matchmaking/episode pool，不能把 700.3、607.3 或恢复件分数当成同一个 bot 的
  时间序列。
- 8/14 14:49 新提交 `grim_v22_final`，ref **55499962**，状态 `PENDING`；结算前
  不宣称分数改进。

### 唯一 baseline 锁（用户 08-14 最新裁决）

- **baseline = 目前最强真实提交的纯规则 retreat**，不是 config A、根目录当前代码、
  Router/Grim 公共候选，也不是任何 notebook 标题中的历史分。live ref 用恢复件
  `55496363`；源码锁 `main=411d9dff4c146e3bf5b8cbbb935f6c53c84742d670d41930d8315926a61ba480`，
  `deck=2a541d7bf3d9e6b36037123f53f4dfef6348223f79fd27095dafc602a5357c19`，归档
  `submission_baseline/submission.tar.gz`。
- 所有新策略都是 challenger。先用官方本地引擎、同牌组口径、交替座位，**同批直接
  对 retreat baseline**；小样本领先或历史公共分不构成替换证据。未明确胜出时，
  当天为满足真实提交硬约束就重交 baseline，不拿榜件做无保护实验。
- `scripts/candidate_h2h.py` 省略 `--opponent` 时已强制使用并校验上述 baseline 哈希。
  config A 仅可用于历史消融，禁止再出现在候选晋级主闸。

**为何不是峰值 859.1 的 config A：** `55451759` 的 859.1 出现在仅 4 局、恰好
4-0 的瞬态；到 26 局已是 11-15，最终 24-30（WR 0.4444）。同构的两次 config A
`55431232 + 55451759` 合计 50-58（WR 0.4630），retreat `55468450` 为 27-21
（WR 0.5625）。按座位拆分也同向：retreat seat0/seat1 = 0.607/0.500，config A
合并 = 0.516/0.391；当前 leaderboard 可匹配对手均分 689.6 vs config-v2 701.1，
没有足以解释约 10pp 差距的明显软池。单侧 Fisher p=0.165，故这是**截止期的
期望值裁决**，不是“pivot 真效应已显著”的认知结论。这里的 public score 峰值和
episodes 都来自独立 submission/matchmaking 池，不能把 859.1、700.3 或恢复件分数
拼成同一个 bot 的时间轨迹。恢复件 `55496363` 初始 5-1
只作一致性旁证，不计入主证据。峰值分只记轨迹，不用于 baseline 选择。

### 08-14 实际发射与工程结果

- Grimmsnarl v1：ref **55495955**，`COMPLETE`；首分 600.0，曾更新到 709.1；
  archive SHA `307bfc6bb6abcf562cdd5c1912cae13d3934af6845e79083de6a318e381d4f5b`。
- Visible Router V3：ref **55496233**，`COMPLETE`，首分 600.0；精确源码绑定的旧池
  844.4 未复现，证明历史公共分只可作候选先验。最终 deterministic archive SHA
  `860f26a614899ae52f1c89cb7b0a15737c209feb2321702ec4866a1f4f3b2590`。
- 机制核验后恢复：ref **55496363**，重交 55468450 的精确 retreat 原包；archive SHA
  `a199c9c516d05ca57bd31fe55096c2e54fc8fd60382c331c1ae4b95c88763b4f`。
- 首包 ref 55495594 因遗漏官方 `cg/` 为 ERROR；交付工具已默认随包，并新增候选 cwd、
  Kaggle last-callable 双入口、确定性 gzip 和候选目录 H2H 闸。

候选交付统一走 `scripts/candidate_delivery.py`；不得用根目录 `submit.py` 的 freshness
校验替换独立候选。跨策略候选优先于旧 Lucario flag 翻牌；后者只有在候选失败且额度
仍有余时才进入回滚队列。

### 测量纪律增补（08-14 14:13，覆盖旧多候选 H2H 的可信度口径）

- 旧 `candidate_h2h.py` 在双方都使用顶层 `policies` 包时会共享 `sys.modules` 和
  policy 状态；这类旧腿默认失效。runner 已改为每个 `CandidateAgent` 私有模块缓存，
  新报告必须带 `module_isolation`、runner/main/deck SHA 和 native-seed 作用域。
- `zero fault` 不能证明提交件完整。v22/v28 曾因净包遗漏 `EN_Card_Data.csv`，异常被
  组合 policy 吞掉后静默退化；提交前必须从最终 tar 解包、实读依赖资产，再跑双入口、
  self-play 与跨牌组腿。完整纪律和旧结果可用边界见
  `reports/20260814_grim_v22_delivery.md` 的“测量纪律”节。
- 当前唯一 challenger 是 Grim+v22，archive SHA
  `599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`。
  修复后 Alakazam exact n=64 为 51-13；v29 经隔离重审后，在已覆盖 70.7% live
  权重上仅约 +0.27pp，直接 H2H 合并 208-175（54.3%，Wilson 区间跨 50%），
  不足以用复杂路由覆盖 v22。
- 8/16～冻结的冲突裁决已写死：两件都 n≥20 且 WR 差≥3pp 取高者；否则优先局数
  更多者，再比 Wilson 下界，仍同档退回 retreat。候选集合只允许 v22/retreat，
  禁止末班车全新变体。

---

# 🏁 历史状态（2026-08-13 06:58 CST 修订）— 收兵期 + 探针在飞

> §1–§6 为 08-09 旧版内容，大量已被 08-10~08-12 进展取代（v24.8→F1→baseline1084 战略切换）。**历史细节以 `experiments/ledger.jsonl` 为准**。

## 现役盘面（last-2 提交槽位）
| 件 | sha | Kaggle ref | 内容 |
|---|---|---|---|
| **retreat_pivot 探针（08-13 06:54 交）** | `411d9dff` | 55468450 | config A + 防守性 prize-denial pivot 单 flag ON（live 探针，**非闸过候选**，ledger #136）。**判读完（08-15 20:07，ledger id183）：48 局=47 public+1 validation，public 26-21 / live WR 0.5532，Δ vs config A 0.476 = +7.7pp < 15pp → flat/小动，retroactive NO-GO 归档（统计功效不足、非证伪，n=47 σ≈7.3pp）；config A v2 仍为落袋锚** |
| **config A v2（锚）** | `459cf97` | 55451759 | 原 config A 重交件；瞬读 606.3 不记账 |
| ~~config A v1~~（已出 last-2） | `459cf97` | 55431232 | 08-13 06:54 被探针顶出；瞬读 650.3 不记账 |

- **截止**：官方 8/16 23:59 UTC = 本地 **8/17 07:59**。
- **铁律**：瞬读分不记账（ledger #98）；结算漂移 ±400 分/1-2 天；last-2 外旧发自动顶出。

## 收兵决议（08-12 晨定谳，下午增补口径）
- **全 meta 无决策空间（first-pilot 口径）**：9 腿中唯二有 headroom 的腿均 STRUCTURAL——Alakazam 0.830（属性克制+奖品地图不对称+无第二攻击线，凶手 743 占 98%）、Crustle 0.799（345 墙 setup 竞速 variance，无复发劣手）。其余 7 腿 0.92–0.99 无 headroom 定义。（ledger #126-127）
- **闸保真度 caveat（08-12 下午新增）**：本 HANDOFF 与 ledger 中一切本地腿 WR 均系 `builtin 'first'` 驾驶 meta 牌的 first-pilot 口径，**系统性高估 live**；live 真人池口径以 #132 为准（WR 0.476 / ~647 分 / 42 局平线）。真人级闸 `experiments/realpilot_gate.py` 已跑完（n=2000×9 腿，invalid=0）：**8/9 腿优势、加权 0.840，唯一劣势腿 Cornerstone 0.3515（占比 1.1%，即 #115 已知牌组悬崖再现，非新靶）**——牌组层无藏住缺口，live 0.476 缺口纯在 pilot 层。注意它是 **real-deck/equal-pilot 闸**（两侧均 config A policy），非 real-pilot 闸：全均势 ≠ live 回到 0.5。判读见 `reports/2026-08-12_收口判读.md`，产物 `experiments/runs/realpilot_gate.json`。（08-13 上午精化：0.840→0.476 的 36.4pp 缺口经 live 配比重加权分解为**权重错配 9.6pp + pilot 残差 26.8pp**——arena_pool 配比 ≠ live 实测配比（other 19.7% vs 2.4% 是主因），live 配比加权后 equal-pilot=0.744（**软锚 ±3-5pp**，n=41 配比推得；K1 命中仍按 0.476±5pp 宽松带，软锚不做硬卡），产物 `experiments/runs/live_pool_mix.json`。）
- **提交冻结不变**：除非闸认证 > config A 现态 **+2.2pp** 且用户点头。dying_674（+0.43pp）、hybrid 牌组搜索（收敛回 config A）均已按此闸 NO-GO。
- **收兵范围收窄→pilot 调查 CLOSED（08-12 17:40 OPEN → 20:41 收线）**：①盲调牌组/规则收兵成立（闸加权 0.840，牌组层无油水）；②pilot 层调查已关——68 局 top-3 pilot replay + 41 局我方 live replay 参数化 diff（`experiments/pilot_investigation/`），实证两条真行为差：pre-KO 喂 active 能量 28.2% vs 6-11%、付费 retreat 0.42/局 vs 1.5-2.1/局；建成两候选过闸：**nrg_bench −0.09pp / retreat_pivot −0.50pp，均 NO-GO**（regression 全过、invalid 0，只证无害）。**核心方法论结论「闸灵敏度天花板」：first-pilot 闸对 pilot 质量改进已失灵——本地加权 0.92 贴顶，live 缺口全在 first-pilot 不会做的事上，闸能证无害、证不了有益**；纯规则工具箱在 pilot 层够不着，剩余差距在 pilot 能力层（NN/search）。live 探针因统计功效不足未执行（n≈42-72 时 σ≈7.7pp，<15pp 跳动检不出），载具留 `pilot_investigation/retreat_probe_plan.md`（BACKUP 未授权不执行）。raw 337MB 已清。
- **settle 监控到 8/17 照旧**（观测哨被动）；pilot 调查已于 08-12 晚收线，盘面全被动，收官链路（9a7c7fda / #135 / f6bd5dac / 530a9aba）未受任何污染。
- **A 轨=签名轴对手模型仪器 → CLOSED @ N1/K0=KILL（08-13 15:36，唯一 in-window 主动轨终结）**：**K0 判读：加权 fail 份额 0.649 ≥ 0.50 → KILL（互斥三分支无条件优先）**。N0 由 Kimi 自建（用户指派，advisor 零交付）：`experiments/signature_opponent/`（sig_opp 变体+自观测 watcher + n1_scan 双实例 harness，smoke 三验证点全过：BASE R2=0.967 落 config A 带、BASE usWR=0.667≈realpilot_gate 0.6565、E 轴旋钮强力）。N1 全量 7 腿×11 格×n=400=30800 局零 fault（产物 `experiments/runs/n1_knob_scan.json`）。**R2 可达上限 4 腿离线（pass=≥1.5）：Alakazam 1.060(w.274) / Crustle 1.385(.175，摆动腿、离线 2.3σ) / Cornerstone 0.690(.100) / Archaludon 0.975(.100)**；仅 Lucario 1.837 / Grimmsnarl 1.710 / Dragapult 1.745 过线。E1 带（6.2-10.9%）更惨：仅 Grimmsnarl 一腿可达（Alakazam E-4=11.8% 贴带沿）。**结构性结论：双旋钮签名对手无法在多数 meta 池 impersonate 真人 pilot——config A 支配的对局（usWR 0.88-0.97 腿）太短，pivot 五条件无机会积累真人撤退率；仪器工作正常，失败在 matchup 结构，正是 K0 设计要抓的天花板。** 即便最宽松剔除 Crustle 也仍 FLAG（Alakazam 大腿+Archaludon 残差腿），且 N2 前提（R2≈1.5 且 E1 落带格）在 5/7 腿无格可选——KILL 实质正确非仅字面。N2/N3/N4 不执行，8/15 12:00 全局时间 kill 提前达成。仪器归档保留（`experiments/signature_opponent/` + 预写件三件套 `experiments/pilot_investigation/` 不删，下一场可复用）；全貌 ledger `n0_built_and_n1_k0_kill`，原设计见 ledger `deep_probe_closure_signature_axis_instrument_track` + 三件套。
- **下一场方向=RL 四步路线（08-13 17:10 战略判读闭环，advisor 共识+Kimi 裁决）**：用户点破「647 vs 全场地板 1000+ = 结构能力差非池子时机」**成立**。**三层地基诊断**：①数据锚 OK（`inference/dataset/manifest.csv` 6873 条：92% rank≤1500、42% rank≤500 真人 replay，含 rank-20 @kdcyberdude 1079.7）；②**模仿保真塌=真瓶颈**：纯 BC（winner-only，与奖励无关）克隆 top-500 真人决策 canary 0.5332-0.5498（advisor 原报 0.263 无出处，08-13 核实更正）/ nn_first h2h 0.4024 vs 规则（gate3_h384d1.log）——Level 3 预言的「保真崩塌+covariate shift」被实证；③奖励函数不最优但仅三阶：稀疏终局 ±1（`selfplay_harvest.py:135/196`）+ batch-mean 冒充 advantage（`train_v2.py:334-336`）=「过滤式 BC」，且 AWR 仍把 0.40 推到 0.53-0.54（+13pp，非瓶颈）。**rating 数学（仓库 08-10 分析）**：1000+ 需 ~62-65% WR，我们 47.6%→650，缺口 ~15pp；计分=纯胜率 ELO（非分差制，advisor 分差假设已否）。**牌组悬崖**：Lucario 35%@500s→1.2%@1000s，800+ Grimmsnarl 43-46%——牌组强度 pilot 依赖，equal-pilot 闸拆不开这层混杂。**下一场顺序**：①修模仿保真——**BC 保真解剖三探针已定谳（08-13 18:24 ledger `bc_fidelity_autopsy_phase12_verdict`）**：瓶颈=**模型类×特征表示**，非奖励/多模态/过拟合/训练预算。证据链：a) 多模态非约束——1.8M 决策帧状态哈希分组，LB 真人一致性 0.8754≈规则对照 0.8836，天花板≥0.73（中局）-0.87（全局），克隆现状 0.54 远在其下（`experiments/runs/multimodal_probe.json`）；b) train 0.5407=fixed-test 0.5410=canary 0.5498 零泛化差距=纯欠拟合（`experiments/runs/train_test_gap.log`）；c) 边际 epoch 价值 BC6 0.5207→AWR20 0.5332/0.5432 已入平台（+0.5-1pp/翻倍），从零 epoch1 即 0.4709 快速逼近——多 epoch 到不了 0.65；d) 本机 MPS 前向 1.9s/batch 慢 15-50×、60 epoch 探针三次被掐，本机长训练不可行实证，终审须云 GPU（`experiments/runs/long_train_probe.log`）。**路由=表示层（关系化卡牌特征/能量血量算术可见/序列记忆）→模型结构（选项结构化/牌组上下文嵌入）→云 GPU 200 epoch+特征消融终审**；distributional head 降为次要（多模态非主缺口）。里程碑改用 canary top1：现 0.5332，实测天花板 0.73-0.87→②奖励升级（PBRS 塑形/IQL-CQL，此时才二阶）→③online 环（self-play 数据回流迭代）→④搜索 bootstrap（top 选手用搜索零证据，纯假设；Kaggle 每步时限未测）。**本场 87h RL 无可交产物**，此路线全部为下一场/截止后工程。**live 非技术损失审计 CLOSED（08-13 17:12，advisor 扫描+Kimi 独立复核一致）**：42/42 replay `statuses=["DONE","DONE"]`，零 TIMEOUT/INVALID/ERROR——22 场败局全技术性失利，无基础设施失血；内容级缺陷由 #127 牌组硬断言+探针 sha 两验覆盖。advisor 提议的逐决策软失血深挖已拒（假设空间被全 DONE+#132 无复发劣手挤干）。
- **下一场执行手册=`experiments/bc_fidelity/NEXT_CAMPAIGN_RUNBOOK.md`（v2，08-13 19:30 C-0 终版，fresh session 先读它再读本文件）**：**C-0 裁决——日报 student 0.2633 系 08-08 CPU 冒烟报告（limit=30000、distill 1 epoch/5.45s）陈旧引用，已证伪**；真实云端全量蒸馏（08-09，8 epoch）student canary **0.5372**（本地复验精确一致，参数量断言过）、teacher 0.5494，**蒸馏仅 −1.2pp 健康**——原「−28.5pp 并列瓶颈」是测量 artifact，Track C 降级仅微调。里程碑重锚 student canary 0.5372，上限中局 0.7337（~19pp）。瓶颈双战场不变：①表示层×模型类（in-dist 0.54→0.73，Track A/B 云 GPU）②部署保真（0.54→实战 ~0.40，Track D；D0=LB student 从未跑 arena，现有 0.4024 等数字全来自 self-play 系 h384d1）。canary 治理新教训：refresh_rolling_canary 评测时会重写 live manifest（08-13 已非预期滚动一次，新旧 0/100 重叠），评测一律显式快照（`canary_snapshot_20260809_cloud.json` 为历史可比基准）。student 已 1,993,537≈2M 顶格（输入投影占 1.73M），宽度无余量，扩容=特征重设计并入 Track A。**D0 已 DONE（08-13 21:00 三格矩阵 n=2000）**：LB student 同环境 H2H +3.5pp vs v23_2_rules / −6.8pp vs first / −2.7pp vs random——in-dist canary 优势（0.5372 vs h384d1 跨分布 ~0.30）**不转化为部署优势**，部署保真瓶颈实体化；h384d1 自身同日复测 0.4024→0.734/0.3744→0.513 = **arena 环境漂移（宿主更正：根 main.py=v24.8/F1 系 sha 9efb8606 无 flag 机制+v4 FINAL deck 01330d50，非 config A——drift 归因=lineage+牌组双重差异，ledger#130 早有明断），历史 arena 基线作废**，今后对比必跑 drift-control 格（runbook §9-7）；vs first 成全栈共性短板（规则 0.37/LB 0.44/h384d1 0.51），列 Track D 专项。**config A 镜像已重冻（`configA_pristine_79653e2c63b1`，行为等价 pristine=探针件翻 PIVOT→False+内联 deck 2a541d7b 断言+libcg sha 7a157f04 针+registry 登记，非逐字节 459cf97 盘上无此件）；D0e 新开格：LB 0.0385 / h384d1 0.053 / v24.8 纯规则 0.0615 vs 真 config A（n=2000 非 donk）——克隆打不过最好件，v23_2 稻草人实锤，vs-rules 基准自此用新镜像。**D0e-tail（submission 系挂 NN 移植清单）已立项进 runbook Track D：科学问题+判读规则写死（NN 叠加 Δ±2.2pp 消融口径，非「能不能赢」），六步移植（编码器输入契约为主要工程量），边界=禁动 baseline/已注册镜像。**
- **结算期望锚（08-12 下午更正，替代晨版）**：晨版「本地 0.928 → 预期 ~1000+」**已证伪**。live 真人池实证 **WR 0.476 / 分 ~647（42 局平线，#132）**——真水位 **~650±**，非「爬向 1000 途中」；实际跃迁 = **467.9 → ~649 ≈ 1.4×**（非 2.3×；makthanithin 1084.5 系不同时间窗/对手池的分数，不可移植）。**结算停 600–750 属预期内**，不慌、不返工、不因此重开已关闭路线；本地仍可证最强（h2h 87:13 / +620 ELO / LB +616 三口径互证）。（08-12 晚补证：全 LB 扫描 1217→461.7 约 355 页无 makthanithin 队，我方 41 局对手亦无——1084.5 系其公开 notebook 标题自报分（发布期池子），当前排名场根本无作者件可对照，「同代码差 250 分必有未发现差异」分支排除。）

## 观测设施（自动化安全网，不信任记忆）
| 设施 | id | 行为 |
|---|---|---|
| 观测哨 | `automation_f6bd5dac-a888-4c9c-8354-e7e49ae26b45` | condition every=2h，谓词 `assets/conditions/should_fire.py`（调 `experiments/lb_watch.py`，~5s 静默）；四触发器 QUIET_4H / PLATEAU(3样本跨4h极差<3) / EP_100 / CRASH(连续2次跌>30)，命中才开会话推送。历史 `experiments/runs/lb_score_history.jsonl`。**决赛期（~2 周）保持 enabled 持续采样，待 #135 落账后才 disable**；教训 08-17：QUIET_4H 的 4h 静默可能只是 lull（11:37 误报 SETTLED、15:35 被新局证伪），触发判词须人工复核后再行动 |
| 周报 | `automation_530a9aba` | 周三 09:20，读 ledger + lb_score_history.jsonl（禁 CLI）；8/19 收官期出终值版后自 disable |
| ~~结算日报~~ | `automation_c9a973a7` | **已 superseded 并 disable（08-12 16:33）**：内容并入 `reports/2026-08-12_收口判读.md`，避免双发 |
| ~~探针判读提醒~~ | `automation_dd5afa22` | **已触发完成并自 disable（08-15 20:07）**：once 8/15 20:00 按时拉起；探针 48 局达标直接判读（未接力）——public 26-21 / WR 0.5532，Δ+7.7pp<15pp → retroactive NO-GO 归档；dying_674 未翻牌（用户未点头，铁律不动）；结果落 ledger id183 |

## 关键新教训（08-10~08-12，血泪新增）
1. **deck.csv cwd 静默漂移**（#127）：baseline 系模块 `DECK_PATH='deck.csv'` 相对 cwd，从项目根加载会静默捡到根 v24.8 牌组而非 baseline 自家牌组。一切"模块自带牌组"断言不可信——诊断/闸必须显式传 `dsh._baseline_deck()` 并 `assert == submission_baseline/deck.csv`。
2. **引擎不可播种**（#111）：cg C 引擎自取熵，seed 对赛局零作用 → 一切测量=无配对二项抽样，n=1000 两测差 σ≈2.2pp；基线必须同批现测；|Δ|<2.2pp 一律当噪声。
3. **parity 不可达 action-diff**：改造回归验证=结构审查（flag off 控制流逐点等价）+同批 9 腿分数等价。
4. **ELO 波动结构**（#119 讨论）：easy points 前置，新提交初期尖峰（600+）是瞬态非水位；早交=多吃前置红利+多沉淀。
5. **测试件==提交件**：提交前净环境（仅包内文件）`import` 冒烟必须真执行 agent；arena_runner 注入 COMP 会遮盖运行时差异。

## 诊断/工具新增
- `experiments/alakazam_diag.py` — 通用输局结构诊断：`--leg X --n 2000`，logs 事件流归因（KO/奖品/凶手/受害者/奖品竞速），座位轮换 + 牌组硬校验。产物 `experiments/runs/diag_<leg>.json`。
- `experiments/lb_watch.py` + `assets/conditions/should_fire.py` — 观测哨管线。
- 提交 baseline 系的打包：`COPYFILE_DISABLE=1 tar -czf submission.tar.gz main.py deck.csv cg`（在 `submission_baseline/` 内打，**不走根目录 pack.sh**）。
- **08-12 历史警告已失效**：当前 `submission_baseline/main.py` 就是最强 retreat
  提交源码（DYING/NRG=False，RETREAT=True），以上述 SHA 锁为准；目录仍严格只读。

## 待办（接手即查，08-12 起）
| 事项 | 命令/位置 | 状态 |
|---|---|---|
| 结算日报判读 | 已并入 `reports/2026-08-12_收口判读.md`（独立日报已 disable） | ✅ 完 |
| 真人级闸判读 | `experiments/runs/realpilot_gate.json` | ✅ 完：8/9 优势加权 0.840，唯一劣势=已知 Cornerstone 悬崖（非新靶） |
| pilot 层调查 | `experiments/pilot_investigation/`（README 含结论与产物索引） | ✅ 完（08-12 晚收线）：两行为差实证、两候选闸 NO-GO、「闸灵敏度天花板」定谳 |
| **探针判读（live WR 重测）** | #132 管线：`list_submission_episodes(55468450)` + replay + `pilot_investigation/top_pilot_analyze.py --source probe` | ✅ 完（08-15 20:07）：48 局=47 public+1 validation，public 26-21 / WR 0.5532，Δ vs config A 0.476 = **+7.7pp < 15pp → flat/小动，retroactive NO-GO 归档**（统计功效不足、非证伪，σ≈7.3pp@n=47）；config A v2(55451759) 仍为落袋锚；replay 47/47 双路一致；ledger id183 |
| settle 监控 | 观测哨推送即看；勿主动拉瞬读分 | 被动等 |
| 收官记账（决赛期） | 照单跑 `reports/2026-08-17_收官checklist.md`（头号禁忌=截止瞬间不读分）；ledger #135 已预留给收官条（勿占用） | ⏸ 推迟（08-17 晚判，ledger #191）：决赛期 episodes 仍在跑、分数全天漂移，待约两周阶段结束（~8/31）榜单停变后落账；每日样本由观测哨自动落 `lb_score_history.jsonl` |

---

## 1. 项目核心目标与背景

**目标**：在 Kaggle 模拟赛 `pokemon-tcg-ai-battle` 中打造最高分对局 agent。提交物为 `submission.tar.gz`（顶层含 `main.py` + `deck.csv`，可选 `model_student.npz`），Kaggle 以 exec 方式加载源码对局结算。

**三条技术路线现状（08-09 17:00）**：

| 路线 | 载体 | 现状（结算真值） |
|---|---|---|
| 规则版（主力） | `main.py` v24.6，3776 行单文件自包含，硬编码卡库 + 规则引擎 + tuned 参数 | 可证最佳 **396.7**（ref 55310444, v23.1）；今日 ref **55368819**（4 tuned 参数版）瞬读 600.0，**结算真值待 08-10 晨复核** |
| NN pure-python | student 模型独立提交 | 240.8（ref 55348242 结算值）；今日克隆线重建后本地 nn_first 0.40 vs 规则（仍低于平价 0.50，未再提交） |
| hybrid | main.py NN Advisor + `model_student.npz` 随包 | 门禁 REJECTED（新旧两代 student 均未过线，不上线） |

**关键背景教训**：
- **模拟赛道分数结算漂移数小时**。v23.2 瞬读 561.6→结算 373.6；55348242 瞬读 382.2→结算 240.8。**记账一律以次日结算稳定值为准**。
- Kaggle harness exec 加载时 **`__file__` 未定义**；`deck.csv` 读取必须有兜底。
- 本地 arena（全量卡数据）与 Kaggle 端 main.py（硬编码卡库子集）是**两套卡数据**，牌组/参数变更必须过 `pack.sh` 四源校验才能外推。
- **术语更正（ledger 已记）**：`vs_first` = 对内置 `builtin_agent('first')`+SAMPLE_DECK 的苦手对局胜率（先后手轮换），**不是"执先手胜率"**；`nn_first` = NN Advisor 直连模式（`PTCG_NN_MODE`），与先手位无关。旧文档中"先手洞"表述作废；规则版 vs_first ≈0.35-0.37 是对最强 baseline 的 matchup 短板。
- 剩余时间预算：约 6 天（自 08-09 起算）。

## 2. 文件结构说明

### 根目录（提交与门禁）
- `main.py` — **核心交付物**，规则 agent v24.6。当前 sha12=`f3b81aec9ee4`。含：`_INLINE_DECK`（FINAL 60 张）、`_CARD_DB`、`_TRAINER_IDS`（含 1205）、`_PARAMS`（4 个 tuned 参数）、NN Advisor（`_nn_consult`）、TTW 仲裁、1-ply 前瞻、对手建模
- `deck.csv` — FINAL 牌组 60 行（宝可梦 14 / 训练家 29 / 能量 17，含 1205シアノ×1）
- `pack.sh` — 打包 + 四源校验；**npz 显式 opt-in**（`--with-npz` 才随包，默认排除）
- `submit.py` — Kaggle 提交脚本（依赖 `kagglesdk`，须用 `/opt/homebrew/bin/python3 submit.py`；描述串已改自动派生）
- `submission.tar.gz` — **1205 FINAL 版已打包（50K，纯规则无 npz），待用户确认提交**
- `model_student.npz` — 当前为 **h384d1**（student 直接 BC + DAgger r1，996K）；非提交物，仅供本地 NN 实验
- 关键备份：`main.py.bak-2026-08-09-tune`（**调参前旧默认参数，mirror 对照专用**）、`main.py.bak-2026-08-09-pre1205`、`deck.csv.bak-2026-08-09`（原牌组）、`deck.csv.bak-2026-08-09-r2`（round2 牌组）
- `kaggle_gpu_train.py` — Kaggle GPU 一体化训练脚本（teacher→distill→npz；**stage 默认已改 `all`**，支持 `--sample-index` 胜方过滤）

### experiments/（实验 harness — 引擎室）
- `arena_runner.py` — 对局评估核心：`run_arena(agent_a, agent_b, decks_a, decks_b, n, seed0)`、`builtin_agent('first'/'random')`、`load_module()`、`wilson_ci_lo()`
- `param_tune.py` — 规则参数调权 harness（**本轮已完成**：round1+2 + final，产出 4 tuned 参数）
- `deck_search.py` — 牌组贪心置换爬山（**本轮已完成 3 轮**，round3 接受 -673+1205）
- `deck_final_verify_v4.py` — 1205 部署复验（mirror + vs_first 双腿，已过）
- **`selfplay_harvest.py`** — 主线B 自对弈/DAgger 采集器：`--games N --seed0 --workers 8` 自对弈；`--dagger --gid0 100000` DAgger（student 轨迹+规则 oracle 重标）；`--manifest` 重建清单。产出 leaderboard_replay 同构 JSON → `inference/selfplay_replay/raw/`
- **`student_bc_probe.py`** — student 直接 BC 训练（跳过 teacher 蒸馏），`--hidden 384 --epochs 16 --tag xxx`，产物 `/tmp/student_bc_probe_<tag>_best.pt`
- **`nn_gate_verify.py`** — NN 四道门核验（teacher top1 / 蒸馏损失 / nn_first 实战 / hybrid 双腿）
- `make_splits_selfplay.py` — 自对弈数据集 splits 生成器
- `nn_override_probe.py` — NN Advisor 介入率探针
- `ledger.jsonl` — **项目事实账本**（查历史先 grep 它）
- `runs/` — 事件流/断点/日志（含 `deck_final_verify_v4.json`、`nn_gate_verify.json`、`selfplay_harvest.log` 等）

### inference/（NN 训练/数据管线）
- `dataset/extract.py` — replay→张量（**新增 `PTCG_EXTRACT_MANIFEST` env 覆盖清单路径**）
- `dataset/train_v2.py` — teacher→distill 训练（**新增 `--sample-index`**：BC/distill 限胜方子集，AWR 仍全量保 reward 对比）
- `dataset/quality_subset.py` — 胜方过滤（captured_team_only）
- `dataset/data-selfplay/` — 自对弈张量（356,576 决策 / 4,992 episodes，含 DAgger 批）；`data-selfplay-quality/`（入选 184,796）；`splits-selfplay/`
- `selfplay_replay/raw/` — 4,992 局自对弈+DAgger 回放 JSON（~1.1GB）；`manifest.csv`
- `dataset/data/`、`leaderboard_replay/` — 旧排行榜数据源（1.8M 决策，**已判定 covariate shift，弃用**）

### Kaggle 云端（NN 训练）
- Datasets：`daniel1547/ptcg-tensors`（最新版=自对弈 276K+sample_indices）、`daniel1547/ptcg-code`（最新版=sample-index 接线+selfplay splits）
- Kernel：`daniel1547/ptcg-gpu-train-teacher-distill`（T4 x2，**当前 v3 已训完自对弈版**）
- staging：`.kaggle_stage_tensors/`、`.kaggle_stage_code/`、`.kaggle_kernel/`（push 前打包处）
- ⚠️ **竞态教训**：`kaggle datasets version` 后必须等 `datasets status` 返回 ready 再 `kernels push`，否则 kernel 挂载旧版数据（v2 白跑过一次 1.8M 旧数据）

### 文档
- 本文件 + `HANDOFF.md.bak-2026-08-09`（旧版）；`reports/kaggle-daily-2026-08-0{6,7,8}.md` 日报
- `reports/kerr_selfplay_v3/` — v3 训练产物（train_v2.log、report、npz、ckpt）
- `reports/model_student.pre-selfplay.backup.npz`、`model_student.distill-v2t-ep8-canarybest.backup.npz` — 旧 student 备份
- `kimi_code_summary.txt` — 08-08 kimi code 对话记录；`hy3_investigation_claim{,2,3,4}.txt` — hy3 四批审计（已核验修复 19 项+1 更正）

### 关联项目（本工作区外，勿混入）
- `~/Desktop/ptcg-bcrl` — bcrl 离线强化学习循环（launchd 驱动，00:30 轮次；`.worktrees/exp/results.tsv` 账本，`.best_commit`=4dce430 / val 0.5379）

## 3. 当前开发进度（截至 2026-08-09 17:10）

### 已完成 ✅（今日，全部入 ledger）
1. **param_tune 完成**：4 tuned 参数写入 main.py（p9_attack_dmg_min=75, bench_attach_can_attack_bonus=500, prize_sprint_threshold=0, switch_ready_bench_energy=1），本地复验 mirror 0.5353/ci_lo 0.5243 PASS
2. **已提交 ref 55368819**（4 tuned 参数纯规则版，13:16）：瞬读 600.0，**结算真值待 08-10 晨复核**
3. **1205シアノ FINAL 牌组部署**（v24.6）：-673マクノシタ+1205シアノ（唯一差异），main.py 三点式移植（trainer_priority 1205:91 + `_TRAINER_SIANO` + P6 强打），复验 **mirror 0.6903/ci_lo 0.6800、vs_first 0.3719、invalid=0** 全 PASS，`pack.sh` PASS，**submission.tar.gz 已打好待确认**
4. **hy3 四批审计核验**：19 项修复 + 1 项更正（pack.sh npz 静默随包、submit.py 描述硬编码、SAMPLE_DECK 空行过滤、replay_harvester 容错等）
5. **NN post-mortem（回答"为何放弃 BC+AWL / NN 为何只有 240 分"）**：无原理性放弃原因；瓶颈排序 = 数据 covariate shift（11/60 重叠）→ BC 模仿天花板 0.55 → 部署约束 2M 参数 → 蒸馏仅 -2.3pp（最健康）；240.8 = 纯 student 独立提交的真实水平（非 hybrid 被覆盖），且其 LB 牌组与规则版不同（混杂因素）
6. **主线 B 数据管线建成**（原"训练分布对准"）：自对弈采集 3,974 局/276,466 决策（72 秒！旧管设想 2-3 晚）→ extract/quality/splits 全通 → Kaggle GPU v3 重训（teacher canary top1 **0.7735**，突破旧 0.55 天花板，数据对齐有效）
7. **NN 四道门实测**：①teacher top1 PASS ②蒸馏损失 FAIL（-12.2pp，**蒸馏是保真杀手**）③nn_first FAIL（0.2741）④hybrid FAIL（0.4647 反劣于纯规则）
8. **student 直接 BC 破局**：跳过 teacher 中转，top1 0.65→**0.7418**，门③实战 0.2741→**0.3997**（+12.6pp）；h768 扩容仅 +0.7pp（0.7484）
9. **DAgger r1**：998 局/80K 决策 oracle 重标，门③ 0.4024（+0.3pp 噪声级）
10. **残差分析**：偏差 26% 集中 **ctx=0 主菜单**（59% 样本，agree 0.6529）——规则是 18 级字典序优先链，MLP 渐近线 ~0.75-0.80
11. **利基测试否定**：NN vs first 0.3744 vs 规则 0.3694（噪声内），NN 在最弱 matchup 也无优势

### 进行中 🔄
- **等待用户确认第二次提交**（1205 FINAL 版，包已打好）
- **NN 方向待拍板**：A（ctx=0 定向扩容/特征）/ C（规则+1-ply 搜索 oracle 标注，唯一原理性超平价路径）/ D（等 bcrl 超 0.5379 后克隆改进策略）

### 阶段性成果 📊
- 规则线：396.7（可证最佳）→ 55368819 结算待复核（瞬读 600.0）；1205 版本地 +2.7pp 已验待提交
- NN 线：克隆保真阶梯 0.53→0.65→0.74 top1 / 实战 0.27→0.40；数据/训练/门禁管线全通且迭代成本降至分钟级
- 工具链：四源校验、断点续跑、独立种子终验、ledger 账本、四道门核验全部脚本化

## 4. 未来开发计划与里程碑

### 短期（24h，按序）
1. **用户确认后提交 1205 FINAL 版**：`/opt/homebrew/bin/python3 submit.py submit`（包已就绪；新旧两包 sha 不同不影响，freshness 门禁只比 tar vs live）
2. **08-10 晨例行**：`kaggle competitions submissions` 复核 55368819 结算真值记账；读 bcrl `results.tsv` 是否超 0.5379
3. NN 方向拍板后执行（见 §3 进行中）

### 中期（本周）
4. **param_tune 管线加 vs_first 回归门禁**（下周期 #1）：未来参数集不得在 vs_first 上退步 >2pp
5. 若 bcrl 超 0.5379：用**新循环权重**经 `build_pure.py` 重建 pure 提交（⚠️ 旧权重×08-08 模板错配实测 0/3 vs random）
6. 若走 C 路线：规则+1-ply 搜索 oracle 标注器（v24.4 前瞻层现成），重训 → 门③ >0.50 才解锁 B-6
7. 每日：结算真值复核 + ledger 维护

### 长期（比赛剩余窗口）
- **B-6 规则抽取**（封锁中，解锁条件 = 门③ nn_first>0.50）：TREPAN/NN2Rules 抽 50-100 条规则 → holdout fidelity ≥90% → 翻译为 `_PARAMS`/优先级表有界修改 → 评估全家桶。定位：解决规则开发 token 成本 + 发现人想不到的启发式
- NN 独立提交线（纯 student）暂不重启：当前 0.40 vs 平价 0.50，差距明确

## 5. 主要缺点与待改进（技术债务 / 风险）

| 类别 | 问题 | 影响 / 缓解 |
|---|---|---|
| 分数漂移 | 结算漂移数小时，瞬读 600 可能大幅回落 | 记账以次日结算值为准；提交决策不过夜不拍板 |
| NN 蒸馏链 | teacher→student 保真 -12.2pp（自对弈数据上） | 已实证 student 直接 BC 更优；蒸馏超参（temp 3/alpha 0.3/8ep）未调 |
| NN 保真渐近 | ctx=0 主菜单 agree 仅 0.65，MLP 对字典序规则链渐近 ~0.75-0.80 | 扩容收益小（h768 +0.7pp）；需结构改造（option-attention）或换 oracle |
| 卡数据双轨 | 本地全量 vs main.py 硬编码子集 | 新卡必过 pack.sh 卡池校验；`gen_card_db.py` 未全自动 |
| 机器资源 | 内存紧张 + thermal 记录，jetsam 杀过进程 | 一律 `nice -n 10`；错开 bcrl 00:30；workers 必要时降 4 |
| Kaggle 竞态 | datasets version 未 ready 就 push kernel → 挂旧数据白跑 | 已立规：status=ready 后再 push；v2 废 run 已记 ledger |
| submit.py | 依赖 `kagglesdk`（managed python 无） | 用 `/opt/homebrew/bin/python3`；CLI 查状态 |
| main.py 体积 | 3776 行单文件 | 改动前确认 sha；内容哈希冻结校验（mtime 不可信） |
| vs_first 短板 | 规则版 vs first bot 仅 ~0.35-0.37（最强 baseline matchup） | 非先手位问题；NN 利基测试也无优势；待专项分析 |
| 旧调权产物 | `best_params.json`、v244 轮 4 参数（p9=90 等） | 旧基底，勿套用，仅作先验参照 |

## 6. 交接特别注意

### 关键接口/事实源
- **`experiments/ledger.jsonl` 是唯一权威账本**（含 NN post-mortem、主线B全程、术语更正）。查历史先 grep 它
- 断点续跑：`param_tune_ckpt.jsonl` / `deck_search_ckpt.jsonl`，键含 main_sha/deck_fp，改牌组/main.py 自动开新命名空间
- Kaggle CLI：`/opt/homebrew/bin/kaggle`（`competitions submissions` / `kernels status` / `datasets status`）
- NN 实验三件套：`selfplay_harvest.py`（采集）→ `student_bc_probe.py`（直训）→ `export_student.py`（导 npz 到仓库根）→ arena 门禁（nn_first 模式）

### 环境配置
- **实验/训练/导出脚本一律 `/opt/homebrew/bin/python3`**（有 torch + zstandard + numpy + kagglesdk）；Kimi managed python（直接 `python3`）仅用于轻量任务，无 torch/zstd/kagglesdk
- 重型任务：`nohup nice -n 10 ... > 日志 2>&1 &`，点火后 60s + 5min 两次确认存活
- arena 速度参考：8 worker 自对弈 ~3,400 g/min；n=8000 对局约 2-4 分钟
- 工作区路径含大写下划线；注意带前导空格的 symlink 陷阱

### 代码/流程规范（血泪凝成）
1. **改 main.py / deck.csv 前必备份**（`*.bak-YYYY-MM-DD`），改后必跑 `pack.sh` 四源校验
2. 冻结校验用内容哈希（`shasum -a 256`），两次间隔 ≥600s
3. 牌组/参数变更落地前：**独立种子集终验**（seed0=9000，n=8000，Wilson 下界 >0.5 且 invalid=0，与搜索种子错开）
4. **不杀** bcrl / param_tune / deck_search 进程；不动 `~/.hermes/` 与 launchd
5. **不提交 Kaggle，除非**：本地复验过 + pack.sh 过 + 纯规则版明确排除 `model_student.npz` + **用户明确确认**
6. ledger 追加用 JSON Lines，人工代写 pipeline 事件必须带 `"source": "manual_reconcile"`
7. Kaggle 数据集更新后：**等 ready 再 push kernel**（竞态教训）

### 多 agent 协作现状
- **本 session（Kimi Desktop automation）**：值守/终验/换牌/调权/NN 实验/账本维护
- **kimi code**：main.py 代码工程。⚠️ websocket 不稳——**一切交接以 ledger + 本文档为准**
- **TRAE SOLO**：bcrl 循环（launchd 00:30 轮次）

### 当前待办一览（接手即查）
| 事项 | 位置/命令 | 状态 |
|---|---|---|
| 第二次提交（1205 FINAL） | `submission.tar.gz` 已打好；`/opt/homebrew/bin/python3 submit.py submit` | **等用户确认** |
| 55368819 结算复核 | `/opt/homebrew/bin/kaggle competitions submissions pokemon-tcg-ai-battle` | 08-10 晨 |
| bcrl 结果 | `~/Desktop/ptcg-bcrl/.worktrees/exp/results.tsv` | 每早，阈值 0.5379 |
| NN 方向 | §3 进行中 A/C/D | 等用户拍板 |
| vs_first 回归门禁 | `experiments/param_tune.py` | 下周期 #1 |

**接手第一步建议**：`tail -8 experiments/ledger.jsonl` + `kaggle competitions submissions pokemon-tcg-ai-battle | head -5` + 本文件 §3，三条即可重建全部上下文。
