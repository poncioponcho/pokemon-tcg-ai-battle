# Grim v22 截止赛交付报告

状态：**READY FOR LIVE（尚未提交 Kaggle）**。8/15 的 challenger 定版为 Grim
固定牌组 + v22 纯规则 pilot；v28 和 v29 不再晋级。

## 定版依据

修复 `candidate_h2h.py` 的跨候选 `sys.modules` 污染后，以同一批 n=64
重新比较 v22 与 v28：

- 对锁定 retreat baseline：v22 42-22（65.6%），v28 43-21（67.2%）；近似持平。
- 对完整 Grim v1：v22 39-25（60.9%），v28 28-36（43.8%）；这是方向性证据，
  n=64 单批本身不宣称显著。
- 对 Router：v22 38-26（59.4%），v28 39-25（60.9%）；近似持平。
- 原独立 Alakazam n=128 腿为 v22 82.0%、v28 75.0%；修复后又用最终解包件
  独立补跑 n=64，v22 为 51-13（79.7%）、零 fault，旧仪器来源风险已结清。

### v29 复核

review 指出 v29 淘汰可能依赖未知 meta 权重后，使用修复后的 runner 重开一次裁决：

- n=64：retreat 45-19（70.3%）、完整 Grim 33-31（51.6%）、Router/Crustle
  41-23（64.1%），全部零 fault。旧的 Grim 60.9% 不再使用。
- 同一 Grim deck 直接对 v22：首批 n=128 为 74-53-1（58.3%），独立复现
  n=256 为 134-122（52.3%）；合并 decisive 383 局为 208-175（54.3%），
  Wilson 95% 约 49.3%-59.2%，仍包含 50%。
- live 池已识别权重为 Alakazam 26.8%、Lucario 17.1%、Crustle 17.1%、
  Grim 9.8%。只汇总未受污染批次，v29 在这 70.7% 已覆盖权重上相对 v22
  约 **+0.27pp**，远小于本地无配对噪声带；其余 29.3% 没有对应闸。

因此 reviewer 的“不能按旧数据早杀 v29”成立，但补证后的结论仍是不足以覆盖 v22：
已知加权近似平手、直接 H2H 区间跨 50%，而 v29 多一层状态路由和未覆盖腿。
行动层保留更简单、证据闭合且已完成 exact-archive 的 v22；认知层不宣称 v22
显著强于 v29。

本地官方引擎没有暴露 native shuffle seed；CLI 的 `--seed` 只控制 Python
侧随机 agent。因此同 seed 重跑是独立批次，不是逐局重放。本报告以多批一致方向
判结构性崩腿，不把单批点估计当精确真值。

## 交付修复

本轮发现并修复两项会制造假结论的问题：

1. 多个候选都使用顶层包名 `policies`，旧 H2H runner 会让双方共享模块和状态。
   runner 现为每个 `CandidateAgent` 保存并切换私有模块缓存；净包对完整 Grim 的
   隔离冒烟已通过。
2. v22/v28 的规则运行时会读取根目录 `EN_Card_Data.csv`。旧净包漏带该文件，
   异常又会被组合 policy 吞掉并静默退化。最终包已带卡表，并从解包目录实读
   card 646 = `Marnie's Impidimp / Basic Pokémon / 70 HP`。

## 最终归档

- artifact：`artifacts/grim_v22_final/submission.tar.gz`
- archive SHA256：`599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`
- main SHA256：`d80d33c570ba5dff445f3be60bcbd038598bd418eeb44c1120f3fbea893cba98`
- deck SHA256：`92b92bac9f9163ecff933b3dc39294d2cc154c8684f3c8497877661419ebc59d`
- 60 个 regular members，含官方 `cg/`、60 卡 deck、完整卡表和 v22 policy。
- 双入口、卡组合法性、启动探针全部 PASS。
- 两次独立打包 SHA 完全一致。

## Exact-archive 复验

从上述归档解包后直接运行：

- self-play 8 局：零 candidate/opponent fault（胜负不作为强度证据）。
- n=32 四腿：retreat 20-12（62.5%）；完整 Grim 22-10（68.8%）；
  Router 18-14（56.3%）；Alakazam 24-8（75.0%）；全部零 fault。
- 较大独立隔离批 n=64：retreat 42-22、完整 Grim 39-25、Router 38-26；
  全部零 fault。
- 最终解包件对 Alakazam 的修复后独立 n=64：51-13（79.7%），零 fault。

证据文件：

- `reports/20260814_grim_v22_isolated_confirm_n64.json`
- `reports/20260814_grim_v22_exact_archive_selfplay_n8.json`
- `reports/20260814_grim_v22_exact_archive_fourleg_n32.json`
- `reports/20260814_grim_v22_exact_archive_vs_alakazam_isolated_n64.json`
- `reports/20260814_grim_v29_isolated_confirm_n64.json`
- `reports/20260814_grim_v29_vs_v22_isolated_n128.json`
- `reports/20260814_grim_v29_vs_v22_isolated_n256_replicate.json`
- `artifacts/grim_v22_final/submission.tar.gz.manifest.json`

## 测量纪律（本轮新增）

1. 报告必须记录 runner SHA、候选 main/deck SHA、模块隔离版本和 seed 作用域。
2. 旧结果若双方共享顶层包名，默认失效；只有能证明对手没有同名包、且候选状态在
   每腿重置的腿，才可标注后继续使用，禁止无说明混池。
3. `zero fault` 不是交付通过：必须从最终 tar 解包，实读运行时资产，再跑双入口、
   self-play 和跨牌组腿。被吞异常的备用 policy 也算交付失败。
4. native engine 不可播种，同 seed 不是配对重放；小于约 2.2pp 的差异按噪声处理。
5. 瞬时 leaderboard 峰值只记轨迹，不作为候选排序证据。

## 线上 incumbent 的诚实读法

retreat 恢复件 `55496363` 截至 13:48 的读数为 650.7、28 局 15-13（53.6%）。
与旧同代码探针 `55468450` 合并为 76 局 42-34（55.3%，Wilson 95% 约
44.1%-65.9%）；config A 为 42 局 20-22（47.6%）。点估计差 +7.6pp，但差值
区间仍跨 0。
因此最新提交是可用且方向偏正的 incumbent，不足以宣称已证明大幅提升。

## 发射与收官

- 8/14 不再提交；今天已有真实发射，保留最后额度处理意外。
- 8/15 确认日配额重置后尽早（目标 08:05 CST）提交上述唯一归档；20:00
  改为首轮 live 盘点，不再等到晚上才发射。
- 8/16 仍执行用户的“每天 1-2 次”硬约束：只在 v22 与 retreat 两个完整归档中，
  重交当时后验最强的一件；禁止全新变体。分数改进无法保证，但必须得到真实可见反馈。
- 8/17 07:59 前最后有效提交必须是累计证据最强的归档；平台按最新有效提交计榜，
  不存在 `max(last-2)` 地板。

### 8/16～冻结 tie-break（写死）

候选集合只允许 `{v22 final, retreat exact recovery}`：

1. `ERROR`、validation fault 或 SHA 不符的件直接剔除。
2. 两件均至少 20 个 scored episodes 时，live WR 差 **≥3pp** 取较高者。
3. WR 差 `<3pp`，或任一件 `<20` 局时，取 scored episodes 较多者；局数相同再取
   Wilson 下界较高者，仍同档则取 retreat（历史测量更充分）。
4. public score 只在以上指标仍完全同档时作末级 tie-break，禁止按瞬时峰值追单。
5. 8/16 为满足每日提交，只重交按上述规则选出的同一精确归档；8/17 冻结前不再发
   全新代码或牌组。
