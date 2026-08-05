# 安全与质量漏洞排查报告

- 审计对象: 提交 `a6c99ff` (v23.1) 及工作区待提交状态 (v23.2 含羞苞体系)
- 审计日期: 2026-08-05
- 审计方式: 全文件静态审查 + 动态复现验证 (test_agent.py 24/24、replay_regression_test.py 945 决策 0 异常、定向边界测试)
- 结论: 无注入/XSS/CSRF/加密类漏洞 (纯离线决策代码, 无 SQL/Shell/HTML/网络面); 主要缺陷集中在**兜底路径非法动作、牌组输入校验缺失、敏感信息输出、决策边界健壮性**。

---

## 高危 (HIGH)

### H-1 异常兜底路径可返回非法动作下标 `[0]` (违反动作铁律)
- **位置**: `main.py:2786-2810` (`agent()` 最外层 except 的 fallback 块及最内层 `return [0]`)
- **描述**: 当 `select.option` 为 `None` / 非 list (引擎异常或观测损坏) 时, `len(options)` 抛 TypeError, 落入最内层兜底直接 `return [0]`。此时 options 为空/非法, 下标 0 不存在 → 返回**非法动作**。动作铁律要求"长度==maxCount、下标合法", 非法动作可导致引擎侧报错或对局异常。
- **动态复现**: `agent({"select": {"type":"Main", "option": None}, ...})` → 返回 `[0]` (选项实际为 None)。
- **影响**: 引擎收到非法下标 → 动作被拒/对局异常, 可能直接判负或拖垮对局稳定性; 违反 README 宣称的"148,772 次决策 0 非法动作"保障。
- **修复建议**: 兜底块必须验证 `options` 是非空 list 后再返回下标, 否则返回 `[]`; 最内层 `return [0]` 改为 `return []`。
```python
except Exception:
    try:
        select = obs.get("select", {})
        options = select.get("option", [])
        if not isinstance(options, list) or not options:
            return []
        n = len(options)
        max_count = select.get("maxCount", 1)
        if not isinstance(max_count, int) or max_count <= 0:
            max_count = 1
        return list(range(min(max_count, n)))
    except Exception:
        return []
```

### H-2 `_load_deck()` 输入校验缺失: 非法/恶意 deck.csv 直接污染 DECK
- **位置**: `main.py:114-129`
- **描述**: 仅校验 `len(deck) == 60`, 不校验行是否为正整数、卡 ID 是否在卡池、同卡数量上限 (非能量卡 ≤4)、是否有基础宝可梦。`int()` 能解析的任意 60 个数值 (负数/0/越界 ID) 都会被接受为 DECK。
- **动态复现**: 60 行含 40 行负数/0 的 deck.csv → `DECK` 含 40 个非法卡 ID。
- **影响**: (1) 卡池外卡 ID 提交后被引擎拒绝或替换 → 对局实际打的是未知牌组; (2) 负数/0 ID 进入引擎 API 可能触发引擎异常; (3) 本次审计发现 HEAD 提交包 `submission/deck.csv` 曾与 `main.py` 头注 (v23.2 含羞苞声明) 漂移, 正是"仅长度校验"这类弱校验未能防止的错误。
- **修复建议**: 校验每行 `int > 0`; 数量必须恰为 60; 非法则回退内联 `_INLINE_DECK` 并向 stderr 输出警告。卡 ID 存在性/同卡上限校验放 pack.sh 阶段 (此时可 import main 得到完整 `_CARD_DB`)。

### H-3 `pack.sh` 交叉校验为同义校验, 无法发现内联牌组与 deck.csv 漂移
- **位置**: `pack.sh:35-53`
- **描述**: 校验内容是 `sorted(main.DECK) == sorted(deck)` —— 而 `DECK` 正是由 deck.csv 加载而来, 恒等成立, 是**同义校验**。内联 `_INLINE_DECK` 与 deck.csv 的漂移无法被发现, 与 README "牌组单一来源/杜绝双源漂移" 的宣称不符。
- **影响**: 提交前保障失效, 牌组双源漂移会静默通过 (HEAD 提交包与 v23.2 语义不一致即此保障失效的实例)。
- **修复建议**: 校验改为: (a) `sorted(DECK) == sorted(_INLINE_DECK)`; (b) 每个卡 ID 存在于 `_CARD_DB` 或 `_TRAINER_IDS`; (c) 非能量卡同 ID ≤4; (d) 长度 60。

---

## 中危 (MEDIUM)

### M-1 上传令牌前缀输出到 stdout
- **位置**: `submit.py:82` `print(f"  获取成功 → token: {blob_token[:20]}...")`
- **描述**: 打印短期上传令牌的前 20 字符。
- **影响**: 令牌属敏感信息, 日志/终端留存可能被滥用 (虽为一次性上传 URL 令牌, 但不应输出)。
- **修复建议**: 仅输出令牌长度与指纹 (如 `sha256(blob_token)[:8]`), 不输出令牌本身。

### M-2 token 文件读取无错误处理
- **位置**: `submit.py:37-38`
- **描述**: `open(TOKEN_FILE)` 失败 (文件缺失/权限) → FileNotFoundError traceback 直接退出。
- **影响**: 体验差 + 暴露本地文件路径; 无法提示正确的修复方式 (设置 KAGGLE_API_TOKEN)。
- **修复建议**: 捕获 OSError, 输出友好错误并提示环境变量方案。

### M-3 `_resolve_card_id_from_option` active (area==4) 分支误判能量卡为宝可梦
- **位置**: `main.py:1573-1581`
- **描述**: `index > 0` 且 `active[0]` 含 `"energies"` 键时, 无条件返回宝可梦 id, 忽略 index 指向的能量卡; `energyCards` 分支也仅取 `[0]`。
- **影响**: AttachFrom/DetachFrom 等"选能量来源"场景中, 选项对应的卡被误判为宝可梦 → 决策器按错误卡种打分, 可能选错能量来源 (决策质量缺陷)。
- **修复建议**: `index > 0` 时按 index 在 `energies`/`energyCards` 中查找; 找不到才回退宝可梦 id。

### M-4 `_handle_yes_no` Mulligan 分支逻辑复杂, fallthrough 易产生错误动作
- **位置**: `main.py:2626-2652`
- **描述**: `has_basic` 三态 (True/False/None) + 多重 if/elif 嵌套, 分支未覆盖"hand 非空但 has_basic is False 且 yes_idx 为 None"情形 → 落到末尾 `_sanitize([0])` 返回未经验证的选项。
- **影响**: 该场景下动作语义可能错误 (引擎问 Mulligan 时选了无意义选项)。
- **修复建议**: 重构为显式三分支: 确认无基础→Yes; 有基础或不可判定→No; 无 Yes/No 选项→`_sanitize([0])` 仅当下标合法时。

### M-5 死代码: `bench_has_674` 计算后从未使用
- **位置**: `main.py:2122`
- **描述**: `bench_has_674` 赋值后无任何引用 (v23 重构后由 `bench_has_non_ex` 取代)。
- **影响**: 误导后续维护者; 属于可读性/维护性问题。
- **修复建议**: 删除。

---

## 低危 (LOW)

### L-1 版本号不一致
- **位置**: `main.py:3` (docstring 标 v23.1) vs `main.py:12-14` (变更块标 v23.2); README 版本表仍为 v23.1 且无 v23.2 行。
- **修复建议**: 统一为 v23.2; README 版本表补充 v23.2 行。

### L-2 README 测试统计陈旧
- **位置**: `README.md` "关键设计原则 7" 声称 "功能测试 17/17, bug 回归 7/7" — 实际 test_agent.py 为 24 项。
- **修复建议**: 更新为最新实测数据。

### L-3 `_handle_main` 遍历残留未用变量 `k`
- **位置**: `main.py:2183` `for k, idx in enumerate(attack_idx)` — `k` 未使用。
- **修复建议**: 改 `for idx in attack_idx`。

### L-4 `.gitignore` 缺少凭据/密钥模式
- **位置**: `.gitignore`
- **描述**: 无 `.env*`、`*.key`、`kaggle_oauth.json` 模式。当前仓库无凭据被跟踪 (已核实), 但未来误提交风险存在。
- **修复建议**: 追加 `.env*`、`*.key`、`*.pem`、`kaggle_oauth.json` 模式。

### L-5 开发脚本边界缺陷
- **位置**: `kaggle_explore.py:301`、`kaggle_verify_v10.py:165` — `random.sample(range(n), max_count)` 在 `max_count > n` 时抛 ValueError 崩溃 (dev 脚本); `gen_card_db.py:48` — `csv.DictReader(open(...))` 文件句柄未关闭; `build_deck.py:205`、`analyze_cards.py:199` — 硬编码本机绝对路径。
- **修复建议**: sample 前夹取 `min(max_count, n)`; 用 `with open(...)`; 路径改 `os.path.dirname(os.path.abspath(__file__))`。

### L-6 陈旧测试套件 `test_v15_optimizations.py` (12/192 失败)
- **位置**: `test_v15_optimizations.py`
- **描述**: 断言基于 v15 旧牌组 (646/935/1086/ポフィン/リザードンex 等已不在 v23 体系), 且 `_TRAINER_IDS` 只覆盖 v23 训练家, 旧训练家卡被当宝可梦 PLAY。属历史套件与牌组演进脱节, 非 v23.1 引入回归 (已逐一甄别)。
- **影响**: 误导性测试结果; 同时暴露设计约束: 未来新增训练家卡必须同步登记 `_TRAINER_PRIORITY`。
- **建议**: 标注为历史套件并迁移断言到当前牌组 (不在本次提交范围内修复, 仅记录)。

---

## 未发现问题领域 (已核查)
- **注入攻击**: 无 SQL/命令/模板注入面 —— main.py 无数据库/Shell/子进程调用, obs 仅用于决策。
- **XSS/CSRF**: 无 HTML 渲染与 Web 端点, 不适用。
- **加密**: 无自实现加密逻辑; 传输走 Kaggle 官方 HTTPS 客户端 (kagglesdk)。
- **凭据泄漏**: 仓库内无 API Key/token 硬编码 (git 跟踪文件扫描 + 全历史核对通过); 唯一敏感输出为 M-1。
- **权限/越权**: 无用户/角色体系, 不适用。
- **并发竞态**: 模块级状态 (`_PENDING_SWITCH_TO_WALL`) 已有"每决策/每对局清除"机制, Kaggle 顺序调用无并发; 无共享文件/网络资源。
- **资源泄漏**: main.py 无文件/网络资源; 仅 dev 脚本 L-5 存在未关闭句柄。
