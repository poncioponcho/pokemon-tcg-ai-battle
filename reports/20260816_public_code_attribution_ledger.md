# Public-code attribution ledger

本文件是 2026-09-13 Hackathon writeup 的署名唯一真源；不改变任何已提交 archive。

> 2026-08-16 16:25：Roman/Jazivxt件已被第二个 exact-v22 挤出 final-2。以下署名仍
> 用于如实记录探索历史，但最终收敛成绩不得再归因于该件。

## 第三方公开组件

### Jazivxt — Codex Sol Eclipse Alakazam

- Kaggle ref：`jazivxt/codex-sol-eclipse-alakazam`
- 角色：最终 ref `55539395` 的实际策略与牌表上游作者。
- 本地源：`/private/tmp/ptcg-kernels-20260814/jazivxt/`
- main SHA：`f31eba2e819ee2b3d46765b4195ea7dab8f32d0b5d09cafd39b3823661f6b5aa`
- deck SHA：`8eccc69c3bf7d499f38c6116c33c5fac837050bf0ec71a5a1883f0f20f41ddbc`
- 许可依据：比赛规则 §3.6(b-c) 的 Kaggle competition public-code deemed license。
- 可声称：采用其公开策略作为 final-2 中的外部开源基线/上限票。
- 不可声称：策略、牌表、权重搜索或 Courage v22 是我方原创。

### Roman Rozen — Strong Start Baseline Agent V10

- Kaggle ref：`romanrozen/strong-start-baseline-agent-v10-lb-950`
- 角色：公开复包、发现入口和 `LB950+` 历史表现来源；不是本次源码的实际原创作者。
- notebook SHA：`3d49b09c4535743470db2ebcea35a7424ac0a88f02d81a79f152174146af55f2`
- 公开 metadata：`is_private=false`，competition source 为本比赛。
- 不可声称：其 notebook 的历史 LB950 是本队成绩或我方复现结果。

## 我方对 public Alakazam 的改动

- 仅在 `main.py` 导入行增加 `sys`，避免搜索异常回退路径触发 `NameError`。
- 静态 AST 字符串提取；未执行第三方 notebook。
- 60 卡、双入口、确定性打包、exact-archive 和 live runtime 验收。
- 提交 ref `55539395`；archive SHA
  `14dfb7666fc14c0fe16e5b9d5e843b0edcd4dd1187f06d22c5114d04e94a53fc`。

这些是工程与评估工作，不足以把策略主体描述为我方原创。

## 我方原创、可作为 writeup 主体

- exact-v22 Grim 策略及其结构化决策层。
- 候选隔离 runner、资产完整性与跨局状态污染修复。
- PUBLIC replay 的 next-step action 对齐与 0-mismatch 校准。
- 新提交高方差、对手强度偏置与隐含 `mu*` 纠偏。
- best-of-latest-2 受控实验与 final-2 风险编排。
- 预注册闸、阴性结果保留、局部残差 RL/guard/offset/结构消融。
- 动态 meta 下的高精度可弃权 matchup 识别与赛后规划。

## 写作底线

任何涉及 public Alakazam 的段落都应同时出现 Jazivxt 与 Romanrozen 的署名，并将本队
实际 ref、实际 W/L 与历史 notebook 标题分开。最终排名若由 ref `55539395` 扛分，
也只说明本队采用的公开组件在本队提交中取得该表现，不改变其作者归属。
