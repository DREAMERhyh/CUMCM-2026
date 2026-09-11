# Q1：由示向度确定定位区域

当前状态：【待验证】。

## 题目在问什么

机器人在若干位置测得干扰源方向，但每次示向度存在 ±1° 误差。Q1 要把所有可能的源位置求成一个区域，计算区域直径，并判断以直径为直径的圆能否覆盖整个区域。

## 算法步骤

1. 把每次“方向 ± 误差”变成两个前向半平面。
2. 求全部半平面的公共交集，并区分空集、无界和有界。
3. 对有界交点求逆时针凸包。
4. 用旋转卡壳求直径，再逐顶点检查直径圆是否覆盖区域。
5. 绘图时另行裁剪到画幅；画幅绝不参与真实几何计算。

| 算法步骤 / 数学关系 | 对应函数 | 说明 |
|---|---|---|
| `bearing ± error` → 两个半平面 | `geometry.py:bearing_planes` | 保留前向扇区 |
| 半平面交集 | `geometry.py:intersect_halfplanes` | 判空、判无界、恢复顶点 |
| 凸包 | `geometry.py:hull` | 删除重复和共线内点 |
| 多边形直径 | `geometry.py:diameter_calipers` | 生产算法，O(n) |
| 独立直径参考 | `geometry.py:diameter_bruteforce` | 测试用 O(n²) oracle |
| 最小包围圆 | `geometry.py:minimum_enclosing_circle` | 后续问题复用的补充量 |
| 一次完成 Q1 | `cli.py:analyze_q1` | 推荐的对外入口 |

## 输入输出示例

```python
from q1 import analyze_q1

answer = analyze_q1(
    [(-600, -300), (850, -250), (-200, 1000)],
    [35.89, 139.44, 300.56],
    error_deg=1.0,
)
print(answer["region"]["status"], answer["region"]["diameter"])
```

字段定义、边界输入和完整输出见 [API.md](API.md)。命令行演示：

```powershell
python src/q1/cli.py --demo --no-show --output output/q1.png --result-json output/q1.json
```

## 测试与局限

```powershell
python tests/q1/test_unit.py
python tests/q1/gen_data.py --mode random --seed 42
python tests/q1/test_duipai.py --dir tests/q1/data/random
```

人工验收必须按 `tests/q1/verify_manual.md` 执行。当前采用双精度和显式容差；近平行边界可能放大数值误差。最小包围圆是小规模枚举实现，适合本题少量顶点。官方模拟器协议仍待补充。
