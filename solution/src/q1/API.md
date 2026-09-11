# Q1 接口契约

当前状态：【待验证】。本文只记录现有代码已经实现的接口；单位均为米、秒和角度制。

## 对外接口

### `analyze_q1(points, bearings, error_deg=1.0)`

- `points`：检测点序列，每项为 `(x, y)`；坐标必须为有限数。
- `bearings`：与检测点等长的示向度序列，单位 °，范围 `[0, 360)`，正东为 0°、逆时针为正。
- `error_deg`：示向误差半宽，单位 °，必须满足 `0 < error_deg < 90`。
- 返回：可 JSON 序列化的字典，含原始输入、显示边界、最终区域和逐次增加观测时的区域变化。

### `localize(observations, bounds, error_deg=1.0)`

- `observations`：观测字典序列；只处理 `status == "direction"` 的记录。
- `bounds=[xmin,ymin,xmax,ymax]`：仅用于生成 `display_polygon`，不裁剪真实定位区域，也不影响直径。
- 返回：区域字典。`status` 为 `bounded`、`unbounded` 或 `empty`。

## `analyze_q1` 输入 JSON

```json
{
  "detector_points": [[-600.0, -300.0], [850.0, -250.0]],
  "bearings_deg": [35.89, 139.44],
  "error_deg": 1.0
}
```

| 字段 | 类型 | 单位/范围 | 含义 |
|---|---|---|---|
| `detector_points` | 二维数值数组 | m，有限数，至少 1 点 | 各次检测位置 |
| `bearings_deg` | 数值数组 | °，`[0,360)`，与点等长 | 实测示向度 |
| `error_deg` | 数值 | °，`(0,90)` | 示向误差半宽 |

最小合法输入：

```json
{"detector_points":[[0,0]],"bearings_deg":[0],"error_deg":1.0}
```

边界示例（跨 0°）：

```json
{"detector_points":[[-1000,0],[1000,0]],"bearings_deg":[359.9,180.1],"error_deg":1.0}
```

`localize` 的单条观测格式为：

```json
{"position":[-600.0,-300.0],"status":"direction","bearing_deg":35.89}
```

`tests/q1/gen_data.py` 在上述输入外包一层 `{"case_id", "mode", "input", "oracle"}`；求解器只读取 `input`，`oracle` 中的真值源和真实误差只供对拍核验，禁止传入算法。

## 输出 JSON

下面是结构示例；为便于阅读，长顶点和半平面数组用空数组示意：

```json
{
  "inputs": {"detector_points": [[0, 0]], "bearings_deg": [0], "error_deg": 1.0},
  "bounds": [-2100, -2100, 2100, 2100],
  "region": {
    "status": "unbounded",
    "vertices": [],
    "diameter": null,
    "diameter_pair": null,
    "diameter_circle": null,
    "minimum_enclosing_circle": null,
    "area": null,
    "bearing_count": 1,
    "display_polygon": [],
    "planes": []
  },
  "progress": []
}
```

有界时，`vertices` 是逆时针凸多边形顶点；`diameter` 为直径，`diameter_pair` 为直径端点；`diameter_circle` 含 `center/radius/covers/excess`；`minimum_enclosing_circle` 含 `center/radius/support`；`area` 单位 m²。Python 返回的点可能是元组，写入 JSON 后为数组。

## 前置条件与不变量

- 每个真实示向方向应落在 `bearing_deg ± error_deg` 的前向扇区内。
- 求解只使用检测点和示向度；测试数据中的真值源不得传入求解器。
- 显示画幅不参与区域、直径或覆盖结论。
- 空集或无界区域没有有限直径；代码以 `null` 表示。

## 官方模拟器边界

模拟器应提供检测位置、测量结果和示向度；本模块内部生成半平面、顶点、直径及圆覆盖结论。请求路径、字段映射、角度舍入和调用时序均为**协议待补充**，`src/runtime/http_client.py` 仅是协议草案适配器。
