# B题 Q1至Q4 算法工程

本目录已完成Q1和Q2的本地算法、可视化与testbench，并完成Q3/Q4可接入官方协议的离线策略、状态机和理论验证。Q3/Q4尚未接入官方模拟器，不能把离线结果视为正式成绩。第一次使用请先阅读 [`快速上手指南.md`](快速上手指南.md)。

Q1输入若干检测点坐标及同一干扰源在这些点的实测示向度，程序构造正向 ±1° 误差扇区的纯交集，输出定位区域状态、凸多边形顶点、区域直径及端点，并判断以该直径线段为直径的圆能否覆盖定位区域。

求解器只使用检测点与示向度；可选源坐标只画作人工核验标记，不参与计算。目标分布圆、真实接收半径和显示画幅也不裁剪 Q1 的真实定位区域。

## 快速运行

需要 Python 3.10+ 和 Matplotlib：

```powershell
python -m pip install -r requirements.txt
python code/q1/cli.py
```

交互模式依次输入检测点数、每个点的 `x y 示向度`，以及可选参考源坐标。示向度范围为 `[0,360)`；正东为 0°，正北为 90°。

也可直接使用命令行：

```powershell
python code/q1/cli.py --demo

python code/q1/cli.py `
  --point -600 -300 35.89 `
  --point 850 -250 139.44 `
  --point -200 1000 300.56 `
  --source 220 280

python code/q1/cli.py --demo --no-show `
  --output output/q1_demo.png `
  --result-json output/q1_demo.json
```

`--output` 支持 PNG 或 SVG。`--no-show` 用于无桌面环境，必须同时指定输出图。`--result-json` 保存输入、区域顶点、半平面、直径、覆盖圆、最小包围圆补充量及逐次加入观测的收缩记录。

题面默认误差界为 ±1°。若需要评估接口两位小数舍入的保守裕量，可另跑：

```powershell
python code/q1/cli.py --demo --error-deg 1.005 --no-show --output output/q1_demo_margin.svg
```

1.005°只是工程敏感性参数，不是题面新增的误差分布。

## 输出图

全局图包含检测点、示向射线、误差边界和半径1800 m的题目背景圆；右上角局部放大图显示实际定位多边形、区域直径和直径圆。背景圆和画幅只用于显示。

当区域为空或无界时，程序会明确报告状态，不用任意大方框伪造有限直径。当区域退化为点或线段时，分别返回直径0或线段端点距离。

## 数学与算法

对检测点 `s`、示向度 `theta` 和误差半宽 `epsilon`，程序把前向扇区写成两个半平面：

```text
cross(u(theta-epsilon), q-s) >= 0
cross(u(theta+epsilon), q-s) <= 0
```

多次观测得到所有半平面的交集。实现流程为：

1. 枚举边界线交点并用全部约束筛选，独立判断空集与无界性；
2. 对可行交点求严格逆时针凸包；
3. 用旋转卡壳在 `O(n)` 时间求凸多边形直径；
4. 保留 `O(n²)` 全点对算法作为 testbench oracle；
5. 以直径端点中点为圆心、直径一半为半径，检查所有顶点；
6. 额外用二点/三点支撑圆穷举最小包围圆，供后续问题复用。

半平面枚举基线约为 `O(m³)`，`m` 是半平面数；适合本题少量观测并便于审查。最小包围圆补充实现为小规模 `O(n⁴)` oracle，不冒称 Welzl 期望线性算法。

## Q1 的圆覆盖结论

**以定位区域直径为直径的圆不一定覆盖定位区域。**

程序对每个具体区域直接检查。一般反例是边长20的等边三角形：区域直径为20，而最小包围圆半径为 `20/sqrt(3) ≈ 11.547`，大于直径圆半径10。两次真实形式的测向扇区同样可以形成不能被直径圆覆盖的四边形，相关数值反例已进入 testbench。

## Python 接口

```python
from q1 import analyze_q1

result = analyze_q1(
    points=[(-600, -300), (850, -250), (-200, 1000)],
    bearings=[35.89, 139.44, 300.56],
    error_deg=1.0,
)

region = result["region"]
print(region["status"])
print(region["vertices"])
print(region["diameter"], region["diameter_pair"])
print(region["diameter_circle"]["covers"])
```

更底层的独立函数位于 `code/q1/geometry.py`：

- `bearing_planes`：示向度转正向半平面；
- `intersect_halfplanes`：区域分类与顶点恢复；
- `diameter_calipers`：旋转卡壳主算法；
- `diameter_bruteforce`：全点对 oracle；
- `minimum_enclosing_circle`：小规模支撑圆穷举；
- `localize`：从观测表完成 Q1 求解。

## 文件结构

```text
problem_b/
  PROJECT_CONTEXT.md              当前可恢复任务状态
  README.md                       使用说明与算法边界
  快速上手指南.md                本科生使用说明
  VERIFICATION.md                 验证状态摘要
  test_res_q1.md                  Q1验收结果
  test_res_q2.md                  Q2验收结果
  test_res_q3_offline.md          Q3离线验收结果
  test_res_q4_offline.md          Q4离线验收结果
  code/
    q1/                           Q1 几何、CLI、绘图与对拍工具
    common/                       Q2至Q4共享模型、物理区域和计时
    q2/                           第二测点规划、CLI与图形
    q3/                           全向搜索与清除策略
    q4/                           定向源增量策略
    runtime/                      HTTP适配、本地规则模型和执行器
    legacy/                       旧合成环境和浏览器实验，仅用于回归核验
    tests/
      test_geometry.py            原有几何与合成环境回归
      test_q1_algorithms.py       Q1 算法 testbench
      test_q1_cli.py              CLI/JSON/PNG/SVG 端到端 testbench
      test_q2.py                  Q2 连续域、选点、CLI和图形 testbench
```

## 验收

在 `problem_b/` 目录执行：

```powershell
python -B -m unittest discover -s code/tests -v
node --check code/legacy/visualization/app.js
python code/q1/cli.py --demo --no-show --output output/q1_demo.png --result-json output/q1_demo.json
```

实际结果和边界分别见 [`test_res_q1.md`](test_res_q1.md)、[`test_res_q2.md`](test_res_q2.md)、[`test_res_q3_offline.md`](test_res_q3_offline.md) 和 [`test_res_q4_offline.md`](test_res_q4_offline.md)。

## 数值边界

当前使用普通双精度和明确容差。testbench 已覆盖跨0°、近平行趋势、退化区域和随机凸包，但这不是任意病态浮点输入的形式化精确算术证书。若边界行列式接近阈值、结果异常巨大或有界区域无法恢复顶点，应保留原始输入并做高精度复核。
