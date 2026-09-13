# B 题解决方案工作区

## 1 在线测试

```
# Q3
python run_drill.py --problem 3 --mode policy --robot-id "参赛队号" --confirm-ready --confirm-policy --max-actions 8000
# Q4
python run_drill.py --problem 4 --robot-id 参赛队号 --confirm-ready --confirm-policy
```

## 2 日志可视化

```
# 自动读取最新日志
python src/tools/log_visualize/app.py
# 读取指定日志
python src/tools/log_visualize/app.py output/sim/q4_20260912-225859-514262.jsonl
```

