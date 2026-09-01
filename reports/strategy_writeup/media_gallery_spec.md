# 媒体画廊规格（Media Gallery Spec）

> 6 张图/表，数据全部取自本仓库可溯源文件。渲染后上传 Kaggle Writeup 媒体画廊，
> 文件名建议带序号。正文引用位置已标注（`writeup_en.md` 对应章节）。

---

## fig1_architecture — 分层决策架构图

**用途**：§3.1 配图，一图讲清「为什么这样分层」。
**绘制建议**：自上而下 5 层（Layer 4 → 0），每层左侧一个职责框、右侧一个动机框；最底层用深色表示「合法性契约」，旁注 `no code path emits an invalid action`。

```
┌ Layer 4  guard policies (23)          ← 生于回放诊断，每个有记录在案的触发条件
├ Layer 3  continuity scheduler          ← 回合目标/阶段推断 + 局内战略记忆（跨局清零）
├ Layer 2  deadline ledger               ← 资源账本 + 字典序截止调度（替换固定优先级表）
├ Layer 1  processing queue + turn DAG   ← 提交任务队列，先补前置依赖再执行
└ Layer 0  validated fallback (2,545 行) ← 唯一契约：动作合法（数量/下标/无重复）
```

旁注数据：`policies/v22` 共 ~7,600 行；23 个守卫文件；`main.py` 入口仅 3 行转发。

---

## fig2_deck — 60 卡构成表

**用途**：§2.1 配图（正文已有表格，可渲染成图增强画廊）。
**数据**：同 `writeup_en.md` §2.1 表格。

补充标注：
- 能量仅 10 张（无特殊能量）→ Punk Up 一次性补能后能量局结束
- 教练卡 32 张中 21 张是检索/抽滤（Poffin 4 + Gym 4 + Petrel 4 + Lillie 4 + Pad 4 + Dawn 1 + Pokégear 1）
- 唯一 ACE SPEC：Unfair Stamp
- 无任何硬币判定卡（全池审查后拒绝）

---

## fig3_h2h — 本地四腿 H2H + Wilson CI 表

**用途**：§5 配图。**数据来源**：`reports/20260814_grim_v22_delivery.md` 与 `20260814_grim_v22_*.json`。

| 对手 | 场次 | 胜-负 | 胜率 | 备注 |
|------|------|-------|------|------|
| Alakazam | 64 | 51–13 | 79.7% | 修复隔离 runner 后独立批次 |
| retreat pivot 基线 | 64 | 42–22 | 65.6% | 本队早期 pivot 方案 |
| 完整 Grim v1 | 64 | 39–25 | 60.9% | 同卡组不同策略 |
| match-up router | 64 | 38–26 | 59.4% | 路由层候选 |

**必须标注**：全部 n=64、**零 fault**；引擎无 native shuffle seed → 同 seed 重跑为独立批次；所有差异需 >±2.2pp 噪声带才宣称。
**图注必带 why**（策略论证 ≠ 裸数字）：Froslass 的 Icy Curtain 对 ability-loop 卡组每回合收税 → 解释了为什么 Alakazam 腿胜率最高；这一句把表格从「数据」升级为「论证」。
**补充条目**（同图下注）：v22 vs v29 合并 383 局 208–175（54.3%），Wilson 95% ≈ 49.3–59.2% → 保留 v22。

---

## fig4_guards — 23 守卫策略分组清单

**用途**：§3.1 Layer 4 配图。**数据来源**：`policies/v22/` 文件名 + ledger。

| 组 | 守卫（文件名前缀） | 数量 | 目的 |
|----|--------------------|------|------|
| Stall 防拉 | boss_damaged_basic_stall / boss_unenergized_kadabra_stall / retreat_morgrem_stall | 3 | 防 Boss's Orders 强拉受损基础宝可梦 |
| 蓄能保全 | energized_impidimp_preservation / energized_morgrem_preservation / retreat_impidimp_preserve_grimmsnarl | 3 | 保已蓄能进化链成员 |
| 晋升时机 | damaged_munkidori_early_promotion / low_hp_mega_munkidori_promotion / energized_munkidori_promotion / energized_mixed_basic_promotion / rare_candy_impidimp_promotion / sacrificial_froslass_mega_promotion | 6 | 谁先上/谁牺牲的裁决 |
| 贴能前置 | preability_active_impidimp_attachment / preability_morgrem_attachment / preattack_froslass_attachment / prestamp_attachment | 4 | 能量花在触发能力/攻击前 |
| KO 数学 | munkidori_lethal / shadow_bullet_double_ko / shadow_bullet_immediate_mega_ko | 3 | 双杀/致命线计算 |
| Meta 特化 | zoroark_guard / zoroark_pokepad_guard / dead_poffin_guard / punkup_backup_guard / manual_guards | 4+1 | 佐罗亚克/死牌/备用引擎 |

---

## fig5_lb — 线上表现叙事图

**用途**：§5 配图。**红线**：禁止把不同 ref 的早期分数拼成单一时间序列（官方评分收敛期约 22–24h，600 起评）。

**建议图**：**唯一 headline = 团队最终收敛值**：rating ≈ 783，rank 924/6838（top ≈13.5%），40 次提交零 runtime 错误。
辅助小字（明确标注「短期隐含、非结算值」）：成熟 ref `55539446` 前 29 场公开局 15–14（51.7%），对手均分 812.22 → 隐含 mu* ≈ 829.6；29 场窗口恰在本队噪声带边缘，不作 headline。
图注：`final-2 双槽 = 同一冻结归档（SHA 599e19ae）`；「早期读数 883.1 为未收敛值，不计账」。

---

## fig6_methodology — 测量闭环流程图

**用途**：§4 配图，原创性轴的核心可视化。

```
回放诊断（失败局 → 假设）
        ↓
单卡置换爬山（screen n=1000 → confirm n=4000）
        ↓
3 种子标准闸（mirror + vs_first，Wilson CI 下界）
        ↓
STRONG / MARGINAL / REGRESS 分类
        ↓（>±2.2pp 且 STRONG 才上线）
冻结归档（两次打包 SHA 一致 → 解包复验）
        ↓
隔离 runner 四腿 H2H（零 fault 才交付）
        ↓
线上：按 ref 归集 episodes + 对手强度校正 → 不追瞬时分
```

---

## 渲染提示

- 图 1/4/6 可用 mermaid/Excalidraw 出 PNG；图 2/3 直接用表格截图。
- 所有数字必须与 `00_框架.md` §1 的事实锁定一致，改一处全改。
- 上传后正文加 `(see Fig. N)` 引用；Kaggle 画廊按图名排序建议：deck → architecture → methodology → h2h → guards → lb（对应阅读顺序 2,1,6,3,4,5）。
