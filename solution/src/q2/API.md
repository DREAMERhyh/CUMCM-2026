# Q2 接口契约

当前状态：【待验证】。现有实现优化有限离散候选，不声称求得连续空间全局最优点。

## 对外接口

### `Q2Config`

`Q2Config(error_deg=1.005, arena_radius=1800.0, min_receive_radius=1000.0, max_receive_radius=1500.0, circle_sides=24, candidate_region_sides=72, scenario_limit=8, uncertainty_seconds_per_metre=0.5)`

各半径单位 m，`error_deg` 单位 °；`circle_sides` 和 `candidate_region_sides` 是圆的多边形近似边数；`scenario_limit` 是有限评分场景上限；最后一项把剩余半径折算为评分秒数。

### `build_candidate_regions(source_region, *, min_receive_radius=1000.0, max_receive_radius=1500.0, circle_sides=72)`

输入 Q1/共享模块产生的有界源位置区域，返回连续的保证接收域内近似和可能接收域外近似。

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
  "method": "set_worst_case_radius_per_action_time",
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

`score = action_time_s + uncertainty_seconds_per_metre × worst_case_radius_m`。若存在保证接收候选，只在该池内选评分最小者；否则在全部有限候选中回退选择。平分时依次比较更大的 `fim_proxy_per_s` 和坐标。Python 点为元组，JSON 中为数组。

## 前置条件与不变量

- 第一观测必须为有效 `direction`，频道为 `1..20`。
- 物理源位置域同时使用示向扇区、半径 1800 m 目标域和距首测点不超过 1500 m 的接收约束。
- 保证接收域是 `max distance ≤ min_receive_radius` 的保守内近似；可能接收域是 Minkowski 和的保守外近似。
- 单次测量时间为移动距离/5 + 换频道 0 或 1 s + 检测 5 s。
- `worst_case_radius_m` 只覆盖有限代表点与有限误差样本，不是连续最坏情形证明。

## 官方模拟器边界

模拟器提供首测位置、频道、结果和示向度；本模块内部生成候选域、候选点和评分。HTTP 请求字段、返回字段、错误码、舍入和调用时序均为**协议待补充**；当前 HTTP 适配器不能视为正式接口契约。
