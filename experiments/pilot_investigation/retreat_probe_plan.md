# retreat live 探针执行方案 (备份·待用户拍板才执行)

> 状态: **BACKUP — 未授权不执行**。advisor 2026-08-12 20:32 定稿, 我落成文件。
> 默认路径是 (a) 收线; 本文件仅当用户明确想烧 1 提交额度时启用。

> **执行覆盖（2026-08-14）**：上面的“收线/WR>0.62 才行动”是历史 pilot
> 假设，已被当前截止约束和跨策略交付流程覆盖。行动层采用“通过安全闸即进入
> live 排名”，认知层仍保留 `WR>0.62` 的显著性阈值；不得以未显著自动阻止
> 每日真实提交。跨策略候选优先于本文件中的单 flag 翻牌。

## 背景

pilot 调查两发候选均本地闸 NO-GO 但证无害:
- nrg_bench: 加权 −0.09pp, regression 全过, invalid 0
- retreat_pivot: 加权 −0.50pp, regression 全过, invalid 0 (半可见闸, Grimmsnarl 触发 0.75/局)

结构性发现: first-pilot 闸对 pilot 质量改进已达灵敏度天花板 (本地加权 0.92 贴顶,
live 0.476 缺口全在 first-pilot 不会做的事上)。闸能证无害、证不了有益 →
唯一剩余仲裁 = live 实测。

## 铁律一: live 实测统计功效极弱 (最主要的反 (b) 论据)

- #132 n=42 下 WR 二项 σ ≈ 0.5/√42 ≈ **7.7pp** (不是 2.2pp——那是 n=1000 量级)。
- 匹配速率 ~1 局/小时 → 8/14 交到 8/17 截止仅 ~50-72 局, σ 仍 ~6-7pp。
- 含义: 探针即便真有效也大概率检不出; flat 也证伪不了 (功效不足 = 假阴性)。
  只有 WR 跳动 >15pp (>0.62) 才可能显著, 而本地闸 −0.5/−0.09pp 暗示真效应本就小。
- 连带: 0.476 这个 live 真值锚本身有 ±15pp 误差棒,「缺口 36pp」只方向性非定量。

## 铁律二: 归因 — RETREAT_PIVOT 单发为首选探针

- **首选: RETREAT_PIVOT 单发** (半可见、−0.50pp 方向性最近、advisor 点名的最干净载具)。
- 备选: NRG_BENCH + RETREAT_PIVOT 捆绑 (kitchen-sink) — 标注: live 动了无法归因到哪个。
- flag 态 (首选): `FLAG_DYING_674=False, FLAG_NRG_BENCH=False, FLAG_RETREAT_PIVOT=True`
- flag 态 (备选): `FLAG_DYING_674=False, FLAG_NRG_BENCH=True, FLAG_RETREAT_PIVOT=True`
- 核实: `grep -n 'FLAG_' submission_baseline/main.py` 确认三标识符后再打包。

## 铁律三: 交前先跑合并配置 regression 闸 (仅备选捆绑需要)

- 两未认证改动叠加有无害交互风险。用 ON=两 flag 都 True 跑一次全 9 腿闸
  (复制本目录 merge_gate_retreatpivot.py 改 ON 态), **只验证无腿 ON−pristine < −2.2pp 且 invalid 0**,
  不指望 >+2.2pp。单发探针跳过此步 (retreatpivot 闸已跑过)。

## 执行清单 (拍板后按序)

1. 核实 flag 标识符 (铁律二 grep)。
2. (仅捆绑) 合并配置 regression 闸过 (铁律三)。
3. 构建 artifact: submission_baseline/ 内设好 flag 态 →
   `COPYFILE_DISABLE=1 tar -czf submission.tar.gz main.py deck.csv cg` →
   净环境 import 冒烟真执行 agent → deck.csv 硬断言 == dsh._baseline_deck()。
4. 提交, 耗 1 额度, 记 ledger: 标「live 探针, 非闸过候选」。
   **last-2 影响**: 顶出 config A v1 (55431232), last-2 = {探针, config A v2 (55431759)}。
   config A v2 是锚 (~647) 不动, 探针本身=config A+无害flag, 最坏情形结算相近, 风险可接受。
5. 交后按 #132 管线重测 live WR (list_submission_episodes + replay + top_pilot_analyze --source ours),
   目标 n≈42-72; 尽早交以最大化截止前局数。
6. 判读: WR >0.62 (跳动 >15pp) → 留, 拆单发归因; flat/小动 → retroactive NO-GO 归档
   (注明功效不足、非证伪), config A v2 仍是落袋锚。

## 不动项

ledger #135 预留收官条不插队; 观测哨 f6bd5dac / 周报 530a9aba / 收官提醒 9a7c7fda / checklist 照旧;
8/15 晚 pilot 调查时间盒不变 (探针提交不占调查时间, 属例外通道)。
