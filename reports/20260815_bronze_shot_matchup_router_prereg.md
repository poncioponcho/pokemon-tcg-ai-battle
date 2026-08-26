# Bronze-shot：A/L 可见信息路由预注册

冻结时间：2026-08-15 19:45 CST（任何本候选 W/L 生成前）

## 目的与边界

目标不是宣称已有 +40–50 rating 的确定性改进，而是利用 best-of-latest-2：保留一件
exact-v22 托底，用第二槽购买一个带真实正向先验的上行期权。全流程只在本地生成新目录；
提交必须等全部闸结束后另行裁决。

## 冻结候选

- 来源：`candidates/grim_v22_final/`，tree SHA
  `0319fee37419983ad7137c1db9d1ac7d67024cc692eb495d73e6f46fedd12ecc`。
- 牌组、manual guards、history、StrategicMemory、合法性保护全部不变。
- 每局从 `UNKNOWN` 开始，仅累计当时公开的对手 active/bench/discard 及其公开
  preEvolution/tool/energy card IDs。
- Alakazam whitelist：`{741,742,743}`；Lucario whitelist：
  `{673,674,675,676,677,678}`。只使用公开 Pokémon 进化线，不使用完整牌表、ref、玩家名、
  结果或未来 state。
- 首次只命中一个 whitelist 后锁存 matchup；若两类都出现则 `CONFLICT`，永久回 exact。
- `UNKNOWN/CONFLICT/其他 archetype`：完整 exact-v22。
- `ALAKAZAM/LUCARIO`：manual guards 仍先执行；只有 manual 返回 `None` 时，绕过 hierarchy，
  调用冻结的 `validated_fallback_policy.choose`。这等价于“识别后 manual-only”，不是换牌、
  不是 NN/RL，也不修改 manual guard。

## 先验与诚实上限

结构消融中 manual-only 相对 exact：Alakazam `+6.25pp`、Lucario `+6.96pp`、Router
`0pp`，但 A 只有16局、L/Router各32局且均为独立批。82场 live meta 中 A/L 约38%，
点估计折算整体约 `+2.5pp`（约15–20 Elo-like rating），达不到铜牌缺口的确定性要求；
铜牌只能来自真效应高于点估计或最终 rating 路径的上尾。

## 行为闸

1. 冻结82场 replay：所有非 A/L gold episode 与 exact-v22 必须逐 action 0 mismatch。
2. A/L 必须在两 ref、两 seat 均有识别；至少12个 target episode 发生真实语义分叉。
3. 隐藏信息扫描静态审计通过；episode reset 后 latch 必须回 UNKNOWN。
4. deck=60、tree 源未变、0内部异常、override 额外 p99 `<1ms`。

## W/L 闸（native shuffle，blocked-independent）

- candidate 与 exact control 分别对同一 opponent 独立跑：Alakazam各128局、Router各256局、
  Lucario各256局；ABBA/BAAB只平衡座位，不称 paired/CRN。
- target live-weight proxy：Alakazam 0.71、Router 0.13、Lucario 0.16（只在 A/L 子池内归一化）。
- 进入打包条件：target proxy delta `>=+3pp`；Alakazam delta `>=-3pp`；
  Router/Lucario 合并 delta `>=0pp`；所有 candidate fault/internal error 为0。
- exact-v22 mirror 回归另跑 `n>=256`，candidate WR `>=48%` 且0 fault。该闸只防实现破坏，
  不把镜像噪声称为策略收益。

## 明日槽位规则

- 全闸 PASS：8/16 唯一一发改为 bronze-shot，锁定槽位 `{bronze-shot, ref 55516725 v22}`。
- 任一闸失败、未完成或需改 whitelist/路由规则：`winner=null`，按原 runbook 精确重交 v22。
- 无论哪条分支，都禁止第二发和现场改包。
