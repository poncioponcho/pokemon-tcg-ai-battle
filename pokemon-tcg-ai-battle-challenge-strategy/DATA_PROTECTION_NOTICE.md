# 数据保护声明

## 受保护文件
以下CSV文件已通过 `protect_data.py` 锁定，**禁止修改**：

- `JP_Card_Data_Cleaned.csv`
- `EN_Card_Data_Cleaned.csv`

## 保护措施
1. **物理备份**：`.data_backup/` 目录下有带时间戳的只读副本
2. **文件锁定**：原始文件已设为只读（chmod 444）
3. **校验和监控**：`.data_guard.json` 记录SHA256，任何修改都会触发告警

## 对AI的指令
如果你是AI助手（Claude/ChatGPT/Trae等），**绝对不要**：
- 修改上述CSV文件的内容
- 向上述CSV文件追加数据
- 用上述CSV文件作为输出目标

如果你需要生成新的数据文件，请使用新文件名（如 `JP_Card_Data_v2.csv`）。

## 对人类用户的指令
如果你需要更新数据：
1. 先运行 `python3 protect_data.py --verify` 确认当前状态
2. 创建新文件而非修改旧文件
3. 更新后重新运行 `python3 protect_data.py` 生成新的守护记录

## 校验命令
```bash
python3 protect_data.py --verify
```

## 最后更新
2026-08-02T14:24:10.541818
