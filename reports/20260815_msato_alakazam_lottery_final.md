# M Sato 胡地彩票 v5：最终审计与冻结裁决

时间：2026-08-15 23:00 CST  
定位：`best-of-latest-2` 的第二槽高上限期权；不是 exact Grim v22 的替代品。

## 最终裁决

冻结 `alakazam_msato_imitation_v5_margin1`。它没有在本地证明强于 exact-v22，
但相对公开同牌表父策略存在可复现、统计上有方向性的 pilot 改进，而且专家来源本身有
榜首级上限。在保留 exact-v22 托底的前提下，v5 适合作为独立彩票提交。

- 认知层：**未证明 v5 强于 v22**。对 exact-v22 独立确认仅 42–86/128（32.81%）。
- 行动层：**第二槽值得买票**。同牌表公开父策略对 v22 为 25–103/128（19.53%）；
  v5 相对父策略提高 13.28pp，Fisher 双侧约 `p=0.0225`。
- 工程层：候选目录、确定性归档、解包归档三层均通过；累计 544 局工程/H2H 样本
  candidate fault=0、opponent fault=0。

## 专家上限与正确样本口径

教师仅取 M Sato 的胡地提交 `55198468`。后续 `55452060/55481866/55518190`
已经换成 Mega Froslass/Lopunny，全部排除，禁止混入胡地能力判断。

旧 ref 的 455 场公开对局为 258–197，WR 56.70%，对手均分 1032.84；按对手强度
校正的隐含实力约 1091.95，历史轨迹达到约 1183 的榜首级区间。分 matchup：

- Grimmsnarl：65–65/130，50.0%
- Alakazam 镜像：42–10/52，80.8%
- Crustle：9–3/12；Crustle+Cornerstone：12–1/13
- Froslass/Lopunny：43–38/81，53.1%
- Dragapult：13–16/29，44.8%
- Lucario：21–31/52，40.4%
- 其他：49–31/80，61.3%

因此，公开胡地候选在本地对 v22 只有约 20% 不是“胡地牌组必输长毛巨魔”的证据；
同一副牌在真实顶级 pilot 手中对 live Grim 已有 130 局、正好 50% 的直接证据。

权威原始数据：

- `experiments/runs/alakazam_msato_policy_audit_full455_v2_20260815.json`
- `experiments/runs/alakazam_msato_ref55198468_strength_20260815.json`
- `/private/tmp/alakazam_msato_replays/`（454 个可用公开 replay；另有错误 ref 被排除）

## 长局到底在做什么

455 场的官方 Result reason 为：奖品取完 389、对手无 Active 46、deck-out 20。
M Sato 的 258 个胜局中，220 场取完奖品、33 场清空对手 Active、仅 5 场靠对手
牌库耗尽；197 个败局中反而有 15 场是自己 deck-out。

结论：这不是磨牌获胜型胡地。`253/258=98.1%` 的胜局仍靠奖品交换、连续 KO 或
清空 Active。高回合数主要来自建立多级进化和持续资源循环，最终目标仍是兑现攻击；
把它训练成“拖到对手没牌”会学反。

## 从顶级 pilot 学到的差异

公开同牌表父策略 Marnie B 对专家动作的整体语义一致率约 59.1%，MAIN 仅约 39.7%，
Grim 状态约 50.6%。顶级 pilot 更早完成三件事：

1. 进化 Kadabra/Alakazam 与 Dudunsparce；
2. 贴能，为下一拍攻击提前付费；
3. 有窗口时直接使用 Powerful Hand 兑现，而不是继续铺 Poffin、Dunsparce、Poké Pad。

专家在所有有 `IS_FIRST` 记录的局中均选择先手（239/239 YES）。这说明差距是节奏与
目标选择，而非牌表本身或磨牌终局。

## 模仿训练与多臂漏斗

模型只用当时可见状态，为合法 option 做 pairwise score；任何低置信状态回退完整公开
规则/搜索父策略。不使用胜负结果、未来状态、隐藏牌表、team/ref 身份。

全量 v2 时间切分盲验：最新 91 局、3748 个 MAIN 决策；margin 0.25 时覆盖 66.81%，
覆盖内 exact 68.61%、semantic 68.97%；全接管 semantic 65.66%。动作保真不是 W/L，
因此随后全部用 native engine 独立裁决。

H2H 漏斗：

- 公开父策略：25–103/128，19.53%
- v1（146 replay）：12–52/64，18.75%
- v2 margin 0.25：16–48/64，25.00%
- v3 Grim router：17–47/64，26.56%
- v4 全接管：8–56/64，12.50%
- **v5 margin 1：screen 13–19/32；独立确认 42–86/128，32.81%**
- v6 margin 2：9–23/32，28.13%
- v7 margin 1 + switch：扩样 41–87/128，32.03%
- v8 Grim 胜局限定：7–25/32，21.88%
- v9 soft blend：10–22/32，31.25%

v5 是唯一经 n=128 独立扩样仍保持相对父策略提升的臂；继续调旋钮会把独立确认集变成
训练集，因此在此冻结。

## 跨 meta 与工程闸

冻结 v5 的既有 n=64 跨 meta：Lucario 43–21（67.19%）、Crustle 24–40
（37.50%）、胡地镜像 32–32（50.00%），全腿零 fault。

最终补量 n=40：exact Grim v22 11–29（27.50%）、Lucario 30–10（75.00%）、
Crustle 13–27（32.50%）、胡地镜像 21–19（52.50%），全腿零 fault。结果确认它是
明显 matchup-dependent 的高方差票，不是均匀更强的 baseline。

确定性归档解包后直接对 exact-v22 复验 13–19/32，candidate/opponent fault=0；
该数与候选目录首轮 13–19/32 相同。归档路径/相对资源/entrypoint 均无退化。

关键报告：

- `reports/20260815_alakazam_msato_imitation_v5_margin1_vs_exact_v22_confirm_n128.json`
- `reports/20260815_alakazam_msato_imitation_v5_margin1_crossmeta_n64.json`
- `reports/20260815_alakazam_msato_imitation_v5_engineering_fourleg_n40.json`
- `reports/20260815_alakazam_msato_lottery_v1_exact_archive_vs_v22_n32.json`

## 冻结物

- 候选：`candidates/alakazam_msato_imitation_v5_margin1/`
- 归档：`artifacts/alakazam_msato_lottery_v1/submission.tar.gz`
- archive SHA256：`83372cfecfe0308a129c9e11b87e4730fa204251ed23f8d8d599a8cf035993a9`
- main SHA256：`be951716ba3bd49aa86ed2e524e72fa8f3cac8799e6be2bf12db942eccfea505`
- deck SHA256：`0598646548d081832ec311c15fdc369b32c6f5e63175b0cfd1904d21fd082451`
- model SHA256：`eac2c69ac250298535db0066f93bd3ae644651461c85b80507b8659ccbc55f16`
- 归档大小：2,212,706 bytes；19 members；重复打包 SHA 一致

## 风险边界

v5 只学到了顶级动作分布的一部分，并且本地仍被 exact-v22 明显压制。它的上行故事是
“同一牌表的专家曾有榜首级实力，v5 已真实修复公开 pilot 的一部分”，不是“本地已经
证明铜牌”。最终槽位必须同时保留 exact-v22；若 v5 Kaggle validation ERROR 且同一
归档重试仍失败，立即放弃彩票，恢复双 v22。
