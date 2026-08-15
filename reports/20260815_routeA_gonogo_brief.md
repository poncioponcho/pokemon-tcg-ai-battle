# 路线 A（真 RL override 层）立刻立项的 go/no-go 核算委托

委托方：Kimi（审计线）→ codex（执行线）
时间：2026-08-15 12:20 CST
性质：**先核算、后开工**。本文件只要求一份 go/no-go 备忘录；未获用户确认前不立项、不改 exact v22、不提交 Kaggle、不动 Automation。

## 背景（一句话）

v22 的局部空间已全部经预注册闸证伪：guard 开关（本地 0 触发 + live 0/82）、数值 offset（W/L 双输）、job 级控制面（44/8251 无复现）、结构 2×2 消融（三臂全负）、Dawn（反向因果）。剩余唯一高上限方向：对高暴露 MAIN 决策训练 advantage/override 层，v22 fallback 永远兜底。用户问"立刻做路线 A 来不来得及"，请逐项核算以下疑难点后给出明确 GO / NO-GO。

## 疑难点清单

### 1. 截止时间与倒排窗口

比赛确切截止时刻是哪天哪时（时区）？从现在起，扣除每日精确重交 v22 的操作成本和最终打包/提交缓冲，净训练+评估窗口有多少小时？给出 milestone 时间表，并为每个阶段写明 kill criteria（什么条件下当场停止，不留"半立项"）。

### 2. 瓶颈核算：CPU 还是 GPU

native 引擎是 CPU dylib，episode 生成吃 CPU；override 头（线性/小型 advantage 模型）训练开销应极小。请实测核算：

- 本地现有并行度下的 episode 吞吐（局/秒）；
- 达到统计功效所需的总局数（见疑难点 3）折合墙钟时间；
- 结论：瓶颈若在 episode 生成，则 Kaggle P100/T4×2 帮不上忙，"GPU 预算紧"不是阻塞点——请明确确认或纠正这一点，它直接决定路线 A 的资源前提。

### 3. 统计功效与方差（最硬的一条）

终局 W/L 信号、平均 ~186 步/局、无配对（native shuffle 不可播种，CRN 物理不可能）。请给出硬数字而非乐观估计：

- 把一个 context 桶的 advantage 估到 ±3pp 需要多少局？
- 高暴露 MAIN context 有多少个桶？各桶在 82 场 live replay 决策面数据里的实际频率是多少？
- 合并回答："训练多少墙钟小时后，才可能出现一个可过 screen 闸的可测信号？"

### 4. override 的挂载点与上下文空间

- 挂在哪一层：fallback 输出之后做覆盖裁决，还是嵌入 MAIN 决策点？
- 开放哪些 context / 回合阶段给学习层？（决策面数据显示仅 44/8251 次选择被上层改写，override 层的可干预面必须明确枚举。）
- 不可破坏的不变量：硬合法性 guard 不可绕过；select/protocol 流程不被 override 打断；`select-none-before-every-game-v1` 的 episode reset 继续生效。

### 5. fault 与超时预算

override 推理必须满足 Kaggle 每步时间限制且零 fault。方案中写明：任何不确定/超时/异常 → 无条件回退 exact fallback；本地 n 局 0 fault 才可进 W/L 闸。

### 6. 对手分布漂移

本地四腿 ≠ live meta（live 有 Dragapult / Archaludon / Crustle 等，本地没有）。两个子问题：

- (a) 82 场 replay 里是否含对手完整牌表？若有，构建 live-derived 代理腿加入 screen/回归；若没有，给出替代方案。
- (b) 训练对手分布如何选取，避免过拟合本地四腿（C-002 的教训）。

### 7. 仪器适配

新件行为必然偏离 exact v22，现有 live-replay 0-mismatch 自检需要扩展为"新件版本"：验证 observation 对齐与归因仍工作，而非要求动作一致。同时为 override 层定义行为 canary：在同批 82 场 replay 状态上的首次分叉率必须落在预设区间内，避免重演 TOO_BROAD（70–85% 分叉）/ TOO_SPARSE（0–2/82）。

### 8. 过闸标准（沿用 + 加码）

全部沿用既有闸：screen（四腿加权相对 incumbent +3pp、v22 主腿 ≥53%、任一跨牌组腿不崩 >10pp）→ n≥256 主闸（WR ≥55%、相对同批 incumbent control +3pp、零 fault）。追加一条消融要求：override 层须与"同架构随机初始化 override"对照臂比较，证明收益来自学习而非结构扰动。

### 9. 与每日提交节奏的兼容性

训练期间每日仍精确重交 v22（SHA `599e19ae…b4c8bfcf`）不变；新件只有过完全部闸才替换当日提交额度。确认此安排不违反"每日真实反馈"硬约束。

### 10. 回退条件

若任何一项核算不满足（窗口不足 / 功效不足 / 对手牌表不可得 / 挂载点会破坏不变量），输出明确 NO-GO，将路线 A 归档为赛后项目，并把理由记入 ledger，不留模糊态。

## 输出要求

一页 go/no-go 备忘录，含每项的核算数字（不是定性判断），落盘 `reports/`，记 ledger，HANDOFF 加一行指针。
