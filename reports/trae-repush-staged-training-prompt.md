# Trae 任务：PTCG 阶段拆分训练重推（teacher → distill）

## 背景（你需要的全部上下文）

项目：宝可梦 TCG AI Battle（Kaggle 竞赛 pokemon-tcg-ai-battle），工作区
`/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge`（注意不是带空格的别名路径）。

NN 训练管线：本地抽取的张量数据集（ptcg-tensors）+ 训练代码数据集（ptcg-code）
挂载到 Kaggle kernel 做 teacher(BC+AWR)→distill→导出 npz。

刚刚完成的事故处理（你不需要重做，只需知道结论）：
1. 发现 extract.py 的 deck 归属 bug 污染了 8/6 的训练数据（"my deck" 槽位填了对手牌组）。
   上一伦训练（8/6 22:39 启动）因此作废，已于 8/7 10:50 被 12h TLE 砍掉。
2. 污染张量已用修复版 extract.py 重抽，并已上传 ptcg-tensors 新版本
   （151MB，8/7 11:51 生效，deck 归属经 2,320 行抽样验证 100% 正确）。
3. 上轮训练全程 CPU 兜底（Kaggle 分了 P100/sm_60，与预装 torch sm_70+ 不兼容），
   12 小时只跑到 distill 2/8 epochs。**这次必须确认分到 T4**。
4. 两轮代码审计的 30 处修复已全部 commit（最新 a9eebbb），工作区干净。

## 前置事实（已验证，不要重复验证）

- `ptcg-tensors` 数据集已是干净版，kernel metadata 已指向它，无需动。
- `.kaggle_kernel/run_experiment.py` 与修复版 `kaggle_gpu_train.py` 内容一致（含 torch
  重启修复），push 脚本 `scripts/push_t4.py` 会把它推到 kernel
  `daniel1547/ptcg-gpu-train-teacher-distill`（先删旧 kernel 再建 session，shape=GPU T4 x2）。
- `push_t4.py` 读 `kernel-metadata.json` 的 `dataset_sources`（已修复，ckpt 数据集能真正挂载）。
- `train_v2.py --stage` 合法值：`teacher`（BC 8 + AWR 5 epochs）/ `distill`（8 epochs）/ `all`。
- T4 参考时长：teacher ~25-45 分钟，distill ~20-35 分钟（CPU 兜底则会慢 20 倍以上）。
- kaggle CLI 与 kagglesdk 都在 `/opt/homebrew/bin/python3`（受管 Python 没有 kagglesdk）。
- 上传私有数据集用 `kaggle datasets version -p <dir> -r zip -m "<msg>"`；
  查询自己的数据集必须加 `-m`（`datasets list -m -s ptcg`），否则搜不到私有数据集。

## 任务 A：刷新 ptcg-code 数据集（当前线上是 8/6 修复前版本，必须更新）

```bash
cd "/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge"
mkdir -p .kaggle_stage_code && /bin/rm -f .kaggle_stage_code/ptcg_code.tar.gz
COPYFILE_DISABLE=1 tar -czf .kaggle_stage_code/ptcg_code.tar.gz \
  -C inference/dataset \
  train_bc.py train_v2.py model_v2.py export_student.py \
  mlops_registry.py card_vocab.py card_vocab_v1.json \
  -C ../.. inference/dataset/splits
```

验证 tar 里确实是修复版代码（必须命中 grep，否则中止排查）：

```bash
tar -xOf .kaggle_stage_code/ptcg_code.tar.gz train_v2.py | grep -c "checkpoint 已标记 stage=student"
tar -xOf .kaggle_stage_code/ptcg_code.tar.gz train_bc.py | grep -c "early.stop.min.delta\|min_delta"
```

写 metadata 并上传：

```bash
cat > .kaggle_stage_code/dataset-metadata.json <<'EOF'
{"id": "daniel1547/ptcg-code", "title": "ptcg_code", "licenses": [{"name": "other"}]}
EOF
kaggle datasets version -p .kaggle_stage_code -r zip -m "code refresh 2026-08-07 post-audit"
kaggle datasets list -m -s ptcg-code   # 确认 lastUpdated 是今天
```

## 任务 B：设置 stage=teacher 并推送 kernel

编辑 `.kaggle_kernel/run_experiment.py` 第 47 行附近：

```python
# 改前：'--stage', os.environ.get('KAGGLE_STAGE', 'all'),
# 改后：'--stage', os.environ.get('KAGGLE_STAGE', 'teacher'),
```

推送（删除旧 kernel → save → 以 GPU T4 x2 建 session）：

```bash
/opt/homebrew/bin/python3 scripts/push_t4.py
# 期望输出末尾：PUSH_OK shape=GPU T4 x2
```

确认 `.kaggle_kernel/kernel-metadata.json` 的 `dataset_sources` 当前只有
`ptcg-tensors` 和 `ptcg-code`（teacher 首轮不需要 ckpt 数据集）。若里面有
`ptcg-ckpt`，先删掉再推。

## 任务 C：监控（关键：识别 CPU 兜底）

每 10 分钟查一次：

```bash
kaggle kernels status daniel1547/ptcg-gpu-train-teacher-distill
```

处置规则：
- **RUNNING 超过 2 小时** → 高度怀疑又是 P100/CPU 兜底：不要等，手动停止
  （Kaggle 网页 stop，或删除 kernel 重推），重推后仍超时再上报。
- **ERROR** → `kaggle kernels output daniel1547/ptcg-gpu-train-teacher-distill -p reports/kerr_teacher_fail`
  拉日志，把最后 50 行贴进汇报，不要自行改训练代码。
- **COMPLETE** → 拉 output 验证：
  ```bash
  kaggle kernels output daniel1547/ptcg-gpu-train-teacher-distill -p reports/kerr_teacher
  grep -o "Tesla [A-Z0-9]*" reports/kerr_teacher/*.log | head -2   # 必须是 T4，是 P100 则标注
  grep "\[awr\] epoch 5/5" reports/kerr_teacher/*.log              # teacher 阶段跑完的标记
  ls reports/kerr_teacher/ckpt/                                    # 必须有 ckpt_v2_last.pt + teacher_best.pt
  ```

## 任务 D：teacher 完成后接续 distill

1. 把 teacher 的 ckpt 做成数据集（首次 create）：
   ```bash
   mkdir -p .kaggle_stage_ckpt && cp reports/kerr_teacher/ckpt/ckpt_v2_last.pt \
     reports/kerr_teacher/ckpt/teacher_best.pt .kaggle_stage_ckpt/
   cat > .kaggle_stage_ckpt/dataset-metadata.json <<'EOF'
   {"id": "daniel1547/ptcg-ckpt", "title": "ptcg_ckpt", "licenses": [{"name": "other"}]}
   EOF
   kaggle datasets create -p .kaggle_stage_ckpt -r zip
   ```
   （若 ptcg-ckpt 已存在则改用 `datasets version -p ... -r zip -m "<msg>"`）
2. 编辑 `.kaggle_kernel/kernel-metadata.json`：`dataset_sources` 加入
   `"daniel1547/ptcg-ckpt"`（保留原有两项）。
3. 编辑 `.kaggle_kernel/run_experiment.py`：stage 默认值 `teacher` → `distill`。
4. 再次 `/opt/homebrew/bin/python3 scripts/push_t4.py`，按任务 C 同样监控
   （distill 在 T4 上 ~20-35 分钟，超 1.5 小时按 CPU 兜底处置）。

## 任务 E：distill 完成后验收（不达标不许提交）

```bash
kaggle kernels output daniel1547/ptcg-gpu-train-teacher-distill -p reports/kerr_distill
ls reports/kerr_distill/output/    # 应有 model_student.npz
```

把 `model_student.npz` 复制到项目根，然后跑本地 arena（2000 局 × 4 对手，
对阵 v23_2_rules / v22_5_rules / first / random，复用 TLE 轮的跑法）。

提交门槛（双门，都要过）：
1. hybrid（main.py + npz）总胜率 > 纯规则基线（基线参考：总 WR 0.628）
2. vs v23_2_rules 镜像 ≥ 基线 0.520

过门槛：`bash pack.sh` 重新打包 → `python3 submit.py`（有新鲜度守卫，过期 tar 会被拦，
属正常）。不过门槛：不许提交，把 arena 数据贴进汇报。

## 严禁事项

- 不要重抽张量、不要动 `inference/dataset/data/`（数据已验证干净）。
- 不要运行 `scripts/redraw_tensors.sh` 或 `scripts/resume_kernel.sh`
  （前者有 DONE flag 幂等保护，后者流程已手动化在任务 D 里）。
- 不要 commit 任何 `.kaggle_stage_*` 目录（已在 gitignore 覆盖外，注意别 git add）。
- 不要修改 `inference/dataset/` 下的训练代码——发现疑似 bug 就停下汇报。
- 不要用 `--shape GPU` 推 P100。

## 汇报格式（完成后按此回报）

1. ptcg-code 数据集新版本时间戳 + tar 校验结果
2. teacher：session 时长、GPU 型号（日志 Tesla 行）、AWR 末轮 canary_top1
3. distill：session 时长、distill 末轮 canary_top1、npz 大小
4. arena 四门对阵表 + 双门判定结论
5. 若提交：submit 返回的提交号/状态；若未提交：原因
