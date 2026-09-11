# Q2 接口契约

当前状态：【待验证】。现有实现同时保留离散集合评分基线和连续测点坐标的鲁棒 FIM 数值优化；两者都不声称求得原问题的连续全局最优点。

## 对外接口

### `Q2Config`

`Q2Config(error_deg=1.005, arena_radius=1800.0, min_receive_radius=1000.0, max_receive_radius=1500.0, circle_sides=24, candidate_region_sides=72, scenario_limit=8, uncertainty_seconds_per_metre=0.5, continuous_fim_enabled=True, fim_samples_per_edge=4, fim_initial_step_m=200.0, fim_min_step_m=2.0, fim_max_iterations=120, fim_seed_limit=10)`

各半径和 FIM 步长单位 m，`error_deg` 单位 °；`circle_sides` 和 `candidate_region_sides` 是圆的多边形近似边数；`scenario_limit` 是基线有限评分场景上限；`uncertainty_seconds_per_metre` 把剩余半径折算为评分秒数。`continuous_fim_enabled` 控制是否运行连续优化，其余 `fim_*` 字段控制边界场景密度、多起点投影模式搜索的步长与预算。

### `build_candidate_regions(source_region, *, min_receive_radius=1000.0, max_receive_radius=1500.0, circle_sides=72)`

输入 Q1/共享模块产生的有界源位置区域，返回连续的保证接收域内近似和可能接收域外近似。

### `optimize_continuous_fim(source_region, guaranteed_region, *, first_position, current_position, current_channel, target_channel, min_receive_radius=1000.0, seed_points=(), samples_per_edge=4, initial_step_m=200.0, min_step_m=2.0, max_iterations=120, seed_limit=10)`

在保证接收域中连续改变第二测点坐标，以“各源边界场景中最小的两次示向 FIM 行列式 / 动作时间”为目标进行确定性多起点投影模式搜索。返回的 `robust_fim_index_per_s` 越大越好。这里仅测点坐标连续，源位置的鲁棒性仍由有限边界场景近似，因此 `optimality_claim` 是 `numerical_near_global_for_fim_surrogate`，不是原问题全局最优证书。

### `plan_measurement(region, observations, *, current_position=None, current_channel=None, target_channel=None, config=Q2Config())`

对已有有界区域和一个或多个 `BearingObservation` 评分第二测点。当前位置默认取最后一次观测位置；目标频道默认取首次有效示向观测的频道。

### `plan_second_point(first_observation, *, current_channel=None, config=Q2Config())`

Q2 常用入口。`first_observation` 必须是 `BearingObservation(..., result="direction", bearing_deg=...)`；函数先构造物理源位置域，再调用 `plan_measurement`。

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
| `config_overrides` | 对象 | `Q2Config` 同名字段 | 可选试验配置 |

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
  "method": "baseline_and_continuous_fim",
  "selected_point": [0.0, 0.0],
  "selected": {
    "candidate_id": "C01",
    "point": [0.0, 0.0],
    "guaranteed_reception": true,
    "worst_case_radius_m": 120.0,
    "action_time_s": 205.0,
    "score": 265.0,
    "fim_proxy_per_s": 0.0,
    "time_breakdown": {"movement_s":200.0,"switching_s":0.0,"measurement_s":5.0,"optical_s":0.0,"laser_s":0.0,"total_s":205.0}
  },
  "baseline": {
    "method": "discrete_set_score",
    "selected_point": [0.0, 0.0],
    "selected": {}
  },
  "continuous_fim": {
    "status": "ok",
    "method": "continuous_position_robust_fim_pattern_search",
    "selected_point": [-100.0, 566.0],
    "robust_fim_index_per_s": 0.0012,
    "selected_score": 234.4,
    "score_delta_vs_baseline": 27.2,
    "selected": {},
    "optimality_claim": "numerical_near_global_for_fim_surrogate"
  },
  "comparison": {
    "score_definition": "action_time_s + uncertainty_seconds_per_metre * worst_case_radius_m",
    "lower_is_better": true,
    "baseline_score": 207.2,
    "continuous_fim_score": 234.4,
    "continuous_minus_baseline": 27.2
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

`selected_point`、`selected` 与 `baseline` 始终指向原离散搜索结果，以兼容 Q3 和已有调用方。`score = action_time_s + uncertainty_seconds_per_metre × worst_case_radius_m`；若存在保证接收候选，基线只在该池内选评分最小者，否则回退到全部有限候选。`continuous_fim.selected` 是把连续 FIM 选点送回同一个 `score_candidates` 后得到的复评分，因此 `baseline_score` 与 `continuous_fim_score` 单位相同、均为越低越好；FIM 自己的 `robust_fim_index_per_s` 则越高越好。保证接收域为空时连续结果为 `status="unavailable"`。Python 点为元组，JSON 中为数组。

## 前置条件与不变量

- 第一观测必须为有效 `direction`，频道为 `1..20`。
- 物理源位置域同时使用示向扇区、半径 1800 m 目标域和距首测点不超过 1500 m 的接收约束。
- 保证接收域是 `max distance ≤ min_receive_radius` 的保守内近似；可能接收域是 Minkowski 和的保守外近似。
- 单次测量时间为移动距离/5 + 换频道 0 或 1 s + 检测 5 s。
- `worst_case_radius_m` 只覆盖有限代表点与有限误差样本，不是连续最坏情形证明。
- 连续 FIM 以源域边界采样近似最差信息量，并采用有限多起点模式搜索；它是可复现的数值近似，不是严格全局最优证明。

## 官方模拟器边界

模拟器通过 `POST /measure` 接收位置和频道，并返回检测结果；仅 `measure_result="direction"` 时包含 `svd_deg`。运行层把成功方向观测映射为 `BearingObservation(position, channel, result="direction", bearing_deg=svd_deg)`；本模块内部生成候选域、候选点和评分。HTTP字段、错误处理、幂等重试与串行调用由 `src/sim/` 负责，本模块不直接发送网络请求。
