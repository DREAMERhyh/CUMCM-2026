# Q2：选择第二个检测点

当前状态：【待验证】。

## 题目在问什么

已在第一个位置收到某频道信号和示向度后，要选择第二个检测位置。程序既给出连续的“保证能收到”和“可能收到”区域，也同时运行原离散集合评分基线和新的连续测点坐标 FIM 优化。

## 算法步骤

1. 用目标圆、首测接收圆和示向扇区建立源位置区域。默认 `q2_version="new"`：先以 `circle_sides` 边整圆外切得到有界粗外包，再补充端点切线和超差切线；`legacy` 保留旧版固定外切正多边形，供启动前消融比较。
2. 计算第二测点的保证接收连续域（内近似）与可能接收连续域（外近似）。
3. 从首测方向、区域中心和保证域中心等位置生成有限候选。
4. 对有限源位置及误差样本模拟第二次观测，计算最坏后验半径。
5. 离散基线在保证接收候选中最小化“动作时间 + 不确定半径折算”；若该集合为空则回退到全部候选。
6. 连续 FIM 方法在离散基线动作时间再增加 15/30/60 s 的三档预算下，分别搜索“最差边界场景的两示向 FIM / 动作时间”。
7. 把三档连续候选送回集合评分器，统一计算最坏后验半径和动作时间；在允许多 30 s 的执行预算内，按“半径优先、时间次之”选连续代表点。
8. 将离散点、连续点和其他分时限候选组成 `T-R` Pareto 前沿；顶层推荐点保证不会比离散基线的有限场景最坏半径更差。
9. 在两个代表点附近采样，输出并绘制 5%/10% 近优域，作为题目“选取区间”的可审计近似。

| 算法步骤 / 数学关系 | 对应函数 | 说明 |
|---|---|---|
| 首测后的物理源域与版本分流 | `common/domain.py:build_region_from_observations` | `new` 输出自适应外近似；`legacy` 输出固定外切正多边形 |
| 新观测后的同版本更新 | `common/domain.py:extend_region_with_observation` | 新版局部细化，旧版追加固定外切圆；禁止同一后验混用版本 |
| 保证/可能接收连续域 | `candidates.py:build_candidate_regions` | 分别是内近似、外近似 |
| 生成离散搜索点 | `candidates.py:generate_candidates` | 确定性有限候选 |
| 有限场景评分 | `planner.py:score_candidates` | 不代表连续全局最坏情形 |
| 连续测点 FIM 优化 | `continuous_fim.py:optimize_continuous_fim` | 源不确定性仍用边界场景近似 |
| 通用测点规划 | `planner.py:plan_measurement` | 接受已有区域与观测 |
| Q2 常用入口 | `planner.py:plan_second_point` | 从第一观测开始 |
| 移动/换频/检测计时 | `common/time_model.py:measure_cost` | `距离/5 + 0或1 + 5` 秒 |

## 输入输出示例

```python
from common.models import BearingObservation
from q2 import plan_second_point

first = BearingObservation((-600.0, -300.0), 1, "direction", 35.89)
plan = plan_second_point(first)
print(plan["baseline"]["selected_point"], plan["baseline"]["selected"]["score"])
print(plan["continuous_fim"]["selected_point"], plan["continuous_fim"]["selected_score"])
print(plan["recommendation_source"], plan["selected_point"])
```

字段、配置和返回结构见 [API.md](API.md)。绘图演示：

```powershell
python src/q2/cli.py --demo --no-show --region-mode online --output output/q2.png --result-json output/q2.json
```

上式不写参数时默认新版；启动前添加 `--q2-version legacy` 即可生成旧版结果和图。输出中的 `config.q2_version` 及 `region.approximation.kind` 可用于核对实际版本。

## 测试与局限

```powershell
python tests/q2/test_unit.py
python tests/q2/gen_data.py --mode random --seed 42
python tests/q2/test_duipai.py --dir tests/q2/data/random
python -B tests/q2/benchmark_200.py --count 200 --seed 20260911 --workers 16
python -B tests/q2/benchmark_arc_refinement.py --count 200 --plan-count 20 --repeats 7 --seed 20260912
```

200 例配对结果及指标选择讨论见 `tests/q2/analysis/q2_200_case_comparison.md`。规划器以最坏后验半径为主指标、动作时间为次级指标；FIM 负责生成候选，最终由统一集合评分和 Pareto 规则裁决。

人工验收必须按 `tests/q2/verify_manual.md` 执行。离散结果在 `baseline.selected_point`，连续结果在 `continuous_fim.selected_point`，顶层 `selected_point` 是供 Q3/Q4 使用的推荐点。`--q2-version new|legacy` 在启动前选择源域算法，默认 `new`；`--region-mode online` 适合现场，`offline` 用较密采样生成论文图，`off` 用于只比较选点。5%/10% 近优域是局部采样凸包近似，不是统计置信区间或连续证书。新版圆弧细化始终保留原粗外切半平面，因此不会排除真实源；旧版同样保守但通常更松。连续 FIM、源域最坏情形和圆域都仍含有限近似，不能写成原问题连续空间全局最优证明。
