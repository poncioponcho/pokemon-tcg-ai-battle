# v22 结构 2×2 消融预注册

时间：2026-08-15 CST
状态：`preregistered-before-W/L`
线上动作：无；本实验不修改、打包或提交 exact v22。

## 动机与未覆盖空间

固定 82 场 PUBLIC replay 的 exact-v22 顺序重放为 8,333 次 ACTIVE 调用、
8,251 次选择、0 mismatch。相对 `validated_fallback_policy`，manual guards 或
hierarchy 最终只在 44 个选择上产生语义不同的动作（0.53%）。job 级拆分后没有任何
`control:*@turn<=4` 路径同时满足旧 ref 发现集与新 ref 复现集的最低覆盖，因此不再
为单个稀疏 job 制造新规则。

C-009 的 residual ES 只关闭一个到三个 manual guard / MAIN 层，且可关闭的 hierarchy
仅含 processing queue、turn DAG、deadline scheduler、continuity scheduler。它没有回答
下面这个更粗但正交的问题：v22 的完整 manual guard 层和完整 hierarchy 层，各自对
validated fallback 的净贡献是什么，二者是否存在负交互。

## 冻结的 2×2 候选

两个因子均为布尔值：

- `manual=on/off`：是否保留 `manual_guards.GUARDS`；
- `hierarchy=on/off`：是否让 `main.choose` 调用完整 hierarchical policy；off 时直接调用
  exact-v22 自带的 `validated_fallback_policy.choose`，仍保留 main 的硬合法性兜底、
  `_HISTORY` 与 episode reset。

四个臂：

1. `exact_v22`：manual on，hierarchy on（冻结 incumbent）；
2. `hierarchy_only`：manual off，hierarchy on；
3. `manual_only`：manual on，hierarchy off；
4. `fallback_only`：manual off，hierarchy off。

所有臂使用同一 exact-v22 60 卡牌组、同一运行树作为源码；只做进程内 monkeypatch，
不得写回候选目录。每局必须发送 `select=None` 清理 `_HISTORY` / StrategicMemory。

## 运行前行为 canary

用已经冻结的 82 场 replay 顺序重放：

- `exact_v22` 对 recorded action 必须 0 mismatch；
- 三个消融臂各自在首次语义动作分歧处停止该局的反事实重放，不能把分叉后的 incumbent
  observation 当成消融臂自己的轨迹；
- 记录每臂首次分歧的 episode/ref/seat/reward/turn/context；索引不同但卡牌与目标语义
  相同不算分歧；
- 牌组必须始终与 exact v22 一致；任一初始化/合法性 fault 先修仪器，不解释 W/L。

canary 只证明开关真实生效和量化行为覆盖，不用 replay 的历史 W/L 选择 winner。

## 四腿 blocked-independent screen

原生 cg shuffle 无 seed setter；所有对局是独立随机样本，不称 paired/CRN。每臂独立跑：

- exact v22：64 局，权重 0.45；
- Router/Crustle：32 局，权重 0.15；
- Alakazam：16 局，权重 0.30；
- Lucario/config A：32 局，权重 0.10。

每腿局数均为 4 的倍数，候选座位按 ABBA/BAAB 四局块交替，seat 0/1 严格平衡。
四臂并行时只平衡粗时间窗口，不声称共享 shuffle。

消融臂进入 n=256 的必要条件全部同时成立：

- candidate fault = 0；
- 对 exact v22 主腿 WR >= 0.53；
- 相对同批独立 `exact_v22` control 的加权 WR 增量 >= 3pp；
- Router、Alakazam、Lucario 任一跨牌组腿相对 control 不得下降超过 10pp。

若多个臂合格，只取加权增量最高者；再按 v22 主腿 WR、标签字典序打破平局。

## 独立 n=256 主闸

只对 screen 合格的唯一最佳臂运行：候选 vs exact v22 256 局，另跑 exact-v22 自镜像
256 局作同制度独立 control。PASS 必须全部满足：

- candidate fault = 0；
- 候选对 exact v22 WR >= 0.55；
- 候选 WR 相对独立 incumbent control 增量 >= 3pp。

未达即 `winner=null`，不降闸、不追跑、不 materialize、不打包、不提交。即便 PASS，
也只获得“可进入 exact-archive 复验”的资格，不自动改变 8/16 精确重交 v22 的默认动作。

## 解释边界

- 这是结构消融，不是新一轮参数搜索或单 job 归因；
- screen 点估计不作显著性声明，W/L 仍受 native shuffle 路径方差影响；
- 若三种消融均失败，只能封口“赛前可交付的 v22 内部删减空间”，不能证明每个 job
  在所有 meta 下都最优；
- Crustle live 2-3 不作为单独晋级理由，本实验不重开牌组或 Crustle 专项。
