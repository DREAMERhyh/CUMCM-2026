# Q2 人工验证步骤清单

本清单是改变 Q2 状态的唯一依据。当前程序同时输出离散基线和连续 FIM 数值结果，不验证原问题连续空间全局最优。

## 1. 分块单元测试

在 `solution/` 目录运行：

```powershell
python tests/q2/test_unit.py
```

期望：命令以 `OK` 结束；连续保证域顶点均满足最远源距离不超过最小接收半径，CLI 能写出非空 JSON 和 PNG。

## 2. 三类数据与对拍

```powershell
python tests/q2/gen_data.py --mode random --seed 42
python tests/q2/test_duipai.py --dir tests/q2/data/random
python tests/q2/gen_data.py --mode boundary --seed 42
python tests/q2/test_duipai.py --dir tests/q2/data/boundary
python tests/q2/gen_data.py --mode adversarial --seed 42
python tests/q2/test_duipai.py --dir tests/q2/data/adversarial
```

期望：每次对拍报告零失败，并明确“不是连续全局最优证明”。对拍独立复算：有限候选池最小项、保证接收标签、评分公式、连续 FIM 点可行性、连续 FIM 同口径复评分、连续域包含关系和时间记账。

## 3. 手算交叉核对

1. 时间：从 `(0,0)` 移动到 `(3,4)`，距离为 5 m，速度为 5 m/s，所以移动 1 s；同频道检测总时间 `1+0+5=6 s`，换频道时为 `1+1+5=7 s`。可分别调用 `measure_cost((0,0),(3,4),1,1)` 和 `measure_cost((0,0),(3,4),1,2)` 核对。
2. 保证接收：从输出 `region.vertices` 任取候选点 `s`，逐个算 `distance(s, vertex)`。最大值不超过 1000 m 才能标为 `guaranteed_reception=true`；凸函数在凸多边形上的最大值可由顶点达到。
3. 离散候选选择：若存在保证接收候选，只在这些候选中按 `(score, -fim_proxy_per_s, point)` 排序；否则用全部候选。人工抽查 `baseline.selected` 等于第一项。
4. 运行 `python src/q2/cli.py --demo --no-show --output output/q2_manual.png --result-json output/q2_manual.json`。人工确认源位置域、保证接收域、可能接收域、候选点和选中点图例对应 JSON。
5. 图中红色星号是离散基线，蓝色菱形是连续 FIM，黑色空心圆是供 Q3/Q4 使用的最终推荐点。中图横轴为动作时间 `T`、纵轴为最坏后验半径 `R_wc`；人工核对 Pareto 折线上的点不被另一个点同时以更小 `T` 和更小 `R_wc` 支配。
6. 核对 `continuous_fim.budget_solutions` 的三档 `max_action_time_s` 分别等于基线动作时间再加 15/30/60 s，且每个可用解的实际 `action_time_s` 不超过对应上限；执行点不超过 `execution_action_time_limit_s`。
7. 核对连续点到 `region.vertices` 每个顶点的距离都不超过 1000 m，并确认 `continuous_fim.robust_fim_index_per_s >= continuous_fim.best_seed_fim_index_per_s`。这只说明局部细化未劣化该预算下的最佳初始种子，不等价于严格全局最优证明。
8. 红/蓝实线分别是两个方案的 5% 近优域，虚线是 10% 近优域；总览图右下有两个局部放大窗。逐个抽查 `boundary_points`：应同时满足 `worst_case_radius_m <= radius_limit_m` 和 `action_time_s <= action_time_limit_s`。凸包内部未经逐点验证，因此只验收为“近优域可视化近似”，不得称置信区间或严格连续子水平集。
9. 分别用 `--region-mode online` 和 `--region-mode offline` 导图；后者采样更密、通常更慢。若现场真实计算时间紧，可用 `--region-mode off`，这不改变确切推荐点。

## 4. 记录与状态

- 将测试命令、数量、失败详情、手算和图形检查填入 `test_res.md`。
- 全部通过后，由人工更新状态；AI 不得代为标记【已验证】或【模拟器未测试】。
- 失败时保持【待验证】，记录输入 JSON、实际/期望输出和复现命令。
