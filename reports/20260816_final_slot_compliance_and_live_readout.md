# 2026-08-16 最终槽位：合规与 live 成绩联合裁决

> **16:25 后续覆盖：** 16:00 新数据为 v22 新增约7-2、Roman新增2-6；用户随后批准
> 用一发冻结 exact-v22 替换 Roman 槽。当前 final-2 已为
> `{55547740新v22,55539446成熟v22}`，详见
> `reports/20260816_exact_v22_slot2_duplicate_submission.md`。本文保留为10:40时点审计，
> 其中公开代码许可与署名结论继续有效。

采样时点：2026-08-16 10:40 CST。截止：2026-08-17 07:59 CST；07:30 后禁止改槽。

## 裁决

**KEEP：`{55539395 public Alakazam, 55539446 exact-v22}`；本轮不提交。**

剩余两发只作为工程故障恢复额度，不再执行 `M Sato -> exact-v22` 回退。M Sato 的
同快照 live 证据明显弱于当前两件；Roman/Jazivxt 公开代码的使用权则已由比赛规则
§3.6(b-c) 闭合。短期仍不能宣称 public Alakazam 强于 v22，但它是第二槽里上限和
meta 互补性最好的现成票。

## 同一排行榜快照

完整榜单快照：`2026-08-16T02:34:25Z`，6,838 队。

- 团队：802.8，rank 924。
- 约 top-10% 铜牌线：rank 684，839.3；当前差 36.5 分。
- ref `55539395`：784.2。
- ref `55539446`：802.8。

逐局对手强度校正（Elo 期望方程反解；不是 Kaggle Glicko 状态重建）：

- public Alakazam `55539395`：29 PUBLIC，17-12，WR 58.62%，Wilson 95%
  `[40.74%, 74.49%]`；对手均分 754.88；隐含 `mu*=822.00`。
- exact-v22 `55539446`：29 PUBLIC，15-14，WR 51.72%，Wilson 95%
  `[34.43%, 68.61%]`；对手均分 812.22；隐含 `mu*=829.58`。
- M Sato v5 `55537313`：21 PUBLIC，9-12，WR 42.86%；对手均分 739.01；
  隐含 `mu*=677.43`。

Roman/Jazivxt 与 v22 的校正读数只差 7.58 分，样本区间大幅重叠，不能认知层宣称
前者更强。M Sato 则同时在裸分、WR、对手强度和校正值上落后，回退会降低第二槽
上限。

## 公开回放分解

public Alakazam 的 29 场全部完成，未见 runtime/timeout/fault；2,148 次决策对本地
归档策略的动作复现率为 96.65%。非 100% 主要受搜索层私有 RNG 影响，不构成运行时
故障证据。

- vs Alakazam：4-1。
- vs Lucario：4-0。
- vs Grimmsnarl：3-6。
- vs Crustle（不含 Cornerstone 混合）：2-0。
- vs Froslass/Lopunny：0-2。

它的主要 live 风险是 Grim，而不是“靠把双方牌库磨空”：29 场只有 1 场以 deck-out
结束，且是我方在 turn 24 被 Crustle/Cornerstone 磨空后落败。另有一场我方牌库
归零但先拿完奖品获胜。exact-v22 同期 29 场 15-14、对手明显更强；已审计的前 28
场 2,605 次 ACTIVE 调用对归档 v22 为 0 mismatch。

## 代码来源与比赛许可

源码比较结果：

- 上游实际代码作者/公开源：`jazivxt/codex-sol-eclipse-alakazam`。
- 发现与历史表现来源：`romanrozen/strong-start-baseline-agent-v10-lb-950`。
- Roman notebook 提取出的 `main.py` 与 Jazivxt `main.py` SHA 均为
  `f31eba2e…f6b5aa`，牌表 SHA 均为 `8eccc69c…1ddbc`。
- 我方运行时代码只增加 `import sys`，当前 main SHA `c1b2ee3f…cfe9c`；策略主体
  不应、也不会被描述为我方原创。

官方规则 §3.6(b) 允许在本比赛 Kaggle forum/notebook 向所有参赛者公开 Competition
Code，并规定发布者因此被视为已按“不限制商业使用的 OSI-approved license”授权；
§3.6(c) 明确允许使用满足该条件的开源代码。两个上游 metadata 均为
`is_private=false` 且 `competition_sources=[pokemon-tcg-ai-battle]`，满足公开范围。

规则 §3.14 的原创性/权利保证仍要求不能冒充作者或侵权。因此最终口径是：**允许
作为公开开源组件使用，但必须完整署名，不得将其策略、牌表、LB950 历史表现写成
我方原创。** 这是基于官方比赛文本的高置信合规判断，不替代主办方的最终解释。

## Writeup 口径

- 第三方部分：明确署名 Jazivxt（策略与牌表）和 Romanrozen（公开复包与历史 live
  证据），只写“采用公开组件作为一张 final-2 上限票”。
- 我方原创部分：exact-v22、隔离 runner 修复、live replay 0-mismatch 校准、对手强度
  纠偏、best-of-latest-2 受控实验、提交槽位/回退编排、预注册阴性实验，以及动态
  meta 下的可弃权 matchup 识别。
- 禁止：把 notebook 标题的 `LB950+` 写成我方成绩；把 Jazivxt 策略讲成我方发明；
  用公开代码表现替代本队 ref `55539395` 的实际结果。

## 操作纪律

1. 当前不提交，保留两发应急额度。
2. 后续只读监测分 ref 的 W/L、对手均分、`mu*` 和 runtime 状态；不按单次分数尖峰追单。
3. 仅当任一 current ref 进入 ERROR/失效，才按冻结归档恢复；否则 07:30 封口。
4. 截止后两周继续采样，writeup 只引用最终收敛后的本队 ref 表现。

## 证据文件

- `experiments/runs/roman950_ladder_strength_20260816_1040.json`
- `experiments/runs/v22_restore_ladder_strength_20260816_1040.json`
- `experiments/runs/msato_v5_ladder_strength_20260816_1040.json`
- `experiments/runs/roman950_live_replay_audit_20260816_1023.json`
- `experiments/runs/v22_restore_live_replay_audit_20260816_1023.json`
- `candidates/roman_alakazam_courage_v22_public950/source_manifest.json`
