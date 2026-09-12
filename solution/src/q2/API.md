# Q2 接口契约

当前状态：【待验证】。现有实现同时保留离散集合评分基线和连续测点坐标的鲁棒 FIM 数值优化；两者都不声称求得原问题的连续全局最优点。

## 对外接口

### `Q2Config`

`Q2Config(error_deg=1.005, arena_radius=1800.0, min_receive_radius=1000.0, max_receive_radius=1500.0, circle_sides=24, q2_version="new", candidate_region_sides=72, scenario_limit=8, uncertainty_seconds_per_metre=0.5, continuous_fim_enabled=True, fim_samples_per_edge=4, fim_initial_step_m=200.0, fim_min_step_m=2.0, fim_max_iterations=120, fim_seed_limit=10, fim_extra_time_budgets_s=(15.0,30.0,60.0), fim_execution_extra_time_s=30.0, fim_cpu_time_limit_s=8.0, near_optimal_region_mode="online", near_optimal_region_cpu_limit_s=5.0, near_optimal_time_slack_s=10.0, near_optimal_tolerances=(0.05,0.10))`

各半径和 FIM 步长单位 m，`error_deg` 单位 °。`q2_version` 可取 `new/legacy`，默认 `new`：新版从 `circle_sides` 边粗外包出发，在实际交会边界补充端点切线和超差切线；旧版只使用固定 `circle_sides` 边外切正多边形。该开关只改变源位置圆域的保守近似方式，不改变离散候选、连续 FIM、Pareto 或近优域流程。`candidate_region_sides` 仍是保证/可能接收域的圆近似方向数。`scenario_limit` 是集合评分场景上限；`uncertainty_seconds_per_metre` 只用于报告工程折中分数。`fim_extra_time_budgets_s` 是相对离散基线增加的虚拟动作时间预算，默认分别多 15/30/60 s；`fim_execution_extra_time_s` 指定连续分支可作为执行点的最大额外虚拟时间。`fim_cpu_time_limit_s` 是本地 CPU 墙钟保护上限，与机器狗虚拟时间不同。`near_optimal_region_mode` 可取 `off/online/offline`，后两种分别使用稀疏/较密局部采样。

### `build_candidate_regions(source_region, *, min_receive_radius=1000.0, max_receive_radius=1500.0, circle_sides=72)`

输入 Q1/共享模块产生的有界源位置区域，返回连续的保证接收域内近似和可能接收域外近似。

### `optimize_continuous_fim(source_region, guaranteed_region, *, first_position, current_position, current_channel, target_channel, min_receive_radius=1000.0, seed_points=(), samples_per_edge=4, initial_step_m=200.0, min_step_m=2.0, max_iterations=120, seed_limit=10, action_time_limits_s=(), cpu_time_limit_s=None)`

在保证接收域中连续改变第二测点坐标，以“各源边界场景中最小的两次示向 FIM 行列式 / 动作时间”为目标进行确定性多起点投影模式搜索。`action_time_limits_s` 可一次传入多个绝对动作时间上限，各预算共享场景和缓存；返回的 `budget_solutions` 给出每个预算下的候选。`cpu_time_limit_s` 是真实 CPU 墙钟安全截止。这里仅测点坐标连续，源位置鲁棒性仍由有限边界场景近似，因此 `optimality_claim` 不是原问题全局最优证书。

### `plan_measurement(region, observations, *, current_position=None, current_channel=None, target_channel=None, config=Q2Config())`

对已有有界区域和一个或多个 `BearingObservation` 评分第二测点。当前位置默认取最后一次观测位置；目标频道默认取首次有效示向观测的频道。

### `plan_second_point(first_observation, *, current_channel=None, config=Q2Config())`

Q2 常用入口。`first_observation` 必须是 `BearingObservation(..., result="direction", bearing_deg=...)`；函数先构造物理源位置域，再调用 `plan_measurement`。

命令行 `src/q2/cli.py`、`src/q3/cli.py`、`src/q4/cli.py` 和 `src/sim/cli.py` 均接受 `--q2-version new|legacy`，默认 `new`。必须在一次新测试启动前选择版本；正在运行的策略状态不支持中途换版。

## 输入 JSON

测试数据与 `plan_second_point` 的映射如下：

```json
{
  "first_observation": {
    "position": [-600.0, -300.0],
    "channel": 1,
    "result": "direction",
    "bearing_deg": 35.89
  },
  "current_channel": 1,
  "config_overrides": {}
}
```

| 字段 | 类型 | 单位/范围 | 含义 |
|---|---|---|---|
| `position` | 长度 2 数组 | m，有限数 | 第一次检测位置 |
| `channel` | 整数 | `1..20` | 有效信号频道 |
| `result` | 字符串 | 必须为 `direction` | 第一检测结果 |
| `bearing_deg` | 数值 | °；当前模型按角度制使用 | 第一示向度 |
| `current_channel` | 整数或省略 | `1..20` | 移动前机器人频道 |
| `config_overrides` | 对象 | `Q2Config` 同名字段 | 可选试验配置；可用 `{"q2_version":"legacy"}` 切换旧版 |

最小合法输入即上例去掉 `current_channel` 和 `config_overrides`。边界示例：

```json
{"first_observation":{"position":[-1500,0],"channel":20,"result":"direction","bearing_deg":359.99},"current_channel":1,"config_overrides":{}}
```

Python 调用时将 JSON 数组转为元组：

```python
obs = BearingObservation(position=(-600.0, -300.0), channel=1,
                         result="direction", bearing_deg=35.89)
plan = plan_second_point(obs)
```

`tests/q2/gen_data.py` 同样外包 `{"case_id", "mode", "input", "oracle"}`；规划器只读取 `input`，`oracle` 只用来确认合成示向误差合法。

## 输出 JSON

核心字段如下；完整输出还保留每个候选的审计信息。

```json
{
  "method": "time_budgeted_fim_pareto_hybrid",
  "selected_point": [-100.0, 566.0],
  "recommendation_source": "continuous_fim",
  "selected": {
    "candidate_id": "FIM-T02",
    "point": [-100.0, 566.0],
    "guaranteed_reception": true,
    "worst_case_radius_m": 80.0,
    "action_time_s": 162.0,
    "score": 202.0,
    "time_breakdown": {"movement_s":157.0,"switching_s":0.0,"measurement_s":5.0,"optical_s":0.0,"laser_s":0.0,"total_s":162.0}
  },
  "baseline": {
    "method": "discrete_set_score",
    "selected_point": [0.0, 0.0],
    "selected": {"worst_case_radius_m":150.0,"action_time_s":132.0,"score":207.0},
    "near_optimal_regions": {"5pct": {}, "10pct": {}}
  },
  "continuous_fim": {
    "status": "ok",
    "method": "time_budgeted_continuous_robust_fim_pattern_search",
    "selected_point": [-100.0, 566.0],
    "robust_fim_index_per_s": 0.0012,
    "selected_score": 202.0,
    "score_delta_vs_baseline": -5.0,
    "selected": {},
    "execution_action_time_limit_s": 162.0,
    "budget_solutions": [],
    "candidates": [],
    "near_optimal_regions": {"5pct": {}, "10pct": {}},
    "optimality_claim": "numerical_near_global_for_fim_surrogate"
  },
  "pareto_front": [],
  "comparison": {
    "score_definition": "action_time_s + uncertainty_seconds_per_metre * worst_case_radius_m",
    "lower_is_better": true,
    "baseline_score": 207.0,
    "continuous_fim_score": 202.0,
    "continuous_minus_baseline": -5.0
  },
  "candidate_regions": {
    "guaranteed_reception": {"status":"bounded","vertices":[],"approximation":{"relation_to_exact_region":"inner"}},
    "possible_reception": {"status":"bounded","vertices":[],"approximation":{"relation_to_exact_region":"outer"}}
  },
  "candidates": [],
  "region": {},
  "config": {},
  "limitations": []
}
```

`baseline.selected_point` 是原离散搜索结果；`continuous_fim.selected_point` 是满足执行时间预算、再用集合指标复评分后选出的连续结果。顶层 `selected_point`/`selected` 是二者按 `(worst_case_radius_m, action_time_s)` 词典序作出的最终安全推荐，`recommendation_source` 说明来源；Q3/Q4 调用该顶层推荐点。`score = action_time_s + uncertainty_seconds_per_metre × worst_case_radius_m` 仅用于并列报告，不覆盖上述主次目标。

`continuous_fim.budget_solutions` 保留 15/30/60 s 三档 FIM 解，`pareto_front` 给出动作时间与最坏半径互不支配的候选。两个分支各自包含 `near_optimal_regions.5pct/10pct`：采样点同时满足 `R <= (1+eta)R_ref` 和 `T <= T_ref+10s`，多边形是这些已验证采样点的凸包。它们是便于描述“选取区间”的局部可视化近似，不是统计置信区间，也不是凸包内部处处达标的数学证书。保证接收域为空时连续结果为 `status="unavailable"`。Python 点为元组，JSON 中为数组。

## 前置条件与不变量

- 第一观测必须为有效 `direction`，频道为 `1..20`。
- 物理源位置域同时使用示向扇区、半径 1800 m 目标域和距首测点不超过 1500 m 的接收约束。
- `q2_version="new"` 时，源位置域保留初始整圆外切半平面，并只增加包含相应真实圆盘的切线，因此自适应结果不会排除真实源且嵌套于原粗外包；`legacy` 时完整保留固定外切正多边形。`region.approximation.q2_version` 和 `kind` 可审计实际分支。
- 保证接收域是 `max distance ≤ min_receive_radius` 的保守内近似；可能接收域是 Minkowski 和的保守外近似。
- 单次测量时间为移动距离/5 + 换频道 0 或 1 s + 检测 5 s。
- `worst_case_radius_m` 只覆盖有限代表点与有限误差样本，不是连续最坏情形证明。
- 连续 FIM 以源域边界采样近似最差信息量，并采用有限多起点模式搜索；它是可复现的数值近似，不是严格全局最优证明。
- 近优域只验证采样点；展示的凸包内部没有连续保证，论文中必须称“5%/10% 近优域近似”，不能称“置信区间”。

## 官方模拟器边界

模拟器通过 `POST /measure` 接收位置和频道，并返回检测结果；仅 `measure_result="direction"` 时包含 `svd_deg`。运行层把成功方向观测映射为 `BearingObservation(position, channel, result="direction", bearing_deg=svd_deg)`；本模块内部生成候选域、候选点和评分。HTTP字段、错误处理、幂等重试与串行调用由 `src/sim/` 负责，本模块不直接发送网络请求。
