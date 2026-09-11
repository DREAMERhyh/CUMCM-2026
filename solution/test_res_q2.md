# B-Q2 自动测试与试验结果

当前状态：【待验证】。本文件记录 AI 执行的自动检查，不能替代队员按 `tests/q2/verify_manual.md` 完成的人工验收，也不包含官方模拟器测试。

## 本轮实现范围

- 保留原离散集合评分基线 `baseline`。
- 连续 FIM 在相对基线多 15/30/60 s 三档虚拟动作时间预算下搜索；三档共享场景与缓存。
- 所有连续候选均送回原有界误差集合评分器，统一得到最坏后验半径 `R_wc`、动作时间 `T` 和工程分数 `T+0.5R_wc`。
- 连续执行点默认最多比离散基线多 30 s；最终推荐按 `(R_wc,T)` 选择，因此有限测试场景下不会比离散基线的半径更差。
- 输出 `T-R` Pareto 前沿；离散和连续分支分别输出 5%/10% 近优域近似。
- Q3/Q4 继续读取顶层 `selected_point`，现在会使用上述最终推荐点。

## 已执行测试

```powershell
python -B -m unittest solution.tests.q2.test_unit -v
python -B solution/tests/q2/test_duipai.py --dir solution/tests/q2/data/random
python -B solution/tests/q2/test_duipai.py --dir solution/tests/q2/data/boundary
python -B solution/tests/q2/test_duipai.py --dir solution/tests/q2/data/adversarial
```

结果：Q2 单元/CLI 共 9 项全部通过，耗时 54.668 s；随机、边界、对抗三类对拍各 4 例，共 12 例，全部 0 失败。对拍覆盖离散候选选择、接收域包含关系、时间记账、三档 FIM 预算、连续点同口径复评分、最终推荐半径安全性和近优域结构。

全项目回归命令 `python -B -m unittest discover -s solution/tests -t solution -v` 共 76 项全部通过，耗时 61.705 s；其中 Q3 7 项、Q4 4 项通过。可视化增加局部放大窗后，Q2 CLI 测试另行复跑 1 项通过，耗时 8.689 s。

## 200 例配对比较

```powershell
python -B solution/tests/q2/benchmark_200.py --count 200 --seed 20260911 --workers 16 --output solution/tests/q2/analysis/q2_200_case_comparison.json
```

固定种子 20260911 的 200 个合法首测案例全部可比较：

| 指标 | 离散基线 | 分时限连续 FIM | 连续 FIM 更优占比 |
|---|---:|---:|---:|
| 最坏后验半径均值 | 119.037 m | 70.082 m | 200/200 = 100% |
| 最坏后验半径中位数 | 122.034 m | 75.050 m | 200/200 = 100% |
| `T+0.5R` 均值 | 169.573 s | 174.802 s | 76/200 = 38% |
| `T+0.5R` 中位数 | 201.759 s | 199.701 s | 76/200 = 38% |

连续分支平均多用 29.706 s 虚拟动作时间，主指标平均减少 48.955 m。200 例的 16 进程墙钟时间为 122.015 s。完整逐例数据见 `tests/q2/analysis/q2_200_case_comparison.json`。

## 单案例真实计算开销粗测

同一固定演示输入、当前机器单次测得：

- 仅离散基线且关闭近优域：3.741 s；
- 分时限 FIM 且关闭近优域：4.115 s；
- 默认在线近优域：6.919 s；
- 较密离线近优域：17.227 s。

这是 CPU/墙钟时间，不是机器狗虚拟时间；机器负载和 Python 环境会改变数值。在线默认方案相对仅离散粗测增加约 3.178 s，远低于题目 20 min 的真实时间上限，但正式上机仍应复测。

## 演示与可视化

```powershell
python -B solution/src/q2/cli.py --demo --region-mode online --no-show --output solution/output/q2_pareto_regions.png --result-json solution/output/q2_pareto_regions.json
```

命令成功生成 PNG 和 JSON。图中同时展示两个确切点、最终推荐点、两套 5%/10% 近优域近似和 `T-R` Pareto 前沿。图像已做一次人工目视检查，未见明显裁剪或图例遮挡。

## 结论和边界

自动测试支持当前程序在这些有限样例上的正确性与一致性，但不证明原连续问题的全局最优，也不替代官方模拟器实测。近优域凸包只用于展示“选取区间”的局部近似，凸包内部没有逐点证书。Q2 仍保持【待验证】，由队员按人工清单验收后决定是否变更状态。
