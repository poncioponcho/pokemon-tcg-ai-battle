# 2026-08-16 exact-v22 第二槽独立实例提交

执行时点：2026-08-16 16:25 CST。

## 结论

按用户明确批准，只提交了一发冻结 exact-v22。新 ref `55547740` 已 `COMPLETE`，
latest-2 已验收为：

- 新 exact-v22 `55547740`：600.0，COMPLETE；
- 成熟 exact-v22 `55539446`：841.5，COMPLETE。

Roman `55539395` 已按预期出槽。成熟 v22 仍在 latest-2，团队分地板没有因新件
`mu0=600` 被替换。

## 提交前证据

16:00 PUBLIC 数据：

- 成熟 v22：38 局 22-16，较 10:40 新增约 7-2；对手均分 826.96，校正
  `mu*=891.83`。
- Roman：37 局 19-18，较 10:40 新增 2-6；对手均分 757.07，校正
  `mu*=768.24`；对 Grim 累计 4-8。
- 08:04Z 全榜：6,845 队，本队 841.5/rank 681；rank 684 为 841.3。

因此 Roman 第二槽的 live 上行证据已经消失，而 exact-v22 同时有更强的新增战绩、
更硬的对手池和更高校正读数。再交一个 exact-v22 只挤出 Roman，不挤出成熟 v22。

## 冻结产物

- archive：`artifacts/grim_v22_final/submission.tar.gz`
- archive SHA256：`599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`
- main SHA256：`d80d33c570ba5dff445f3be60bcbd038598bd418eeb44c1120f3fbea893cba98`
- deck SHA256：`92b92bac9f9163ecff933b3dc39294d2cc154c8684f3c8497877661419ebc59d`
- manifest/60卡/双入口/copy-limit：PASS。

## 服务端回读

- 上传响应 ref：`55547740`。
- 文件大小：2,109,197 bytes。
- 描述：`exact-v22 duplicate slot2 | mature ref 55539446 retained | archive 599e19ae9c6f`。
- validation：COMPLETE，error_description=null。
- team-submissions：`[{55547740:600.0}, {55539446:841.5}]`。

## 绝对停止规则

本场之后禁止第二次成功提交。当天最后一发只允许在 ref `55547740` 或成熟 ref
`55539446` 出现 ERROR/失效时，使用同一冻结 SHA 做恢复；正常波动、低初始分或
Roman 后续历史分均不得触发提交。

## 20:52 运行时封盘验收

- 新 ref `55547740`：816.5，33 PUBLIC，17-16，COMPLETE。
- 成熟 ref `55539446`：837.1，42 PUBLIC，24-18，COMPLETE。
- latest-2 构成正确，smoke verdict=`HEALTHY`。
- `scripts/final_predeadline_watch.py` 已启动四轮只读采样；它不包含提交端点，输出写入
  `experiments/runs/final_predeadline_watch/`。
