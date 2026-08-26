# 顶尖 pilot 行为 diff 方案（2026-08-12 17:40）

> 背景：真人级闸证明牌组层无油水（加权 0.840），live 0.476 缺口整个在 pilot 层。
> 排行榜证据：Laura +442/4-5h、Dipam +109.5/8h —— pilot 层大陆仍有人找到。
> 本方案 = 用他人公开 replay 做行为 diff，证据驱动攻 pilot 层。

## Step 1 可行性结论（已验证，2026-08-12 17:33）

- 排行榜行 live_tv 按钮 → Game History 面板，URL 带 `submissionId` / `episodeId`。
- `kaggle competitions replay <eid> -p <dir>` 可拉**任意** episode 完整 replay
  （样本 ep 92268635：7MB、244 步、双方视角 obs 含 current/logs/select/step、rewards/statuses 齐全）。
- `list_submission_episodes(任意 submissionId)` 可枚举他人 episodes（Sixth Sense 83 局实证）——
  **规模化枚举不需要浏览器**，webbridge 只需抠每人的最高分发 submissionId 一次。

## 目标池（已抠 submissionId）

| 选手 | 最高分发 submissionId | LB 分（瞬读） | 最近活跃 |
|---|---|---|---|
| Sixth Sense（Raja Biswas, /conjuring92） | 55439076 | 1228.5 | 16h |
| Dipam Chakraborty | 55449184 | 1227.3 | 5h |
| やる気元気ミワハルキ | 55449976 | 1218.7 | 4h |

（Laura 554? 待补抠——名字定位偶发失败，执行时按分数/行重试即可，非阻塞）

## Step 2 采样方案

- 每人 `list_submission_episodes` → 取**最近 ~25 局**（胜败混合，不挑——抗幸存者偏差：
  live_tv 默认给最高分发，只抄高光局会被坑）。
- 3-4 人共 ~75-100 局；对照组 = 已有 42 局 config A replay（`experiments/runs/live_replays/`），
  重点是我们的 22 局败局。
- 下载纪律：5s 基础限速 + 断点续拉（按 eid 存在即跳过，进程被 thermal/jetsam
  掐掉重跑不归零），产物 `experiments/runs/top_pilot_replays/`。
- 座位 sanity：参数化解析器写完后，对 Dipam / ミワハルキ 各先验 1 局座位定位
  （TeamNames 显示名完全匹配才进全量），再跑全量 diff——第六感 5/5 只证明单人生效。
- 镜像局：TeamNames 双同名 → flag，不进「us vs them」结论（#132 教训）。
- 存储：解析产出结构化事件后删 raw 7MB 原包（峰值 ~525MB，清完很小）。

## 解析与 diff 维度

复用 live_loss_analyze.py 的新鲜窗口规则（`lg != prev_lg`）+ `info.TeamNames` 定座位。
按决策类聚合频次/时机，每个维度算「他们胜局 vs 我们败局」的系统差：

1. prize mapping / KO 顺序（打谁、何时转火）
2. 能量挂载优先级（尤其 Solrock 引擎保护 vs 扩张）
3. retreat 时机与频率
4. Boss's Orders 使用时机 / 目标选择
5. 对墙（345）交互模式
6. 开局 T1 动作序列

输出 = 候选启发式清单（按出现频率 × 胜负相关性排序）。

## 决策树

- diff 露出**规则可移植**启发式 → 建候选 → 9 腿闸（嵌入 OFF 对照 + 同批 pristine A/B +
  |Δ|<2.2pp 当噪声）→ 加权 > config A +2.2pp 且用户点头才交。
- diff 本质是 NN/search 能力（纯规则复刻不了）→ 先对照「pilot 层选项地图」
  （08-12 附件）：①项目史上胜率 = 手搓启发式因子 + 卡组体系双轮，NN 顾问
  `_nn_consult` 混合架构已存在但 student canary 0.263 < 0.30 未过门、未进提交包；
  ②「小网 + expectimax 浅搜索」= 时间预算换容量的竞赛验证路线；③压缩/蒸馏/INT8
  与本项目瓶颈正交（提交无模型文件）。若差距落在可工程的浅搜索/估值维度 →
  评估该路线可行性再定；确属复刻不了 → 文档固化「天花板在 pilot 能力」，
  关线，收官路径不变。

## 时间盒与冻结

- 时间盒 ~8/15 晚：无具体可移植发现 → 关调查，收官路径不变。
- 提交冻结不变：5 次/日额度只花过闸候选，不为交而交。
- 不动：`9a7c7fda`（8/17 20:00 收官提醒）/ ledger `#135`（已预留，中间不插队）/
  `f6bd5dac`（观测哨）/ `530a9aba`（周报）。
