# 2026-08-14 跨策略发射记录：Grimmsnarl v1

状态：runtime-fixed 包已完成 Kaggle 校验；首分 600.0，随后曾更新到 709.1。
它证明了跨策略发射可以超过旧 700.3，但已被后续两次有效提交顶出活跃集。

| 项目 | 值 |
|---|---|
| Kaggle ref | `55495955`（成功）；`55495594`（缺 `cg/`，Validation Episode failed） |
| artifact | `artifacts/grimmsnarl_v1_cg/submission.tar.gz` |
| archive SHA256 | `307bfc6bb6abcf562cdd5c1912cae13d3934af6845e79083de6a318e381d4f5b` |
| `main.py` SHA256 | `c61e540bcb45aa2e8184ae912e7e17efaa900dba3df4536468da41899b09dcd8` |
| `deck.csv` SHA256 | `92b92bac9f9163ecff933b3dc39294d2cc154c8684f3c8497877661419ebc59d` |
| 包内容 | 197 个 regular files，2.5 MB，含官方 `cg/`，排除 pycache/link |
| Kaggle 状态 | `COMPLETE`，首分 `600.0`；08-14 10:4x CST 曾读到 `709.1`，后续漂至 `628.0` |

## 交付前证据

- 60 卡、ID、四张上限和 ACE SPEC 唯一性通过官方卡表检查。
- 净目录 import 与无 `__file__` 的 Kaggle-style `exec` 均通过，启动返回与
  `deck.csv` 一致。
- runtime-fixed 最终包在完全不借外部 engine path 的净进程中完成 4/4 官方
  引擎 self-games；第一次失败确认是交付工具遗漏 `cg/`，已修为默认随包。
- 官方本地引擎（先后手交错、256 局）：
  - 对 pristine config A：165 胜 / 91 负，0 invalid；
  - 对 700.3 retreat pivot：169 胜 / 87 负，0 invalid；
  - 平均约 155 次选择/局，无超时。
- Rmy Mega Lopunny V9 同闸仅 4/64，已淘汰，不提交。

## 下一次观测

```bash
/opt/homebrew/bin/kaggle competitions submissions pokemon-tcg-ai-battle
python3 experiments/live_episodes_probe.py \
  --ref 55495955 \
  --out experiments/runs/live_episodes_grimmsnarl.json
```

行动层不因 `WR≤0.62` 自动归档；认知层只有 `WR>0.62` 才宣称可识别正效应。

## 机制纠错

08-14 的官方完整 leaderboard 亲验表明团队榜跟随最新有效提交，不取
`max(last-2)`。因此 Router 和 retreat 恢复件提交后，本件虽然仍能在提交页看到分数，
但已不在 `team-submissions` 返回的最近两件中，不能再充当团队榜锚。
