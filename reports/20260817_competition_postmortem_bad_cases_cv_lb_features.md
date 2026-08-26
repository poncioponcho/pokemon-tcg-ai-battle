# Pokémon TCG AI Battle Challenge 复盘：Bad Cases、CV–LB Shakeup 与特征工程

日期：2026-08-17  
范围：本次比赛从 BC/规则基线、候选验证、live 诊断，到最终 exact Grim v22 的完整实验链  
证据口径：以仓库中的 HANDOFF、实验 ledger、逐局 replay、冻结归档和预注册报告为准；不把 notebook 标题分、单次峰值或不同 submission 的分数拼成事实

## 0. 结论摘要

这次比赛最大的 Bad Case 不是某一条牌局规则写错，而是多次出现了“测量对象、运行对象、提交对象不是同一个东西”。典型表现包括：

- 本地 CV 用同一个弱 pilot 驾驶双方牌组，得到加权 WR 0.8402；真实天梯却只有 WR 0.476。CV 测到了牌组对位，却没有测到真实 opponent pilot。
- H2H runner 曾让两个候选共享顶层 policies 模块和状态，候选之间互相污染。
- 净包遗漏 EN_Card_Data.csv 后，异常被 fallback 吞掉，报告仍显示零 fault，但实际运行的是退化策略。
- deck.csv 曾按当前工作目录解析，静默加载到错误牌组；训练数据还出现过“我方牌组槽位写入对手牌组”和不可见对手牌组泄漏。
- 本地原生引擎不可播种，历史所谓 paired/CRN 并不成立；小样本尖峰被反复误认为提升。
- 新提交的 Glicko 高不确定度、600 初始分和相近分配对制造了普遍的 spike→decay；不同 submission instance 不能当作同一个机器人时间序列。
- BC 的 in-distribution top-1 约 0.54，并没有转化为实战优势；train、fixed test、canary 几乎相同，根因更像表示能力不足和部署分布漂移，而不是普通过拟合。

最终结论是：

1. **早期 CV 与 LB 明显不一致。** 最大差距来自 opponent policy/pilot 缺失，其次是 meta 权重错配和测量污染。
2. **修正后的 CV 能较好判断候选相对排序，但仍不能直接预测绝对 LB 分数。** v22 在线下击败 retreat 后，线上也在更强对手池中明显优于 retreat；这是方向一致，不是数值校准完成。
3. **最终提交不是学习模型，而是以公开可见状态为输入的结构化规则系统。** 其有效“特征工程”主要是资源账本、进化链、奖品图、回合阶段、动作语义、目标价值、未来资源预约和跨回合连续性。
4. **实验过的 learned features 没有进入最终件。** Route-A 的 32 维 residual features 在 36,432 局 cross-fit 中只有 +0.1991pp，未达到 +3pp 闸；因此按预注册停止。

最终冻结件为 [artifacts/grim_v22_final/submission.tar.gz](../artifacts/grim_v22_final/submission.tar.gz)，SHA256 为 599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf。截止附近两个 exact-v22 实例分别记录为 833.7 和 826.0；这是比赛截止时点的观测值，不应与不同时间窗的历史峰值直接比较。

## 1. 这次比赛中的“CV”究竟是什么

本项目不是标准的静态表格分类赛，因此 CV 不是单一 K-fold accuracy，而是四层验证：

### 1.1 模仿学习 CV

- fixed test：按 episode ID 固定分配，避免同一局的相邻决策泄漏到训练和验证两侧。
- rolling canary：时间更新的真人 replay 监控集，用于检查策略分布漂移。
- 主要指标：动作 top-1、按 context 和 option 数分桶的一致率。
- 局限：动作模仿正确率不是终局胜率；示范者混杂、牌组错配和闭环误差都会让 top-1 与 W/L 脱钩。

### 1.2 本地对局 CV

- 使用官方本地 cg 引擎进行 H2H。
- 候选与冻结 incumbent 同批运行，交替 candidate seat。
- 后期固定四腿或九腿 matchup，而不是只打镜像或 builtin first。
- 主要指标：终局 W/L、Wilson 区间、相对同批 incumbent 增量、各腿保护线和 fault。

### 1.3 部署 CV

- 从最终 tar.gz 解包，不从开发目录运行。
- 检查 60 卡、copy limit、ACE SPEC、manifest、双入口、无 __file__ 的 Kaggle exec 入口、资源文件和官方 cg。
- 再运行 self-play、跨牌组腿与动作合法性检查。
- 这一层回答“测试的代码是不是实际提交的代码”，而不是强度问题。

### 1.4 Live holdout

- 按 submission ref 分开拉取 PUBLIC episodes，排除 validation episode。
- 报告 W/L、对手均分、matchup、运行时状态和对手强度校正后的隐含 mu*。
- 对冻结 replay 做动作重放，验证本地归档是否能复现线上行为。
- 这是最接近 LB 分布的验证层，但样本少、异步、受 Glicko 配对影响，不能当成高频调参集。

LB 本身是异步 Glicko 式动态评估：新件从 600 开始、初期不确定度高、配对偏向相近分 submission，并获得加速采样。因此 CV 与 LB 的对齐目标应是“候选排序和失效模式一致”，而不是“本地 WR 线性换算为某个榜分”。

## 2. Bad Cases 与解决办法

### 2.1 Bad Case：本地 CV 测成了 equal-pilot 牌组测试

#### 现象

九腿本地闸使用 config A 同时驾驶我方和对手牌组，得到：

- 8/9 腿优势；
- 加权 WR 0.8402；
- Alakazam 腿 WR 0.6565；
- 唯一劣势 Cornerstone WR 0.3515，但 live 权重仅约 1.1%。

同一时期真实天梯 config A 只有 42 局 20-22，WR 0.476，约 650 分。尤其 Alakazam 在线下是优势腿，在线上却占败局约 33%，方向都发生了反转。

#### 根因

这套 CV 只改变了牌组，没有改变对手 pilot。它回答的是“同一个 config A pilot 驾驶双方时，牌组对位如何”，而 LB 对手是不同团队写出的真实 agent。真实差距主要在行动顺序、能量投放、付费 retreat、奖品交换和跨回合规划，不是单纯牌表。

进一步按 live 对手配比重算后：

- 原 equal-pilot CV：0.840；
- 换成 live 配比后的 equal-pilot 软锚：约 0.744；
- 0.840→0.744 的约 9.6pp 来自 matchup 权重错配；
- 0.744→0.476 的约 26.8pp 是 pilot residual。

#### 解决

- 将“真人级闸”更名为 real-deck/equal-pilot 闸，停止把它解释成 live 胜率预测器。
- 将真实 submission strategy 加入本地对手腿，而不是只用 builtin first。
- 依据 live episodes 更新 matchup 权重，但把小样本权重标为软锚。
- 把候选验证拆成牌组层、pilot 层和部署层，禁止跨层外推。
- 最终只有 W/L 与 live replay 能证明 pilot 改动；equal-pilot 闸只保留下行保护功能。

### 2.2 Bad Case：候选 H2H 的 sys.modules 污染

#### 现象

多个候选都使用顶层包名 policies。旧 candidate_h2h.py 在同一 Python 进程中加载双方，导致后加载候选复用先加载候选的模块和模块级状态。修复前 v28 的 Grim 腿看似优于 v22；修复后同批 n=64 变成：

- v22 对 Grim：39-25；
- v28 对 Grim：28-36。

原结论被直接推翻。

#### 解决

- 每个 CandidateAgent 维护私有模块缓存，运行候选前切换自己的 sys.modules 视图。
- 报告记录 runner SHA、candidate main/deck SHA、模块隔离版本。
- 双方存在同名顶层包的旧结果默认失效，除非能证明没有共享状态。
- 候选每局前发送 select=None，清空模块级历史与 StrategicMemory，避免上一局污染下一局。

这次修复的价值高于任何单个候选，因为它改变了后续所有实验的可信度。

### 2.3 Bad Case：净包漏资产但“零 fault”假通过

#### 现象

v22/v28 会读取 EN_Card_Data.csv。旧净包没有带这个文件，组合 policy 捕获异常后退回备用策略，所以运行没有抛出 candidate fault，却只打出退化表现。类似问题还出现过首包遗漏官方 cg，直接造成 validation error。

#### 解决

- 将 EN_Card_Data.csv 和官方 cg 纳入提交 manifest。
- 从最终 tar 解包目录实读 card 646，验证为 Marnie's Impidimp / Basic Pokémon / 70 HP。
- 不再把 zero fault 当成交付成功；必须检查预期策略层确实被执行。
- 新增候选 cwd、Kaggle last-callable、无 __file__ 三种入口测试。
- 使用确定性 gzip/manifest，重复打包必须得到相同 SHA。

### 2.4 Bad Case：deck.csv 与训练特征静默漂移

#### 现象一：本地牌组按 cwd 解析

baseline 模块用相对路径 deck.csv。从项目根运行时，它曾静默加载根目录另一版牌组，而不是 submission_baseline 的真实牌组，导致诊断测的不是预期 baseline。

#### 现象二：训练集牌组归属错误和隐藏信息泄漏

旧 replay 提取逻辑用错误条件识别 60 卡选择动作，曾把玩家 1 的牌组写入玩家 0 的“my deck”槽位。同时，对手完整牌组是部署时不可见信息，旧数据约 49% 行该槽非零，形成训练泄漏和推理分布偏移。

#### 解决

- 所有 baseline/候选牌组显式传入，并对 deck SHA 和 60 卡内容做硬断言。
- replay 按 step 内 agent 下标绑定玩家牌组，而不是依据 select 是否为空猜归属。
- 对手牌组槽在训练和推理两侧都强制为零；只使用对局当时公开可见的对手 active、bench、discard 和计数。
- cardId 统一转 int，避免字符串 ID 静默落入 unknown 槽。

### 2.5 Bad Case：replay observation/action 错位

#### 现象

Kaggle replay 的动作不是与同一个 step 中的 observation 对齐；正确关系是 steps[s] 的 ACTIVE observation 对应 steps[s+1].action。错一位会把正确策略判为大量 mismatch，并污染行为归因。

#### 解决

- 固化该 off-by-one 规则。
- 对 82 场 v22 PUBLIC replay、8,333 次 ACTIVE 调用顺序重放，得到 0 mismatch。
- 只有在 0-mismatch 基线成立后，才允许用 replay 做首次分叉、guard 触发率和 matchup marker 分析。

### 2.6 Bad Case：把不可播种引擎当成 paired/CRN

#### 现象

本地 native dylib 使用 random_device，没有暴露 shuffle seed setter。Python 的 random.seed 或 CLI seed 只能固定 Python 侧策略，不能重放相同洗牌。因此同 seed 的两次对局仍是独立二项样本。

#### 解决

- 删除 paired/CRN 表述，统一称 blocked independent trial。
- ABBA/BAAB 只用于平衡座位和粗时间块，不声称逐局配对。
- 每批同时运行 incumbent control，以同批差值而不是历史均值判定。
- 使用 Wilson 区间、Fisher 检验和更大 n；小于约 2.2pp 的差异按本地噪声带处理。

### 2.7 Bad Case：小样本 winner's curse 与榜分尖峰

出现过多个教科书级例子：

- config A v2 在 4 局 4-0 时瞬时到 859.1，最终 24-30，WR 0.4444。
- dying_674 冒烟一度约 +5.7pp，n=2000 后只有 +0.43pp。
- v22 residual ES 候选在 n=64 一度 58.73%，独立 n=256 回落为 133-123，即 51.95%。
- v29 首批直接 H2H 58.3%，独立 n=256 只有 52.3%；合并 Wilson 区间仍跨 50%。
- 同代码不同 submission instance 也走出了不同短期曲线，说明路径方差不能当代码差异。

#### 解决

- 所有实验在看结果前预注册晋级线。
- 采用 screen → independent confirmation → n≥256 主闸 → exact-archive → live 的漏斗。
- 行动层允许用方向性证据选择 incumbent；认知层只有跨过更严格阈值才宣称真实提升。
- public score 只作末级辅助，不再用峰值选择 baseline。
- 对 Glicko 曲线按 submission ref 分开，不拼接不同实例。

### 2.8 Bad Case：BC 的 CV 指标与闭环胜率脱钩

#### 现象

- 真人 replay BC/AWR 的 canary top-1 约 0.5332–0.5498。
- train 0.5407、fixed test 0.5410、canary 0.5498 几乎相同，说明不是典型训练集过拟合，而是模型类和表示层欠拟合。
- 部署 H2H 约 0.40，in-distribution 动作一致率没有转化为对局优势。
- 自生成数据能把 teacher top-1 提到 0.7735，但 student 蒸馏后约 0.6515，实际 nn_first 仍只有约 0.274；动作误差会在长回合闭环中累积放大。
- 旧日报中的 student 0.2633 后来被确认只是 30k 行、1 epoch CPU smoke 的陈旧读数；真实云端 student canary 为 0.5372。错误引用一度把优化优先级带偏。

#### 根因

- 状态采用大量 bag/count 和扁平标量，缺少“哪张能量附在哪个宝可梦”“某个 option 的 source-target 关系”“进化链依赖”“本回合动作次序”等关系结构。
- ctx=0 主菜单是长字典序策略，平坦 MLP 难以表达离散优先级边界。
- winner-only BC 混合不同示范者，且单步 top-1 对多步闭环错误不敏感。
- 部署 student 有约 2M 参数限制，输入投影本身占约 1.73M，模型容量没有真正用在关系推理上。

#### 解决

- 将 fixed test、rolling canary 和 arena W/L 分离；top-1 只作诊断，不再作为提交充分条件。
- canary 使用显式快照，评估时禁止刷新并改写样本。
- 每次模型版本必须运行同环境 drift-control、incumbent H2H 和部署路径测试。
- 本场没有强行提交 NN；最终切回可复现的 exact-v22 规则系统。
- 下一版优先改关系化表示和 option encoder，再讨论更多 epoch 或复杂奖励。

### 2.9 Bad Case：误读 LB 机制和 submission 时间序列

#### 现象

- 一度把 700.3、607.3、恢复件分数当作同一个机器人随时间变化，但它们属于不同 ref、不同 matchmaking pool。
- 一度把 spike→decay 解释成新玩家“刷分”把旧队伍打下去。
- 一度对 latest-2 是 latest-only 还是 best-of-latest-2 存在矛盾认知。

#### 根因

新 submission 从 mu0=600 起步，sigma 大、单局更新大，并优先匹配相近分对手。早期对手通常较弱，随后随着 mu 上升匹配到更强池，于是自然产生 spike→decay。该轨迹不需要“刷分玩家”假设。

#### 解决

- 按 ref 拉逐局数据，排除 validation，并同时报告对手均分。
- 用对手强度校正的隐含 mu* 作为跨 ref 辅助指标。求解：

  sum_i 1 / (1 + 10^((opponent_rating_i - mu*) / 400)) = observed_wins

- n<20 只记方向；当前对手分与对局时点不一致，mu* 只作粗代理。
- exact-v22 受控重交后，在 +5、+15、+84 分钟同时读取新旧 ref 和团队行，实证团队分取 best-of-latest-2。
- 最终槽位用两个 exact-v22 独立实例，而不是按短期峰值追单。

## 3. CV 与 LB 到底一致吗

### 3.1 直接回答

**早期不一致，而且是严重 shakeup；后期相对排序逐渐一致，但绝对数值仍不一致。**

不能用一句“CV 好、LB 差，所以过拟合”概括。至少有四种不同问题：

1. CV opponent policy 与 LB 不同；
2. matchup 权重不同；
3. runner、牌组和资产发生测量污染；
4. Glicko 分数和静态胜率不是同一统计量。

### 3.2 最严重的绝对校准差

- 本地 real-deck/equal-pilot 加权 WR：0.8402。
- live config A WR：0.476。
- 差距：36.4pp。
- 按 live matchup 配比重加权后，CV 软锚约 0.744。
- 剩余约 26.8pp 仍无法由牌组分布解释，属于 pilot/策略分布差。

这说明本地 CV 不能用于预测“LB 会到 1000+”；它最多能说“同 pilot 下这副牌不差”。

### 3.3 后期相对排序开始对齐

修复 runner 和交付链后，v22 的离线证据包括：

- exact archive 对 retreat：n=32 为 20-12；独立 n=64 为 42-22。
- 对完整 Grim：39-25/64。
- 对 Router：38-26/64。
- 对 Alakazam：51-13/64。

随后同一 live 窗口：

- v22：49 PUBLIC，28-21，WR 0.571，对手均分 799，隐含 mu* 约 852。
- retreat recovery：37 PUBLIC，15-22，WR 0.405，对手均分 657，隐含 mu* 约 583。

v22 不仅 WR 高 16.6pp，而且面对更强的对手池。这里离线“v22 优于 retreat”的排序与线上一致。需要强调：Fisher/Wilson 仍然很宽，所以这是可靠的行动层排序，不是精确效应量。

### 3.4 仍然没有解决的绝对映射

即使后期排序一致，也不能写成：

- 本地 65% 就等于 LB 850；
- 某腿 +5pp 就等于总榜 +40 分；
- 两个同代码 submission 应得到相同短期分数。

原因是本地对手不是完整 live population，LB 还包含 Glicko 状态、对手分布、时间与采样率。最终保留的是“相对晋级规则”，不是伪精确的分数换算公式。

## 4. Shakeup 后如何调整交叉验证策略

### 4.1 冻结唯一 incumbent

- 每轮只允许一个明确 incumbent。
- 锁 main、deck、完整运行树和 archive SHA。
- 任何候选都在同批直接对 incumbent，不再引用过期历史分或不同牌组 baseline。
- baseline 变更必须有 live 或大样本 H2H 证据，并在 HANDOFF/ledger 中显式记录。

### 4.2 从单一镜像改成分层 matchup CV

后期四腿使用：

- exact v22 主腿；
- Router；
- Alakazam；
- Lucario/recovery。

更早的九腿用于牌组层诊断。权重来自 live meta，但小样本权重不设成永久真值。每个候选必须同时满足：

- 主腿不退化；
- 加权相对 incumbent 有足够增量；
- 没有单腿崩塌；
- fault 为零；
- 行为变化率既不为零，也不能大到等同换策略。

### 4.3 同批 control、独立批 confirmation

- 每个 candidate batch 同时运行 incumbent control，抵消当天引擎与环境变化。
- screen 只做廉价淘汰，不用于提交。
- survivor 在独立随机批复验，避免 winner's curse。
- 主闸要求 n≥256；更小样本只提供方向。

### 4.4 exact-archive CV

候选过统计闸后，不直接从开发目录提交，而是：

1. 构建 deterministic archive；
2. 从空目录解包；
3. 读取 manifest 和所有依赖资产；
4. 运行普通入口、Kaggle exec 入口和无 __file__ 入口；
5. 运行 self-play、跨牌组、合法动作和 60 卡检查；
6. 重复打包并验证 SHA 一致。

这一步解决的是“CV 版本和 LB 版本不是同一个程序”。

### 4.5 将 live replay 变成校准层，而不是调参训练集

- 旧 ref 用于 hypothesis design，新 ref 作为 blind holdout。
- 只使用当时可见的信息；完整对手牌表不能进入可部署特征。
- 先验证 exact-v22 对线上 replay 0 mismatch，再检查候选首次分叉。
- replay 的原 W/L 只作覆盖标签，不能把改写动作后的结果当反事实 reward。
- 最终仍需本地 terminal W/L 或真正在线反馈。

### 4.6 加入对手强度校正

每个 live 结论同时报告：

- PUBLIC n、W-L、WR；
- Wilson 区间；
- 对手均分和 matchup 分解；
- 隐含 mu*；
- ref、采样时间、validation 排除情况。

当两个候选 WR 差小于 3pp、但对手均分差超过约 30 分时，不再只看裸 WR。mu* 仍是 Elo-400 粗代理，不替代 Kaggle 内部 Glicko。

### 4.7 分离行动层和认知层

- 行动层：在截止期可按后验排序选择更强候选，即使显著性不足。
- 认知层：只有跨过预注册阈值、独立复验和保护腿，才把规则写成可迁移结论。

这样既不会因为功效不足而归档所有候选，也不会把一次 4-0 峰值写成“真实 +200 分”。

## 5. 特征工程及其业务逻辑

### 5.1 最终 exact-v22：结构化规则特征，而非黑盒模型

最终 agent 明确不包含拟合参数、replay 索引、搜索树或神经网络。它把公开 observation 转成一组可解释的牌局状态，并由 manual guards、hierarchy 和 validated fallback 决策。

#### 5.1.1 动作语义特征

每个 option 被解析为：

- action type；
- source card ID、serial、zone、相对玩家；
- target card ID、serial、active/bench 区域、相对玩家；
- attack ID；
- 原始 area/index/in-play index。

业务逻辑：Kaggle 返回的是可变长度 option list，数组下标本身没有跨状态意义。真正有意义的是“从哪里用什么牌，对哪个目标做什么动作”。语义化还能把两张等价 Trainer 的不同 serial 合并，避免制造假分叉，同时保留同 ID 场上目标的 serial，因为它们的 HP、能量和进化历史可能不同。

#### 5.1.2 资源账本特征

ResourceLedger 汇总：

- 双方奖品数、手牌数、牌库数、弃牌规模、Bench 空位；
- 我方 hand/discard/board 的卡牌计数；
- 双方 active/bench 的 HP、max HP、能量和身份；
- Impidimp→Morgrem→Grimmsnarl 进化线数量；
- 已能攻击的 Grimmsnarl、已供能的 Munkidori；
- 可回收核心资源、受伤己方单位数；
- 本回合是否已经贴能、用 Supporter、用 Stadium、retreat；
- 最近两次动作的类型、来源和目标。

业务逻辑：这副牌的瓶颈不是单张牌价值，而是“主攻手进化链、第二攻击手、Froslass 被动伤害、Munkidori 伤害控制、能量和回收”之间的资源依赖。只看手牌 ID 会错过当前缺的是 body、evolution、energy 还是 replacement attacker。

#### 5.1.3 回合阶段与目标特征

TurnPhase 将牌局分为 setup、build、stabilize、pressure、close；TurnObjective 再选择：

- 建立主进化线；
- 完成攻击手；
- 建立替补攻击手；
- 启用 Munkidori 控制；
- 完成 Froslass 引擎；
- 控制手牌规模；
- 绕过 ex 免伤施加 spread pressure；
- 回收资源或直接转换奖品。

业务逻辑：同一张卡在不同阶段价值不同。例如剩 1–2 奖品时，Boss/gust closer 和立即 KO 的价值高于继续铺场；主攻手在线后，资源应转向 replacement attacker，而不是重复建设已完成角色。

#### 5.1.4 奖品图与 KO 数学

策略显式使用：

- 双方剩余奖品；
- active HP、damage、能量；
- 对手是否需要多次攻击；
- 是否进入 60 HP 内的奖品转换窗口；
- Shadow Bullet 是否能绕过 ex 免伤并推进 Bench 奖品图；
- 应该保护一奖进化资源，还是多奖且已投入能量的攻击手。

业务证据：高水平 Alakazam 专家 258 场胜局中，220 场靠拿完奖品、33 场靠清空对方 Active，仅 5 场靠对手 deck-out。也就是说主胜法是奖品/场面转换，不是把对手磨牌磨死；因此 prize count、HP、KO clock 和 Active/Bench 目标价值比单纯 deck count 更承重。

#### 5.1.5 卡牌角色特征

domain_cards 不只记 card ID，还从官方卡表文本提取：

- 是否惩罚手牌数量；
- 是否阻挡 Pokémon ex 攻击伤害；
- 是否是可重复 draw/search/energy engine；
- 是否是 spread/damage-counter engine。

业务逻辑：规则应该对“角色”响应，而不是只为某个 replay 中的对手 ID 写补丁。例如面对手牌伤害型 Active，应先缩手；面对 ex 免伤，应切换到 bench spread 路线；面对慢速重复 draw engine，可以更早铺第二角色。

#### 5.1.6 未来资源预约与 deadline

ReservationLedger 与 DeadlineLedger 表示：

- 是否保留下一条 attacker base/final stage；
- 是否保留控制身体、控制能量、Froslass stage、Boss 终结手段；
- 何时 Rare Candy 已冗余；
- 必须本回合处理的奖品/锁、贴能、进化或资源压缩任务。

业务逻辑：TCG 的错误常不是当前动作价值低，而是提前花掉未来唯一可完成任务的资源。预约特征把“尚未完成的战略工作”变成硬约束，减少局部贪心。

#### 5.1.7 跨回合连续性

StrategicMemory 保存：

- 当前 objective 和持续回合数；
- phase 持续时间；
- 上回合和本回合最后 job；
- 被预约 Snorunt 是否仍存活；
- passive pressure campaign；
- 公开 card serial 首次出现、首次供能和首次进化时间。

业务逻辑：某一回合没有完成进化或第二攻击手，并不代表下一回合应该重置目标。连续性可以避免每个 decision point 都从零开始、在多个半成品计划之间摇摆。

#### 5.1.8 合法性特征和 fail-safe

最终动作必须满足：

- 选择数量在 minCount/maxCount 内；
- 下标唯一；
- 所有下标位于 option 范围。

不满足时回退到确定性合法选择。业务逻辑很直接：LB 中一次非法动作可能整局失败，合法性是高于策略增益的一票否决条件。

#### 5.1.9 结构消融结果

manual guards 与 hierarchy 不是装饰层。四腿 2×2 消融中：

- exact：加权 68.14%；
- hierarchy-only：54.38%，相对 -13.77pp；
- manual-only：64.69%，相对 -3.46pp；
- fallback-only：60.89%，相对 -7.25pp。

这说明完整结构的各层总体都在正贡献。单腿上 manual-only 偶有正向切片，但没有跨腿复现，因此没有在截止前做 matchup patch。

### 5.2 旧 BC/RL 表示：为什么看起来全面，仍然不够

旧 BC 输入由三块组成：

- 11 个 card-vocabulary bag：手牌、双方弃牌、我方牌组、双方 Active、双方 Bench、双方场上能量等；
- 90 个 scalar：HP/HP ratio、能量数、Bench/手牌/牌库/奖品、异常状态、turn、turnActionCount、每回合 flags、context/type one-hot、min/max count、剩余伤害和能量成本；
- 最多 64 个 option，每个 52 维：动作类型、区域、玩家、下标、目标、attack/card 等字段。

这些特征的业务方向是对的：

- zone bag 表示资源在哪里；
- scalars 表示奖品节奏、血量和每回合额度；
- per-option encoder 适应可变动作集合；
- 对手完整 deck 特征强制置零，避免用运行时不可见信息。

但它们把大量关系压平了。例如“场上有两颗暗能量”和“这两颗都在当前主攻手上”会得到相似 bag，却对应完全不同的攻击可用性；同样，option 的 source、target 和当前战略任务之间缺少显式交互。因此下一版不能只加 epoch 或宽度，应该优先加入：

- 卡牌实例级节点与 source-target 边；
- 进化、能量、工具、Active/Bench 关系；
- attack cost、可造成伤害与剩余 HP 的算术；
- turn 内动作序列和跨回合记忆；
- option 与 unfinished strategic job 的交叉特征。

### 5.3 Route-A 32 维 residual features

Route-A 没有从零接管策略，只在 exact-v22 给出的动作与最高安全 runner-up 分差不超过 25 时，尝试每局最多一次 override。32 维特征包括：

- turn、turn action count、先后手；
- 本回合贴能/Supporter/Stadium/retreat flags；
- 双方奖品、手牌、牌库、Bench；
- 双方 Active HP ratio 和能量；
- 我方 Impidimp/Morgrem/Grimmsnarl/Munkidori/Snorunt-Froslass 数量；
- exact 与 alternative 的 fallback score、绝对分差；
- alternative 是 play/evolve/attach/ability，以及是否与 exact 同 action type。

业务逻辑：只在两个规则动作本来就接近时学习情境优势，保留 v22 作为安全回退，并把探索限制为一次，避免学习器接管整局。

结果是健康的阴性：36,432 局、四腿各 9,108、零 fault，cross-fit uplift 仅 +0.1991pp，要求为 +3pp；只有 2/4 folds 同向，Alakazam 为 -3.8948pp。因此这些 features 没有进入最终提交。Router 腿 +3.64pp 只形成赛后 hypothesis，不能事后改闸追跑。

### 5.4 Matchup 特征：有潜力，但必须可见且可弃权

赛后可行性检查显示，用对手已公开打出的 card marker：

- 新 ref 盲验在 turn 2 覆盖 20/32，且 20/20 识别正确；
- Alakazam/Lucario 子集为 12/12；
- novel-deck 子集覆盖 10/18，命中的 10/10 正确。

这支持下一版做 high-precision abstaining router：识别到已验证 matchup 才切换，unknown/conflict 永远回 exact-v22。不能使用 replay 结束后才能知道的完整 60 卡标签，否则会再次制造 CV–部署泄漏。

## 6. 下一次比赛应采用的 CV v2

### 6.1 数据切分

- 以 episode 为最小切分单位，禁止同局决策跨 train/validation。
- fixed historical test 保持不可变。
- temporal canary 只追加，不在评估函数中自动刷新。
- 单独保留最新 live ref 作为 blind holdout；旧 ref 才能做 hypothesis design。

### 6.2 对手分层

- 按可见 archetype、对手 rating 桶、先后手和比赛时间分层。
- CV 权重同时报告 uniform、live-weighted 和 worst-leg，不只给一个加权均值。
- 对关键 archetype 使用真实公开策略或可执行近似 agent；只有牌表而没有 pilot 时，明确标注 equal-pilot。

### 6.3 实验设计

- 修复 native RNG，或引入 state clone/可重放 shuffle；在此之前只用独立二项试验。
- 每轮保留同批 incumbent control。
- 先做行为暴露闸，再做 W/L；触发为零或行为覆盖过广都提前停止。
- 候选通过独立 confirmation 和 n≥256 主闸后，才进入 exact-archive 验证。

### 6.4 模型表示

- 从 bag-of-cards 升级为 card-instance graph 或 set/attention encoder。
- 将 option 编码成 source-action-target 三元组，并与当前 objective、resource reservation 和 KO arithmetic 交叉。
- 将规则 v22 作为可解释 teacher、安全 fallback 和 feature generator，而不是直接用扁平 MLP 模仿它的全部字典序边界。

### 6.5 线上评估

- 永远按 ref 分开记录。
- 剔除 validation，报告 W/L、对手均分、matchup、Wilson 和 mu*。
- 不按新件早期 score 或单日 rank 调参。
- LB 只承担低频最终确认；如果 CV 与 LB 再次反向，优先审计版本、对手策略、数据泄漏和评分机制，而不是立即新增规则。

## 7. 最重要的经验

1. **测量仪器优先于候选。** runner 隔离、牌组锁、资源完整性和 replay 对齐，比多搜十个变体更值钱。
2. **牌组强不等于 pilot 强。** equal-pilot 牌组优势不能外推到真实 agent 天梯。
3. **动作 top-1 不等于闭环胜率。** 长时序环境中，少数关键错误会放大；终局 W/L 必须进入 CV。
4. **行为变化不等于收益。** guard 触发率和 replay 分叉只证明候选可测，不能替代对局结果。
5. **小样本尖峰默认是假设，不是结论。** 独立复验和预注册停止规则成功拦下了多次假 challenger。
6. **特征必须对应可执行的牌局工作。** 最有价值的特征不是更多 ID，而是奖品转换、进化/能量依赖、资源预约、动作先后和跨回合连续性。
7. **线上指标必须做对手强度与实例归属校正。** Glicko 分数、WR 和不同 ref 的轨迹不可混为一谈。

## 8. 主要证据索引

- [HANDOFF.md](../HANDOFF.md)
- [收口判读：real-deck/equal-pilot 与 live 差距](2026-08-12_收口判读.md)
- [Grim v22 交付、runner 污染与 exact-archive 复验](20260814_grim_v22_delivery.md)
- [天梯评分机制与对手强度纠正](20260814_ladder_scoring_mechanism_review.md)
- [v22 与 retreat 的同窗 live 比较](20260815_晨间分析.md)
- [on-policy residual ES 与 n=256 回归](20260815_v22_onpolicy_residual_rl.md)
- [live replay 0-mismatch、数值残差与四腿闸](20260815_live_calibration_and_dense_residual.md)
- [结构消融与剩余决策面](20260815_v22_remaining_surface_audit.md)
- [Route-A 36,432 局训练闸](20260815_routeA_training_kill.md)
- [最终 exact-v22 双槽提交](20260816_exact_v22_slot2_duplicate_submission.md)
- [实验 ledger](../experiments/ledger.jsonl)
- [最终 v22 policy](../candidates/grim_v22_final/policies/v22/main.py)
- [最终 v22 资源账本](../candidates/grim_v22_final/policies/v22/resource_ledger.py)
- [最终 v22 阶段与目标](../candidates/grim_v22_final/policies/v22/turn_objective.py)
- [BC replay 特征提取](../inference/dataset/extract.py)
- [Route-A 32 维特征](../experiments/routeA_policy.py)
