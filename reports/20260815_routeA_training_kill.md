# 路线 A 正式训练闸裁决：TRAINING_KILL

裁决时间：2026-08-15 18:48 CST
预注册：`reports/20260815_routeA_prereg.md` 及 `routeA_prereg_amendment1.md`

## 结论

路线 A 在首个下游统计闸被明确淘汰，`winner=null`。不运行 82 场 trained live
canary、四腿 screen、n≥256 main gate、materialize、打包或提交。8/16 唯一一发恢复为
精确重交 exact-v22；禁止先交 v22 再交任何实验件。

## 正式采集完整性

- 数据：`experiments/runs/routeA_collect_formal36432_20260815.json`
- SHA256：`ea7be6e7a948c211f132f4b6b79fee61c3b49743acc50861a60b026f380ce241`
- 36,432 局；v22/router/alakazam/lucario 各 9,108 局。
- Z=0/1 各 18,216；eligible 23,458；32 维特征完整。
- candidate/opponent fault 与内部异常均为 0；每局最多一次干预。
- 吞吐 2.950356 局/s；override p99 0.825084ms，均通过工程闸。

## Cross-fit 裁决

训练输出：`experiments/runs/routeA_train_formal_20260815.json`
输出 SHA256：`ae140f957cc5484d3fa417e1627e1e60d95b27053f2e9c029c54a71724feae65`

- held-out 总体 IPS uplift：`+0.1991pp`，要求 `>=+3pp`，失败。
- 同向 fold：`2/4`，要求 `>=3/4`，失败。
- 最差 fold：Alakazam `-3.8948pp`；虽未越过 `-5pp` 崩腿线，但不能抵消前两项失败。
- 分腿：v22 `-0.4885pp`、router `+3.6446pp`、Alakazam `-3.8948pp`、
  lucario `+1.6482pp`。
- 随机对照 calibration intervention rate 精确匹配（0.385496 vs 0.385496），因此
  淘汰不是对照率失配造成。

原始随机处理的未建模均值差也支持同一方向：v22 `-0.46pp`、Alakazam `-1.05pp`、
Lucario `+0.40pp`、Router `+2.39pp`。安全 runner-up 干预只在 Router 腿出现局部收益，
没有形成跨对手可部署优势。

## 停止纪律

训练程序以退出码 2 和 `TRAINING_KILL` 正常结束。按预注册停止规则，不因 Router
切片为正而重训、改特征、改阈值、追加桶或继续 W/L；这些属于赛后新实验，而不是本次
pilot 的合法 continuation。exact-v22 tree SHA 仍为
`0319fee37419983ad7137c1db9d1ac7d67024cc692eb495d73e6f46fedd12ecc`。
