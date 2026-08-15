# v22 精确重交与 Q1 榜单语义观测

时间：2026-08-15 CST
状态：Q1 已结案；+60 分钟复核已由 Kimi 于 +84 分钟补采封口（见下）。

## 提交物与提交前快照

- 归档：`artifacts/grim_v22_final/submission.tar.gz`
- SHA256：`599e19ae9c6f5f09160565a9ffb0f3662062bde921dd196ad20c81f6b4c8bfcf`
- 原 v22：ref `55499962`，public score `823.2`
- recovery：ref `55496363`，public score `581.3`
- 提交前团队榜：rank `789`，score `823.2`，submission count `2`

## 执行

- 2026-08-15 08:46:33 CST 精确重交原包成功。
- 新 ref：`55516725`
- API 状态：`COMPLETE`，无 error；归档大小 `2,109,197` bytes。
- 新 latest-2：`{55516725 新 v22, 55499962 旧 v22}`；弱 recovery 已出槽。

## Q1 观测

### validation / 即时

- 新 v22 individual score：`600.0`
- 旧 v22 individual score：`823.2`
- 团队榜：rank `788`，score `823.2`，榜行日期已更新为 `2026-08-15 00:46:33 UTC`
- 初判：支持 best-of-latest-2；仍需排除异步刷新。

### +5 分钟

- 新 v22 individual score：`498.8`
- 新 v22 episodes：2（validation W + 公开局 L），public-only `0-1`
- 旧 v22 individual score：`823.2`
- `team-submissions` 已明确返回新件 `498.8` + 旧件 `823.2`
- 团队榜：rank `786`，score 仍为 `823.2`，榜行日期仍是新件日期
- 判定：平台已经接纳并更新新 submission，但团队分选择最新两件中的最高分；这不是 latest-only，也不是单纯榜单未刷新。

### +15 分钟

- 新 v22 individual score：`702.8`
- 新 v22 episodes：5（validation W + 公开局 `3-1`）
- 旧 v22 individual score：`823.2`
- `team-submissions`：新件 `702.8` + 旧件 `823.2`
- 团队榜新鲜快照：生成于 `2026-08-15 01:02:32 UTC`，rank `788`，score 仍为 `823.2`
- 判定：在新件自身从 `498.8` 变化到 `702.8` 的过程中，团队榜持续取旧件 `823.2`；Q1 已可结案为 `best-of-latest-2`。

### +60 分钟（Kimi +84 分钟补采，2026-08-15 10:10 CST）

- 新 v22（`55516725`）individual score：`796.9`（沿 +5→+15 的 498.8→702.8 轨迹继续爬升）
- 旧 v22（`55499962`）individual score：`829.4`（自身也在缓慢爬升，823.2→829.4）
- 团队分应为 `max(796.9, 829.4) = 829.4`，与 best-of-latest-2 语义一致；新件全程未拖累团队分
- 判定：与 +5/+15 结论一致，无反转迹象；Q1 观测封口

## 当前结论

Q1 已结案：leaderboard 展示 `best-of-latest-2`。+60 分钟缺口已由 Kimi 于 +84 分钟补采封口，结论不变。
