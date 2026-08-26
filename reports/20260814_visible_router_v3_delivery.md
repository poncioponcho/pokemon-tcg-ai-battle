# 2026-08-14 Visible Router V3 发射记录

状态：Kaggle `COMPLETE`；旧池 844.4 没有在当前池即时复现。该发射同时完成了
交付链路加固，并亲验推翻 `max(last-2)` 假设。

## 不可变交付件

- Kaggle ref：`55496233`
- 首分：`600.0`（随后初始漂移；4 局时 3-1，仅作瞬读）
- artifact：`artifacts/visible_router_v3/submission.tar.gz`
- archive SHA256：`860f26a614899ae52f1c89cb7b0a15737c209feb2321702ec4866a1f4f3b2590`
- `main.py` SHA256：`91f91c0d41381e33523ce47d4f771ecf2ed815dca9bf2b4f51a64a08e791e526`
- `deck.csv` SHA256：`6415396d35c0f4b3d69ee6c231337968cc9f2d5d0767de801346d6f412c18e62`
- Kaggle 入口：末尾 `competition_entrypoint`；普通 module 入口为 `agent`

公共 notebook 将完全相同的 main/deck 哈希绑定到历史 COMPLETE row `55056992`
（844.4，2026-07-28）。该 row 不属于本队，API 读取返回 403；可核证内容是公开 notebook
内的固定源码、牌组哈希和分数 receipt，不能把旧池分数当作当前池承诺。

## 本地官方引擎闸

- vs pristine config A：93-35 / 128，0 fault
- vs retreat pivot：76-52 / 128，0 fault
- vs Grimmsnarl v1：19-109 / 128，0 fault（明确硬克）
- vs Alakazam Codex v22：19-13 / 32，0 fault
- 最终 tar 在只含包内文件的目录中 8 局 self-play：0 fault
- 相同输入连续打包两次 SHA 完全一致

## 工程修复

1. `candidate_delivery.py` 在调用 agent 时保持 candidate cwd/sys.path，修复相对
   `deck.csv` 被仓库根文件污染的误判。
2. 普通 import `agent` 与 Kaggle 无 `__file__` 的 last-callable 两条入口均做 60 卡复验。
3. gzip 外层 `mtime=0`，补齐真正的字节级确定性打包。
4. 新增 `scripts/candidate_h2h.py`，可对任意候选目录/最终归档做官方引擎 H2H，双方
   fault 分开计数。

## live 结论与恢复

Router 完成后，官方完整 leaderboard 的本队行变成 600.1，时间戳精确对应 Router；
前一件 Grim 当时为 709.1，却没有保护团队榜。因此 last-2 只是活跃匹配集，榜分当前
关联最新有效件。为把已在当前池跑到 700.3 的策略重新放回活跃集，随后重交 retreat
精确原包为 ref `55496363`。恢复件首分 600.0，初始 2 局 1-1；个位数局不作效果判定。
