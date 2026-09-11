# Q2：选择第二个检测点

当前状态：【待验证】。

## 题目在问什么

已在第一个位置收到某频道信号和示向度后，要选择第二个检测位置。程序既给出连续的“保证能收到”和“可能收到”区域，也从有限候选点中选择兼顾移动时间和定位收缩效果的点。

## 算法步骤

1. 用目标圆、首测接收圆和示向扇区建立源位置区域。
2. 计算第二测点的保证接收连续域（内近似）与可能接收连续域（外近似）。
3. 从首测方向、区域中心和保证域中心等位置生成有限候选。
4. 对有限源位置及误差样本模拟第二次观测，计算最坏后验半径。
5. 在保证接收候选中最小化“动作时间 + 不确定半径折算”；若该集合为空则回退到全部候选。

| 算法步骤 / 数学关系 | 对应函数 | 说明 |
|---|---|---|
| 首测后的物理源域 | `common/domain.py:build_region_from_observations` | 合并圆域与示向约束 |
| 保证/可能接收连续域 | `candidates.py:build_candidate_regions` | 分别是内近似、外近似 |
| 生成离散搜索点 | `candidates.py:generate_candidates` | 确定性有限候选 |
| 有限场景评分 | `planner.py:score_candidates` | 不代表连续全局最坏情形 |
| 通用测点规划 | `planner.py:plan_measurement` | 接受已有区域与观测 |
| Q2 常用入口 | `planner.py:plan_second_point` | 从第一观测开始 |
| 移动/换频/检测计时 | `common/time_model.py:measure_cost` | `距离/5 + 0或1 + 5` 秒 |

## 输入输出示例

```python
from common.models import BearingObservation
from q2 import plan_second_point

first = BearingObservation((-600.0, -300.0), 1, "direction", 35.89)
plan = plan_second_point(first)
print(plan["selected_point"])
```

字段、配置和返回结构见 [API.md](API.md)。绘图演示：

```powershell
python src/q2/cli.py --demo --no-show --output output/q2.png --result-json output/q2.json
```

## 测试与局限

```powershell
python tests/q2/test_unit.py
python tests/q2/gen_data.py --mode random --seed 42
python tests/q2/test_duipai.py --dir tests/q2/data/random
```

人工验收必须按 `tests/q2/verify_manual.md` 执行。连续域只表达接收可行性；最终选点只在程序生成的有限候选、有限源位置和有限误差样本中比较，不能写成连续空间全局最优证明。圆域使用可审计的正多边形近似，官方模拟器协议仍待补充。
