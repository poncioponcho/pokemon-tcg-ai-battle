# 路线 A：单干预 on-policy advantage pilot 预注册

冻结时间：2026-08-15 13:28 CST
授权：用户明确回复“开工路线A”
性质：deadline-bounded randomized contextual-bandit；规则在正式 W/L 数据生成前冻结。

## 不可变对象

- Incumbent：`candidates/grim_v22_final/`，tree SHA256
  `0319fee37419983ad7137c1db9d1ac7d67024cc692eb495d73e6f46fedd12ecc`。
- 线上归档：SHA256
  `599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`。
- 不修改 incumbent、现有两个 live ref、Automation 或提交工具。

## 干预协议

1. 仅包装 `policies.v22.main.choose`：manual guard 返回 `None` 后才会到此挂载点；
   仅 `context==0`；hard legality guard、select/protocol、StrategicMemory 和每局
   `select=None` reset 保持原样。
2. 每局在开局前均匀预分配四个 turn bucket 之一：`turn<=2`、`turn3-4`、
   `turn5-8`、`turn>=9`；并按确定性平衡日程预分配 `Z∈{0 exact,1 alternative}`。
3. 到目标桶首次出现 eligible state 时记录一次。`Z=0` 走 exact；`Z=1` 走
   alternative；此后本局永久回 exact。没有 eligible state 的局只记 opportunity miss，
   不伪装成独立 treatment 样本。
4. alternative proposer：在 exact-v22 的 context-0 semantic options 中，按现有
   `validated_fallback_policy.main_score` 取评分最高且与 exact 语义不同的 singleton。
   排除 `end_turn`、`retreat`、`attack`、Boss、非 singleton/malformed option；并要求
   exact/alternative 的 fallback-score 绝对差不超过行为阈值。
5. 行为阈值只允许从固定网格 `{25,50,100,200,300,500,800,1200}` 选择。旧 live ref
   只用于按“最小阈值使首次 eligible episode 进入 8–33/50”选值；新 ref 32 局盲验必须
   有 `3–13/32` 覆盖，合并 82 局必须 `8–33/82`。不满足即 `BEHAVIOR_KILL`，不得靠
   观看 W/L 后换 proposer 或扩网格。

## 固定特征与模型

- 只读取当时 observation 可见信息；禁止完整对手 deck、ref、结果、未来 state。
- 32 个特征固定为：turn、turn-action-count、first-player-relative、四个 turn flags、
  双方 prize/hand/deck/bench 规模、双方 active HP 比例与能量数、我方六组核心 board
  计数、exact/alternative fallback score、绝对 score gap、alternative 四类动作
  one-hot、exact/alternative 是否同类。连续值按预注册常数裁剪归一化。
- 训练为 L2 logistic response model：base features + `Z` + `Z×features`；部署时计算
  `p(win|Z=1)-p(win|Z=0)`。不允许神经网络、搜索、在线更新或 >32 特征。
- episode 是唯一独立样本；训练/验证按 episode，四个 executable opponent legs
  做 opponent-held-out cross-fit。部署每局仍最多一次 override。

## 数据与评估

- Smoke：约 1,000 局，四腿等量、桶与 treatment 平衡；只测协议/吞吐/fault，不用于
  选模型或报告收益。
- 正式随机化批上限 36,432 局；四腿等量收集，实际 eligible 样本与 exposure miss
  分开报告。数据只生成一次，不因结果追加有利桶。
- held-out policy value 用 0.5 propensity 的 episode-level IPS 估计；要求整体 uplift
  ≥+3pp、至少 3/4 held-out opponent folds 同向、任一 fold ≥−5pp。
- 决策阈值只能在训练 folds 上按预注册候选 `{0,0.01,0.02,0.03,0.05,0.08}` 选择，
  目标是最高训练 IPS uplift；held-out fold 只裁决，禁止调参回看。
- random-init control 使用同一架构、proposer 与 calibration states；通过阈值调节使
  intervention rate 与 trained head 差 ≤2pp。

## 硬闸

- Wrapper smoke：每局 ≤1 次干预、Z 比例 48–52%、四桶各 23–27%、0 candidate fault、
  吞吐 ≥1局/s、override 自身 p99 <1ms。失败即 KILL。
- Live behavior canary：旧/新 ref、两 seat、胜败均有覆盖；合并首次分叉 8–33/82。
- 四腿 screen：相对同批 exact incumbent 加权 ≥+3pp、v22 主腿 ≥53%、任一跨牌组腿
  delta ≥−10pp、trained 相对 matched-random ≥+3pp、0 fault。
- exact-v22 main gate：`n≥256`、candidate WR ≥55%、相对同批 incumbent ≥+3pp、
  0 fault。未过不 materialize、不打包、不提交。

## 时间与提交

- 17:00 wrapper/invariants；19:00 smoke；8/16 05:00 正式批+训练；07:00 canary/control；
  10:00 screen；12:00 main gate/归档。
- 8/16 只交一件：全闸 PASS 则交 RL；否则精确重交 v22。禁止同日先交 v22 再交 RL，
  以免成熟 v22 被两张新件挤出 latest-2。

## 停止规则

任何闸失败、绝对时间超限、baseline hash 改变、需要更换 action proposer/特征空间、
或需要多次干预/局时，立即 `winner=null` 并将路线 A 归档赛后；不得降闸追跑。
