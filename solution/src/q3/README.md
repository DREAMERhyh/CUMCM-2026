# Q3：全向干扰源定位与清除

题意：机器人需要在多个频道上寻找全向干扰源，通过移动、检测、定位和清除提高规定时间内的完成效果。

当前状态：【待验证】。

策略仍是待对拍的算法原型。当前细化阶段会调用 Q2 的“多预算连续 FIM + 集合复评分 + Pareto 安全裁决”，使用最终混合推荐点；单次 FIM 真实墙钟上限默认 6 s，5%/10%近优域计算在线关闭。

`cli.py` 仍只运行本地 `sim.fake.FakeSimulator`，但默认参数已与在线策略一致：最多两次细化、单次 FIM 6 s。上线前可运行：

```powershell
python src/q3/cli.py --max-refinements 2 --fim-cpu-time-limit-s 6 --output output/q3_offline/online_like_demo.json
```

官方通信、三动作演练烟雾测试和现场日志入口位于 `src/sim/`。必须先按 `tests/sim/verify_manual.md` 完成 smoke；在人工核对通过前，不得把本地通过理解为 Q3 官方策略通过。
