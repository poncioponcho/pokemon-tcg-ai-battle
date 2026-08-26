# Kaggle 状态日报 2026-08-08

- 生成时间: 2026-08-08 09:00:20 +0800

## 本地产物

- model_student.npz: 尚未产出（在线训练中或未下载）
- 最近训练报告: teacher_canary_top1=0.40542602797795674 student_canary_top1=0.39974565493853326 device=cpu

## 磁盘

- 75Gi 可用 (83% 已用)

## Kaggle 提交状态

- 最新提交: **complete** | 分数 379.3 | 2026-08-07T00:59
  描述: PTCG Agent v23.1 P1策略调优+bug修复 2026-08-07_08:59
- 最近 5 条提交中 **4 条失败**（最近: Validation Episode failed.）
- 最近完成分数: 379.3（历史共 19 条完成）


---

## 晚间更新（18:55，人工复盘后执行）

> 日报正文 379.3 已过时。以 CLI 实测为准：

| 提交 | ref | 状态 | 分数 | 说明 |
|------|-----|------|------|------|
| v23.1 (08-07 00:59) | 55310444 | COMPLETE | 396.7 | 日报生成后又结算，379.3 → 396.7 |
| **v23.2 规则版** (08-08 18:29) | **55347848** | COMPLETE | **373.6（08-09 08:41 +0800 结算回读；昨日瞬读 561.6/483.0/399.1 不作数）** | 内容=根 main.py sha a7cd741458121fd1（含 _nn_consult，即 v23.2）；描述串误写 v23.1 是 submit.py:153 硬编码；不含 model_student.npz |
| NN 首次修复尝试 (18:39) | 55348046 | ERROR | - | 仅修 deck 兜底，未修 __file__，预期失败 |
| **NN pure-python 首得分** (18:49) | **55348242** | COMPLETE | **240.8（08-09 08:41 +0800 结算回读；昨日瞬读 382.2/240.7/181.1 不作数）** | __file__+deck 双修复后 NN 路线首次过 validation |

> 08-09 08:41 +0800 结算回读：55347848=**373.6**，55348242=**240.8**（`kaggle competitions submissions` 实测，详见 kaggle-daily-2026-08-09.md）。

> 教训：模拟赛道分数随对局结算持续漂移数小时，瞬读不可记账；记账以结算稳定后（次日）为准。

### NN validation 失败根因（6 连 ERROR）

Kaggle harness 以 exec 方式加载提交源码，**无 `__file__`**；NN main.py 顶层
`_BASE = os.path.dirname(os.path.abspath(__file__))` 抛 NameError → import 即挂。
champion 幸存是因为它的 `__file__` 调用在 try/except 内（内联牌组兜底）。
修复：`_BASE` 加 try/NameError 兜底 + deck.csv 读取失败回退内联牌组。
已同步修复 build_pure.py 模板（防未来重建复发）。

### bcrl 自动循环修复

- exit=127 根因：launchd 默认 PATH 不含 /opt/homebrew/bin → plist 加 EnvironmentVariables.PATH
- 第二根因：opencode ≥1.18 要求 `run` 必须带 message → launcher.sh AR_CMD 补提示词
- 18:25 手动触发验证：opencode 持续运行，无 127/ABORT，循环已恢复
