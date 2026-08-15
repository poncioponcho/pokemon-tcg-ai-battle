# Router 正切片归因与赛后预注册草案

时间：2026-08-15 19:22 CST
性质：Route A `TRAINING_KILL` 后的只读、事后假设生成；`winner=null`，不授权赛前追跑。

## 复现与总量结论

审计器从冻结的 36,432 局数据重新拟合“非 Router 三腿训练、Router held-out”模型，
精确复现正式结果：阈值 0.01、5,076 个 learning episodes、policy intervention rate
40.68%、IPS uplift `+3.6446pp`。正式 Router 全部 5,641 个 eligible episodes 的原始
随机 ATE 为 `+2.3860pp`，描述性 95% CI `[+0.0080,+4.7639]pp`。

这不推翻全局 `TRAINING_KILL`：v22 与 Alakazam folds 为负，跨腿整体仅 `+0.1991pp`。
Router 是唯一预先可见的正腿，但下面的内部切片全部是事后分析且未做多重比较校正。

## 正信号在哪里

### 回合

- `turn>=9`：1,728 局；原始 ATE `+4.7761pp`，IPS uplift `+6.7130pp`，对 Router
  总 uplift 的分解贡献 `+2.2853pp`。
- `turn5-8`：1,581 局；原始 ATE `+1.1323pp`，IPS `+4.9336pp`，贡献 `+1.5366pp`；
  区间仍跨零。
- `turn3-4`：贡献仅 `+0.0394pp`；`turn<=2` 反而贡献 `-0.2167pp`。

因此可检验的新假设是“Router 对手下的中后盘资源/目标分配”，不是开局改写。

### 动作形态

- ability→ability：1,339 局；原始 ATE `+4.6103pp`、IPS `+5.6759pp`，贡献
  `+1.4972pp`。
- attach→attach：1,454 局；原始 ATE `+2.8063pp`、IPS `+4.0578pp`，贡献
  `+1.1623pp`。
- evolve→evolve：1,248 局；原始 ATE `+1.0025pp`、IPS `+2.0833pp`。
- 81% 的 Router 样本为 fallback score 完全同分（gap=0）；该层贡献 `+3.2900pp`。

最合理的机制解释是：收益来自“同类、同分动作间的目标/次序选择”，尤其是中后盘 ability
和 attachment 的具体落点，而不是把一种动作类型换成另一种。模型 interaction 排名中的
turn、deck count、same-action-type 等高度相关，不能单独解释为因果权重。

## 赛后实验预注册草案 R1

### 假设与候选

- H1：当可见 matchup 被高置信识别为 Router/Great-Tusk 系，且 `turn>=9`、
  fallback gap=0 时，在同类 ability 或 attachment 选项中采用冻结的 safe runner-up，
  terminal WR 比 exact-v22 高至少 3pp。
- 候选仍每局最多一次 override；所有非目标状态、识别 unknown/conflict、异常和低覆盖状态
  永久回 exact-v22。禁止全局部署 Route A 头。

### 数据隔离

1. 本轮 36,432 局只用于提出 H1，永久列为 design set，不得进入确认集。
2. 另生成 Router-only 独立 randomized batch；固定 `turn>=9 + gap=0 +
   same-type ability/attach`，Z 在 episode 前分配，episode 为独立单位。
3. 第一阶段至少获得每臂 2,500 个 eligible episode；若实际 exposure 低于预估，则只增加
   预注册总局数，不改变状态条件。报告 raw ATE、cluster-at-episode CI 与 opportunity miss。
4. H1 只有在 ATE `>=+3pp` 且 95% CI 下界 `>0`、零 fault 时进入部署 W/L。

### 部署闸

1. Router 腿：候选对 exact-v22 同批 blocked-independent `n>=1024`，WR `>=54%`。
2. 跨腿回归：v22/Alakazam/Lucario/Grim 每腿 `n>=512`；任何腿 delta `<-2pp` 即 KILL。
3. matchup 识别必须使用另一份 deck-hash-grouped holdout，Router precision `>=95%`；
   unknown 一律 exact，禁止完整对手牌表特征。
4. 通过后仍只生成赛后 v23 challenger；不得追用本报告的单切片区间作为晋级证据。

## 证据

- 正式 JSON：`experiments/runs/routeA_router_slice_audit_v2_20260815.json`
- SHA256：`9aeed3d4c4ae21720c50393a3246b5462e3f91b56541b9551141b7600c72ccad`
- 首版 JSON 因一个极小 action-pair 只有单侧 Z 而产生 NaN 警告，已保留但判无效；v2 将
  不可估 raw ATE 明确记为 null，不影响总体或 `n>=200` 摘要。
