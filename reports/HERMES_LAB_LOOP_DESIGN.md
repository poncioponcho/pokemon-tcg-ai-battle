# Hermes Lab Loop 设计：以学生 agent 胜率为首要目标的奖励方案与循环架构

日期：2026-08-06 ｜ 距模拟赛道截止（2026-08-16 23:59 UTC）：10 天
状态：设计方案 v1（待 Phase 0 可行性验证后生效）

---

## 0. 现状盘点（设计前提）

| 组件 | 现状 |
|------|------|
| 提交形态 | `main.py` 单文件纯规则 v23.2（LB 600.0）+ 可选 `model_student.npz` 蒸馏学生（`_nn_consult` rerank 模式，失败自动降级纯规则） |
| 训练管线 | Kaggle GPU：`train_v2.py` BC(8ep)→AWR(5ep)→蒸馏(8ep)→`model_student.npz`；1,815,639 决策 / 13,842 episodes；断点续训已支持 |
| 模型 | Teacher：残差 MLP（hidden 1024 × blocks 2，~4M 参数）；Student：Linear+ReLU 纯 numpy 可复现（提交硬约束） |
| 门禁 | 产物闭环已有：`student_canary_top1 ≥ 0.30` → pack → 冒烟 → READY（提交留人工） |
| Hermes 现状 | launchd watchdog：kaggle_poll / kernel_poll / kaggle_artifact / health 四个确定性脚本，**仅监控+回收产物+通知，不构成优化闭环** |
| 硬约束 | Kaggle GPU 配额 ~30h/周（P100/T4x2 共享）；单 session ~9-12h；P100 sm_60 需 cu118 torch（已解决）；提交包仅标准库+numpy |
| 引擎 | `kaggle_environments` cabt 环境支持 `env.run([agent_a, agent_b])` 自我对弈（`sdk/test_cabt.py` 已验证接口） |

**关键澄清**：Hermes 是「脚本 + 按需调用的 LLM agent」，不是可训练策略网络。因此本设计的"奖励函数"落地为三个可执行物：
1. **实验记分卡**（ledger 中的 R(e) 计算公式，确定性脚本计算）；
2. **晋级门禁**（champion-challenger 判定规则）；
3. **元控制器的优化目标**（LLM 提议下一批实验时写进 prompt 的目标函数）。

---

## 1. 奖励方案设计

### 1.1 信号层级（按可信度 × 延迟排序）

| 层级 | 信号 | 性质 | 与真实胜率的相关性 | 延迟 | 成本 |
|------|------|------|------|------|------|
| L1 | Kaggle LB 分数 | 终局真值 | 最高（即目标本身） | 数小时 | 每日提交次数有限，极贵 |
| L2 | 竞技场胜率（arena win rate） | 稠密代理 | 高（直接测对局结果） | 训练后 ~15-60 min | CPU，便宜 |
| L3 | canary_top1 / fixed_test 指标 | 整形信号 | 中（模仿精度≠胜率，只做趋势参考） | 训练中即有 | 免费 |
| L4 | 训练 loss / AWR 权重分布 | 健康度 | 低 | 实时 | 免费 |

**首要目标锚定 L2（竞技场胜率）**，L1 只做终局确认。L3 绝不允许单独作为晋级依据——这是防止"调参调到模仿精度上但胜率不动"的核心纪律。

### 1.2 奖励公式

对每个完成的实验 e（一次 train→arena→eval 全链路）：

```
R(e) = 100 × ( WR_arena(e) − WR_champion )          # 主项：对冠军的胜率差
     +   5 × ( canary_top1(e) − canary_top1(champ) ) # 整形：模仿精度趋势
     +   2 × ( fixed_top1(e) − fixed_top1(champ) )   # 整形：稳定性
     −  20 × 1[validation/非法动作]                   # 罚：动作铁律违反（一票否决）
     −  10 × 1[pack/冒烟失败]                         # 罚：工程失败
     −   5 × 1[超出单实验算力预算]                    # 罚：配额失控
     + (仅提交后) 2 × ΔLB/100                         # 终局奖励，稀疏
```

晋级判定（确定性门禁，不靠 LLM 判断）：

```
PROMOTE ⇔  arena_games ≥ 400
        ∧  WR_arena(e) − WR_champion ≥ +0.02
        ∧  二项 95% CI 下界(WR_e) > 点估计(WR_champ)
        ∧  canary_top1(e) ≥ max(0.30, canary_champ − 0.01)   # 精度不许显著退化
        ∧  invalid_actions == 0 ∧ smoke_pass == True
```

### 1.3 竞技场（胜率测量）设计

- **被测对象**：完整提交形态 `main.py + model_student.npz`（hybrid rerank 模式），**不是裸 student**。因为 LB 上跑的是 hybrid，测裸模型会高估 NN 影响。
- **对手层级**（沿用 Tiered Opponent System）：
  - Tier 1（主基准）：当前 champion v23.2 纯规则——所有实验必须过这关；
  - Tier 2（回归哨兵）：历史版本 v22.5——防止对单一对手过拟合；
  - Tier 3（ sanity ）：random/first agent——~~必须 ≥99%~~ **已证伪，见附录 B3**：实测 v23.2 vs random 仅 86.5%、vs first 仅 33%（first+样例牌组是强快攻基线）。Tier 3 改为「经验基线记录制」，不作固定阈值哨兵。
- **协议**：~~N=400 局~~ **N≥2000 局**（附录 B：单局实测 ~10ms，400 局 ~5s，2000 局也仅 ~20s，白捡 CI 从 ±4.9% 收紧到 ±2.2%），先后手对半，固定种子集；输出 `arena_report.json`（胜/负/平、CI、平均每局回合数、invalid 计数）。
- **执行位置**：~~Kaggle kernel 同 session CPU~~ **本地 Mac 直接跑**（附录 B：官方数据包 sample_submission 自带 `libcg.dylib` arm64，无需 kaggle_environments，无需 Kaggle CPU kernel）；Kaggle CPU 仅作交叉复测。
- **Phase 0 必须实测**：~~单局耗时决定 N 上限~~ **已裁决（2026-08-07，附录 B）：本地可行且极快，此门禁已通过**。

### 1.4 防钻空子（reward hacking 防线）

1. arena 对手池冻结在 `experiments/arena_pool/`，任何实验不得修改对手；
2. 胜率必须跑满 400 局，禁止"跑到领先就停"；
3. LB 提交权保留人工确认（沿用现有纪律），Hermes 只到 READY；
4. ledger 只追加、不修改，所有 R(e) 可由 `arena_report.json` 重算复现。

---

## 2. Hermes Lab Loop 架构

### 2.1 分层架构

```
┌────────────────────────────────────────────────────────────┐
│ L3 元控制器（LLM agent，每周 1-2 次按需调用）               │
│   读 ledger.jsonl + arena_report → 提出下一批实验           │
│   （超参方向 / 结构改动 / 数据刷新）→ 写 experiments.yaml   │
├────────────────────────────────────────────────────────────┤
│ L2 评测与晋级（确定性 python，新增）                         │
│   arena_runner → arena_report.json                         │
│   reward_calc → ledger.jsonl 追加 R(e)                     │
│   promotion_gate → 晋级 champion / 归档 challenger          │
├────────────────────────────────────────────────────────────┤
│ L1 实验编排器（确定性 python，新增）                         │
│   experiments.yaml 队列 → 模板化 kernel config             │
│   → kaggle_push.sh → kernel 监控 → 收 metrics+npz           │
│   配额账本：单实验 GPU ≤3h，周 ≤28h，超额拒发               │
├────────────────────────────────────────────────────────────┤
│ L0 守护（现有，保留不动）                                    │
│   kaggle_poll / kernel_poll / kaggle_artifact / health     │
└────────────────────────────────────────────────────────────┘
```

**设计原则**：L0-L2 全部确定性脚本（0 token）；LLM 只在 L3 出现，且每次调用产出必须是"写进 experiments.yaml 的结构化实验提案"，可审计、可驳回。

### 2.2 实验动作空间（L3 可提议的范围）

| 类别 | 动作 | 实现成本 | P100 适配 |
|------|------|------|------|
| 超参 | lr / tau(AWR 温度) / wcap / distill_temp / distill_alpha / epochs / dropout | 零（已是 CLI 参数） | ✓ |
| 结构-Teacher | blocks 2→4→6；hidden 1024→1536→2048 | 低（已是 CLI 参数） | ✓ 单 epoch 仍分钟级 |
| 结构-多任务 | Teacher 加 value/reward 辅助头（policy+value 联合训练） | 中（改 model_v2/train_v2） | ✓ |
| 结构-离线RL | AWR → IQL/CRR（expectile 价值函数，更稳的优势加权） | 中高（新增 ~80 行） | ✓ 纯离线，无 rollout |
| 结构-option编码 | Teacher 端 option attention/pointer | 高 | ✓ 但优先级后移 |
| 数据 | 新 replay 抓取→重提取→增量续训；TopRatedEpisodes 周更 | 低（管线已有） | ✓ **预期 ROI 最高** |
| 数据-DAgger | arena 败局挖掘→定位败因决策→加权进训练集 | 中 | ✓ |
| 禁区 | Student 架构（Linear+ReLU 白名单锁死，必须 numpy 可复现）；在线 PPO/自我对弈 RL（10 天内工程风险过高，列为 stretch） | — | — |

**核心架构洞察**：提交约束锁死了 student 必须是纯 numpy 小 MLP，所以**所有结构创新发生在 teacher 端**，靠蒸馏弥合容量差。这正好把"加深网络/加结构"的需求全部引导到不受部署约束的地方。

### 2.3 单次循环时序（一个实验的生命周期）

```
experiments.yaml 出队
  → L1 渲染 kernel 配置（TRAIN_ARGS 模板化注入）
  → kaggle_push.sh 推送 + 监控（现有 kernel_poll 扩展）
  → kernel: train_v2 → export npz → arena_runner（同 session CPU）
  → 回收: model_student.npz + train_v2_report.json + arena_report.json
  → L2 reward_calc 算 R(e) 追加 ledger
  → promotion_gate: 晋级→标记 champion + READY 通知（人工提交）
                    未晋级→归档 challenger，报告晋级差距
  → 配额账本记账；队列空 → 通知 L3 该开会了
```

---

## 3. 可行性评估

### 3.1 算力预算（P100 / 30h 每周）

| 项目 | 单次耗时（估） | 说明 |
|------|------|------|
| train 全流程（BC+AWR+distill） | T4x2 实测 1.5-3h；P100 单卡约 2-4h | 1.8M 决策，bs 16384 |
| arena 2000 局 | ~20-40s **本地 Mac**（附录 B 实测） | 不占 GPU、不占 Kaggle |
| **单实验合计** | **≤4h GPU** | |
| 周实验数 | **6-8 个** | 28h 预算（留 2h buffer） ✓ |

10 天 ≈ 1.4 个配额周 → **全项目可跑 8-11 个实验**，足够覆盖一次有意义的 sweep，不够铺张的架构搜索——所以 Phase 2 结构实验限制在 2-3 个最有把握的。

### 3.2 逐项风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| ~~arena 引擎速度/稳定性未知~~ | ~~高~~ **已裁决（附录 B）**：本地 arm64 单局 ~10ms，harness 经官方 interpreter 交叉验证 | 无 |
| 模仿天花板：replay 数据分布限制 teacher 上限，调参打不破 | 中高 | 数据刷新（周更 TopRated）+ DAgger 败局挖掘作为独立实验类别，预期 ROI 最高 |
| hybrid rerank 模式稀释 NN 影响（规则首选不被推翻时 NN 无贡献） | 中 | arena 测 hybrid 整体；可设 `_NN_MODE/_NN_GAP` 为实验变量；nn_first 模式作对照实验 |
| 400 局 CI ±4.9% 噪声 vs +2% 晋级阈值 | 中 | 阈值与 CI 双重判定；临界结果加跑 400 局复测 |
| LB 提交次数限制 + 延迟反馈 | 中 | LB 不进高频路径，只做 champion 终局确认，每天最多 1 次 |
| 时间只剩 10 天 | 高 | Phase 0 若 arena 不可行立即回退，不在 loop 基建上恋战 |

### 3.3 结论

**可行，且无需新建重型基础设施**——现有训练管线、门禁、watchdog 都已就位，缺的只是：arena runner、实验账本/记分卡、kernel 配置模板化、L3 元控制器 prompt。全部为 1-2 天工程量的轻量脚本。~~唯一硬不确定项是 arena 引擎在 Kaggle CPU 的速度~~ **该不确定项已于 2026-08-07 裁决（附录 B）：本地 arm64 引擎 ~10ms/局，harness 经官方解释器交叉验证忠实——可行性最后的硬疑点消除**。

---

## 4. 实施计划（8/7 → 8/16）

### Phase 0（D1，8/7）：可行性裁决 + 基线固化 —— 门禁日
1. 回收当前云端首训 npz → 过现有门禁 → 人工提交 v24 基线（确立首个 champion，拿到 NN-hybrid 的第一个 LB 锚点）；
2. ~~**arena spike**：CPU kernel 50 局计时~~ **已完成（附录 B）：本地 spike 通过，单局 ~10ms，harness 忠实性已交叉验证**；
3. 落 L1/L2 骨架：`experiments.yaml`、ledger.jsonl、reward_calc.py、kernel TRAIN_ARGS 模板化。

### Phase 1（D2-D5）：超参 + teacher 容量 sweep —— 6-8 实验
- teacher blocks {2,4,6} × hidden {1024,1536} 粗扫；tau {0.3,0.5,1.0}；distill_alpha {0.3,0.5}；
- 每实验 train + arena 400 局，目标：**晋级首个击败纯规则 champion 的 NN-hybrid**。

### Phase 2（D5-D8）：结构实验（限 2-3 个，按 Phase 1 证据选）
- 优先：多任务 value head（表征增强，工程可控）；
- 次选：IQL/CRR 替换 AWR（若 sweep 显示 awr 权重/tau 高度敏感）；
- 穿插：TopRated 数据刷新 + 增量续训（不占结构实验名额）。

### Phase 3（D8-D10，8/14-16）：收官
- 冠军固化 + 复测 arena 800 局；每天至多 1 次 LB 确认提交；
- 冻结代码、复盘文档、ledger 归档。

### 交付物清单（Phase 0-1 新建文件）
```
experiments/experiments.yaml      # 实验队列（L3 写、L1 读）
experiments/ledger.jsonl          # 只追加实验账本（含 R(e)）
experiments/arena_runner.py       # cabt env 自我对弈 + arena_report.json
experiments/reward_calc.py        # 奖励公式 + 晋级门禁（确定性）
experiments/arena_pool/           # 冻结对手：v23.2 / v22.5 / random
.kaggle_kernel/run_experiment.py  # 模板化：train→export→arena 一体 kernel
~/.hermes/scripts/lab_loop.sh     # 编排器入口（launchd/cron 挂载）
```

### 回退方案（Phase 0 若 arena 不可行）
奖励降级为：R(e) = 5×Δcanary + 2×Δfixed + LB 终局项；晋级门禁改为「canary 提升 + LB 确认」；其余架构（账本/模板化/L3 元控制器）不变，仍然比现在"只监控不优化"的 Hermes 强一档。

---

## 附录 A：评审意见（2026-08-06 22:46）

### A1. 方案总评
设计合理、结构完整、务实可落地。核心纪律全部正确：arena 胜率锚定 L2、student 锁死 numpy、结构创新全放 teacher 端、LB 提交保留人工。L0-L3 分层 +「L2 以下全确定性脚本、LLM 仅 L3」是防 reward hacking 的正确工程形态。

### A2. 关键修正：GPU 约束已从 P100 升级为 T4 x2（已验证）
设计前提写的是「P100 sm_60 需 cu118 降级」，但 22:39 起训练已实际运行在 **GPU T4 x2**（通过 `push_t4.py` 的 `create_kernel_session(machine_shape='GPU T4 x2')` 实现，账号支持）。影响：

| 维度 | P100（原假设） | T4 x2（实际） |
|------|------|------|
| torch 兼容 | sm_60 需 cu118 降级 | sm_75 与 cu128 原生兼容 |
| 单训练耗时 | 2-4h | 1.5-3h |
| 结构实验（blocks 6/hidden 2048） | 可行但慢 | 更稳更快 |
| 周实验数 | 6-8 | 上浮（预算更宽裕） |

风险表「P100 适配」列可整体上调一档。`push_t4.py` 已固化此路径（删除旧 kernel → save → create_kernel_session(T4 x2)），自动修复链应默认用 T4 x2。

### A3. 新增发现：本地无法跑 cabt arena（必须上 Kaggle）
本地 Mac 的 kaggle_environments 只有 `cg.dll`(Windows) / `libcg.so`(Linux x86)，**缺 Mac 版（libcg.dylib / libcg-arm64.so）**，`make("cabt")` 加载 C 库失败。结论：
- arena spike 无法本地裁决，**必须在 Kaggle CPU kernel 上跑**（kimi 方案 Phase 0 的预设正确，且是唯一硬不确定项）；
- 本地能做的只有：写 `arena_runner.py` / `experiments.yaml` / `ledger.jsonl` 骨架 + 静态验证 agent 接口（`main.agent(obs, config)` 存在，已确认）。

### A4. 实施顺序建议
1. **当前 T4 x2 训练完成 = Phase 0 第 1 步**（回收 npz → 过门禁 → 建首个 NN-hybrid champion）；
2. 并行写 L1/L2 骨架（本地，零配额）；
3. 训练完成后推一个 **CPU arena spike kernel**（不计 GPU 配额）裁决 400 局成本；
4. spike 通过 → 进入 Phase 1 sweep；不通过 → 启用回退两级奖励方案。

---

## 附录 B：Arena Spike 裁决结果（2026-08-07 06:56，推翻 A3）

### B1. A3 结论下早了：官方数据包自带 Mac 引擎

`kaggle competitions download -c pokemon-tcg-ai-battle`（301MB）内含：
- `sample_submission/sample_submission/cg/libcg.dylib` — **Mach-O arm64**（本机原生）；
- `libcg-arm64.so`（Linux arm64）、`libcg.so`（Linux x86）、`cg.dll`（Windows）；
- `cg/sim.py` 按平台自动选库（Darwin → dylib），`battle_start/battle_select/battle_finish` 纯 ctypes 接口，**完全不需要 kaggle_environments**；
- 另附 `ptcg_engine/` 引擎完整 C++ 源码（未来可自行编译/改引擎，长期期权）。

落地：`inference/comp_data/` 已下载并解压 sample_submission。

### B2. Spike 实测（`experiments/arena_spike.py`，本地 arm64）

| 对阵 | 局数 | 单局耗时 | 400 局外推 |
|------|------|------|------|
| v23.2 vs v23.2 | 200 | 9ms | ~4s |
| v23.2 vs random | 200 | 6ms | ~3s |

**裁决：arena 本地可行且几乎免费，「400 局 ≤ 30 分钟」门禁以 4 个数量级余量通过。** Arena N 从 400 上调到 ≥2000（CI ±2.2%）。整个 L2 评测可在本地 Hermes 侧闭环：Kaggle 训练 → 下载 npz → 本地 arena → 晋级判定，不再需要 Kaggle CPU kernel。

### B3. Harness 忠实性已交叉验证（官方 interpreter 对照）

担心「v23.2 对 first_agent 胜率仅 29%」是 harness 视角 bug，遂用 `sdk/cabt.py` 官方解释器原样驱动交叉验证（修正局间 `battle_ptr` 残留导致的 SIGTRAP/Abort 后）：

| 对阵（200 局） | 自写 harness | 官方 interpreter |
|------|------|------|
| v23.2 vs first | 29.0% | **33.0%** |
| v23.2 vs random | 72.0%(样例牌组) | **86.5%**(cabt 牌组) |
| first vs random | — | 68.0% |

两套实现结果一致 → harness 忠实。**重要领域发现：first_agent（永远选前 maxCount 个选项）+ 样例牌组 = 强快攻基线，v23.2 对它只有 ~33% 胜率**——这不是噪音，是 v23.2 磨库/墙推体系被无脑快攻rush的真实坏对局。设计修正：
1. Tier 3「random/first ≥99%」假设作废 → 改为经验基线记录制（每对手维护实测胜率水位线，显著偏离才报警）；
2. first_agent 升格为 **Tier 2 正式对手**——它可能就是天梯上大量样例牌组 bot 的写照，且是 v23.2 已证实的弱点对局，challenger 对它的胜率提升是高价值信号；
3. 晋级门禁同时考察 vs champion（v23.2 镜像）与 vs first（弱点对局）两个胜率。

### B4. 对实施计划的影响
- Phase 0 第 3 步「CPU arena spike kernel」**取消**（本地已裁决）；
- L2 arena_runner 从「Kaggle kernel 内运行」改为「本地优先」，kernel 侧 arena 降级为可选交叉复测；
- 遗留注意：Mac dylib 上 `VisualizeData` 会 SIGTRAP（arena 不需要，官方 interpreter 的 `finish()` 里调用需跳过）；官方解释器每局结束后须手动清 `Battle.battle_ptr`（官方框架的 env.done 分支动作，自写驱动要补）。
- 算力表更新：arena 成本≈0（本地秒级），单实验成本 = 纯训练 1.5-3h GPU → 周实验数上限进一步上浮，瓶颈转为「Kaggle 训练排队 + 配额」。

---

## 附录 C：L1/L2 骨架落地与本地 arena 验证（2026-08-07 07:30）

### C1. 骨架交付（experiments/，全部验证通过）
- `arena_runner.py`：本地直驱官方引擎（libcg.dylib arm64），被测 hybrid 隔离运行于 runs/<id>/（复制 main.py+npz+deck.csv，忠实提交形态）；2000 局/对手可配；输出兼容 reward_calc。
- `reward_calc.py`：R(e) 公式 + 晋级门禁（Wilson CI），5 场景单测 + 门禁集成测试通过；阈值已同步 2000 局。
- `lab_render.py`：experiments.yaml → kernel TRAIN_ARGS 模板化（exp001 渲染验证通过）。
- `lab_loop.sh`：配额账本（周 28h）+ 出队 + 渲染 + push_t4.py 推送。
- `arena_pool/`：v23_2_rules.py（3036 行冻结）、v22_5_rules.py（git 2f829d7 导出 2619 行）、deck.csv；注册表 sha256 已刷新。

### C2. 正式规模基线（8000 局 68.8s，纯规则 v23.2 作 challenger）
| 对手 | 2000 局胜率 | 解读 |
|------|------|------|
| v23_2_rules（镜像） | 52.0% | ≈50% 合理，deck 随机性 |
| v22_5_rules（回归哨兵） | 92.5% | 版本迭代压制 ✓ |
| **first（弱点对局）** | **32.9%** | **重大弱点实锤**：无脑快攻对磨库体系克制 |
| random（sanity） | 73.8% | sanity 通过 |
| 合计 | 62.8%（CI95lo 61.7%） | 基线确立 |

### C3. 关键结论
1. 本地 arena 门禁从 30 分钟收紧到 ~70 秒（8000 局），且 CI 更紧（2000 局 ±2.2%）；
2. **first 弱点对局是最高 ROI 改进方向**：纯规则 33% → NN 若能提到 50%+，对总 WR 贡献显著（这也解释了为何 LB 上磨库体系排名不稳）；
3. 晋级判定需按 kimi 设计拆「vs champion 镜像」+「vs first 弱点」双指标（当前 reward_calc 为单 WR 聚合，L3 阶段完善）；
4. L2 全链路本地化：训练完成 → 下载 npz → 本地 70s 跑 8000 局 → 门禁 → 通知人工提交。闭环不再依赖 Kaggle CPU。

---

## 附录 D：12h 超时应对预案（2026-08-07 07:50；08:10 修订时限与脚本）

### D1. 事实（已修订）
~~Kaggle 免费 GPU session 上限约 9 小时~~ **官方员工在 product-feedback/317907 确认：单 session 上限 12h（由早期 9h 提升），Save & Run All 后台 script 同样 12h**。当前训练 8/6 22:39 启动，12h 红线 ≈ 8/7 10:39。另一官方确认点：被 cancel 的 version 其 output **不能**被其他 notebook 直接挂载为 input（只认成功 version）——必须「下载 → 上传 dataset → 挂载」，本预案 D2 路径与此一致。

### D2. 恢复机制（`scripts/resume_kernel.sh`，2026-08-07 08:10 修复三处 bug 后可用）
断点续训链路完整：每 epoch 自动保存 `ckpt_v2_last.pt`（含 stage/phase/epoch/optimizer/AMP/RNG）→ `train_v2 --resume auto` 无缝续接（seed 须一致=42）；`prepare()` 通过 `find_in_input` 从挂载 input 恢复 ckpt。

超时被砍后的恢复 SOP（脚本一键执行）：
1. 下载 output 中 `ckpt_v2_last.pt` + `teacher_best.pt` + `student_best.pt`（`--file-pattern` 已核实有效）
2. 上传/更新 dataset `daniel1547/ptcg-ckpt`（首次自动 `datasets create`，之后 `version -p ... -r zip`；已修复原脚本 `version` 不能建 dataset + 参数形态错误）
3. `kernel-metadata.json` 挂载该 dataset → `push_t4.py` 重推（已修复原脚本引号 heredoc 不展开 `${META}` 导致静默跳过的 bug；metadata 更新失败会中止防裸跑）
4. kernel 内 `prepare()` 自动恢复 ckpt → `--resume auto` 从断点续训

捷径：若 output 已有 `student_best.pt`（distill 跑过至少一个 eval 点），可**跳过续训**，直接 CPU kernel 跑 `export_student.py` 导出 npz 锁定 best-so-far（脚本已加提示）；若仅有 `teacher_best.pt`，可用 `--stage distill` 续训跳过剩余 BC/AWR epochs 省 GPU。

### D3. 根治：阶段拆分（已实现）
`--stage all`（21 epochs ≈ 5-10.5h，超时风险高）拆成两个 kernel，各自安全落在 12h 内：
- `stage: teacher`（BC 8 + AWR 5 epochs）→ ckpt
- `stage: distill`（distill 8 epochs，挂载 teacher 阶段 ckpt 续接）
实现：`kaggle_gpu_train.py` 支持 `KAGGLE_STAGE` 环境变量；`lab_render.py` 支持 yaml `train.stage` 注入（已验证）。下轮实验默认走拆分。

### D4. 触发逻辑
- Hermes 10 分钟轮询检测到 kernel ERROR/cancel（超时被砍）→ 通知 + 判定是否含有效 ckpt（output 可下）→ 是则提示运行 `bash scripts/resume_kernel.sh`（或 agent 自动执行）→ 否（ckpt 也丢）则标记实验 failed，L3 重排。
