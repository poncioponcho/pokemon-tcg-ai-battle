# kimik3 重构：思维过程 · 关键步骤 · 变更总结

> **目的**：本文档仅梳理 **kimik3（Kimi）** 对 Pokemon TCG AI Battle 项目的模块化重构——
> 它做了什么、为什么这么做、每个关键步骤是怎么处理的。
> 不含任何第三方（hy3 / WorkBuddy）的代码或后续补全；kimik3 留下的代码现状即为本文描述的现场。
>
> **现场状态**：重构为「平行版本」——根目录 `main.py`（单文件规则 Agent）未被改动；
> `inference/` 下是 kimik3 的新模块化包，但 4 个底层支撑模块（`state_parser` / `option_scorer` / `decision_gate` / `card_meta`）缺失，
> 因此 `inference/main_entry.py` 当前 **import 即失败**，模块化包尚不能独立运行。

---

## 一、kimik3 的整体思路（思维过程）

kimik3 面对的核心问题：**`main.py` 是一个约 2800 行的单文件规则 Agent**，所有 `select` 类型的决策逻辑、卡牌元数据、obs 解析都耦合在同一个文件里，难以维护和复用。

它的解决思路不是重写决策逻辑，而是**按职责做垂直切分 + 一个合并器回灌单文件**：

1. **把决策按 `SelectType` 拆成 11 个专用 handler**（`handlers.py`），每个 handler 只管一类选择场景。
2. **把"解析 obs → 内部状态"和"卡牌元数据"抽成独立模块**（`state_parser.py` / `card_meta.py`），让 handler 不直接碰原始引擎字典。
3. **把"复杂决策"集中到一个决策门**（`decision_gate.py`），简单 handler 直接返回，复杂 handler 委托给它——避免每个 handler 都写一遍战斗策略。
4. **用一个 `merge.py` 把多文件重新拼成一个单文件 `main.py`**，满足 Kaggle 提交格式（提交要求单文件 + `deck.csv`）。

这个架构的关键判断是：**拆分是为了可读性，提交时再合并回去**。所以模块边界清晰、依赖方向单一（`main_entry → handlers → decision_gate → card_meta/state_parser → option_scorer`）。

---

## 二、关键步骤与 k3 的处理方式

### 步骤 1 — 定义类型与枚举层（`option_scorer.py`）
- **做什么**：定义 `Option` / `SelectType` / `SelectContext` / `OptionType` 枚举，以及按类型筛选项的辅助函数（`get_options_by_type` / `find_first_option_by_type`）。
- **k3 怎么处理**：把所有引擎用的「数字常量 → 语义字符串」映射集中在这一层。这样上层 handler 写 `SelectContext.SETUP_ACTIVE` 而不是魔法数字 `1`，可读性和防错都更好。
- **关键设计**：`Option` 用 `__slots__` 包裹 `index / raw_data / card_type / stage`，轻量且避免意外字段。

### 步骤 2 — obs 解析层（`state_parser.py`）
- **做什么**：`parse_observation(obs) → GameState`（玩家/对手的手牌、战场、牌库、弃牌、奖品、active），以及 `parse_select(select) → (SelectType, SelectContext, options, max_count)`。
- **k3 怎么处理**：把引擎原始字典统一翻译成内部结构 `GameState` / `Player` / `Card`，并暴露一组引擎访问器（`_get_my_active` / `_get_opp_active` / `_get_pokemon_hp` 等），供 `decision_gate` 复用。
- **关键设计**：解析与决策解耦——`decision_gate` 只认 `GameState`，不认原始 obs，未来换引擎只改这一层。

### 步骤 3 — 卡牌元数据层（`card_meta.py`）
- **做什么**：`Card` 数据类 + `get_card` / `get_evolution_chain` / `register_card` 等注册与查询接口。
- **k3 怎么处理**：设计成**运行时注册表**——卡牌信息在 `parse_observation` 时从 obs 注册进来，决策时按 `card_id` 查。
- **关键设计**：预留 `_CARD_DB` 精选卡库作为静态兜底（handlers 里 `_pick_highest_hp` / `_pick_evolution_basics` 会按 `card_id` 查 HP 与进化链来打分）。

### 步骤 4 — 11 个 Handler（`handlers.py`）
- **做什么**：每个 `SelectType` 一个 handler，签名统一 `(state, options, max_count, context) → List[int]`。
- **k3 怎么处理**（按场景分三档）：
  - **直接返回**：`attached_card` / `card_or_attached` / `skill` / `special_condition` 直接取前 `max_count` 个 option 的 index。
  - **场景特化**：`card` 按 `context` 分流——`SETUP_ACTIVE`/`SWITCH` 用 `_pick_highest_hp`，`SETUP_BENCH` 用 `_pick_evolution_basics`（进化链越长越优先），其余委托 `DecisionGate`。
  - **上下文判断**：`yes_no` 按 `IS_FIRST`（先手 YES）/ `MULLIGAN`（手牌有基础宝可梦则 NO 重开）做逻辑分支。
  - **委托决策门**：`main` / `attack` / `energy` / `evolve` 全部转交 `DecisionGate.decide`。
- **关键设计**：`_gate = DecisionGate()` 单例，handler 不重复实现战斗策略；辅助函数 `_pick_highest_hp` / `_pick_evolution_basics` 从 `raw_data` 提 `cardId` 再查 `card_meta` 打分。

### 步骤 5 — 统一决策门（`decision_gate.py`）
- **做什么**：`DecisionGate.decide(state, options, max_count, select_type, context)` 承载复杂战斗决策。
- **k3 怎么处理**：内部按 `select_type` 路由到 `_decide_main` / `_decide_card` / `_decide_attack` / `_decide_energy` / `_decide_evolve`，实现通用战斗策略（KO → 进化 → 攻击 → 附着 → 技能 → 撤退 → 结束）。
- **关键设计**：所有输出经 `_sanitize` 保证「长度 == min(maxCount, n)、下标合法、无重复」的**动作铁律**，与根 `main.py` 的约束一致。

### 步骤 6 — 入口与路由表（`main_entry.py`）
- **做什么**：`agent(obs, config)` 入口 + `HANDLERS` 路由表。
- **k3 怎么处理**：`obs["select"] is None` → 返回 `DECK`（60 张）；否则 `parse_observation` → 按 `SelectType` 查 `HANDLERS` → 调对应 handler → 返回。
- **关键设计**：异常兜底用 `random.sample`（永不崩溃）。`DECK` 在 import 时从同目录 `deck.csv` 加载。

### 步骤 7 — 合并回单文件（`merge.py`）
- **做什么**：按 `MODULE_ORDER` 把 6 个模块合并成单文件 `main.py`（Kaggle 提交格式）。
- **k3 怎么处理**：`extract_content` 提取每个模块的 import（标准库去重）与代码体，按依赖顺序拼接；缺失模块打印 `⚠️ 跳过` 并继续。
- **关键设计**：合并器依赖白名单 + 标准库过滤，保证产物是干净单文件。

---

## 三、kimik3 的其它产物（非重构，但同批带来）

| 文件 / 目录 | 内容 |
|-------------|------|
| `sdk/cabt.py` | Kaggle 引擎交互封装（`deck` 定义、`battle_start`/`select`/`finish`） |
| `sdk/cg/` | 游戏引擎核心（`game.py` / `sim.py`） |
| `sdk/test_cabt.py` | 单元测试：`test_cabt_inits` / `test_cabt_first_agent_run` |
| `inference/crawl_daemon.sh` | launchd 守护进程，持续爬取天梯 replay 供训练（`KeepAlive` 自重启、每日预算控制、归档） |
| `inference/*.ipynb` | 实验性 Notebook（PPO / EDA / 策略 MRI / 蒙特卡洛模拟） |
| `*.html` + `*.md` 分析报告目录 | 架构 / 战斗系统 / Meta / 审计等可视化报告 |

---

## 四、现状与缺口（kimik3 留下的现场）

1. **重构半成品**：`state_parser` / `option_scorer` / `decision_gate` / `card_meta` 四个底层模块**不存在**，`handlers.py` / `main_entry.py` 的 import 会失败，模块化包不能独立运行。
2. **`main.py` 未被替换**：仍是单文件规则 Agent（含 NN Advisor 段），模块化版本与原始版本平行存在、未合并。
3. **未纳入 git**：`inference/` / `sdk/` 等目录均未被 git 跟踪，存在丢失 / 无法回溯风险。
4. **未验证**：`merge.py` 构建流程、各模块测试覆盖、与现有 `main.py` 决策逻辑的等价性均未验证。

> 以上缺口均为 kimik3 留下的原始状态，本文档仅作记录，不含任何第三方补全或修改。

---

*整理：基于 kimik3 留下的 `handlers.py` / `main_entry.py`（已回滚至 kimik3 原版）/ `merge.py`（已回滚至 kimik3 原版）/ `sdk/` 等产物推断其思维过程，非 kimik3 原始对话记录。*
