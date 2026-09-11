# Q2 零基础教学（05）：连续 FIM 优化——用信息量找最佳几何位置

离散基线是在撒好的 46 个点里挑。这一篇讲更聪明的连续方案：
在"保证接收域"这块**连续地盘**里，用 **FIM（Fisher 信息量）** 直接算出
几何上交会角最好的那个点，而不是局限于网格点。对应代码 `q2/continuous_fim.py`。

---

## 1. FIM 想度量的是什么？

两次"测方向角"的定位，效果取决于一个几何直觉：

> 用两个测点看同一个小目标，**两个测点在目标处的视线夹角**越接近 90°，
> 两条直线一交，位置就越"咬得死"；夹角太小（几乎平行），交会就飘。

另外：**离目标越近**，角度的微小误差对应的目标位置误差也越小。

于是"两次示向观测能给出的定位信息"大致等于（可推导）：

```
信息 ∝  sin²(视线夹角 Δθ) / (d₁² · d₂²)
```

- `d₁, d₂`：两个测点到目标的距离；
- `sin²(Δθ)`：大力奖励夹角接近 90°，惩罚近乎平行的交会；
- 除以距离平方：惩罚太远。

（这里的"信息"是**费雪信息矩阵行列式**，凸于位置参数，直觉如上，推导见附注。）

---

## 2. 代码是怎么算这一个数的

`q2/continuous_fim.py:bearing_fim_index(first_position, second_position, target, action_time_s)`：

```python
d₁²  = target 到 first_position 的平方距离
d₂²  = target 到 second_position 的平方距离
cross = 两个向量 (target−p1, target−p2) 的叉积
sine² = cross² / (d₁² · d₂²)                      # 这就是 sin²(夹角)
if  d₁² ≤ 25 或 T≤0 : return None                  # 无效
return 10¹² · sine² / (d₁² · d₂² · T)
```

- 除以 `T`（动作时间）是为了得到**"每秒能榨出多少信息"**，公平比较不同耗时。
- `10¹²` 只是放大读数好看，不影响选点（同一个常数）。
- `d₁²≤25`（距首测不足 5 m）视为无效场景，返回 `None`。

---

## 3. 做不出全局最坏，就取"边界场景的最小值"（鲁棒化）

FIM 依赖"目标在哪个点"。真源在 P₁ 里不确定。最稳妥的口径是**最坏情况**：
目标摆在 P₁ 边界上最难看的位置，也要保证信息够多。

```python
scenarios = build_boundary_scenarios(P₁.vertices, samples_per_edge=4)
#  每条边 4 等分采样点 + 多边形质心，去重后作为目标候选集合
robust_value = min( bearing_fim_index(p1, s, g, T)  for g in scenarios )
```

即：**取所有目标场景里信息量最小的那个作为本候选的"鲁棒 FIM"**。
这保证"无论真源在哪，信息都不会低于这个值"。demo 中场景数约 `边数×4+1`。
（这是有限边界场景近似，不是严格连续 minimax 证明——代码明说 `optimality_claim="numerical_near_global_for_fim_surrogate"`。）

---

## 4. 约束与投影：保证点不出"保证接收域"

S₂ 必须落在上篇讲过的**保证接收域** F_g 内（连续多边形，35 顶点）。搜索时可能会跑出去，
所以先做**投影** `project_to_polygon`（`continuous_fim.py:64-73`）：

- 若点已在凸多边形内 ⇒ 原样返回；
- 否则，找多边形每条边上"离该点最近的点"（垂足或端点），再取所有边里最近的，把点**拽回边界上**。

```python
def project_to_polygon(point, vertices):
    if inside_convex(vertices, point): return point
    boundary = [ closest_on_segment(point, a, b)  for each edge (a,b) ]
    return min(boundary, key=dist(point, candidate))
```

同时每次评估都复核 `farthest = max dist(s, P₁所有顶点) ≤ min_receive_radius + 1e-6`，
不满足就弃掉该点（双保险）。

---

## 5. 搜索算法：多起点投影模式搜索

优化的目标函数是"鲁棒 FIM / 秒"，在 F_g 里求最大。这是一个无需梯度的**模式搜索**
（pattern search），`optimize_continuous_fim`：

**① 种子准备**（把"看起来可能不错"的点都拿来当下山起点）：
- 保证域质心、源区域中心；
- 离散基线给的保证候选点；
- 保证域所有顶点、所有边中点。

**② 对每个种子，做"爬山 + 试探式收缩"**：
```
step = 200 m（初始）
while step ≥ 2 m 且未超迭代上限(120):
    在 16 个均匀方向上各试探 step：
        候选 = current + step·方向，投影回 F_g，评估其鲁棒FIM
        若满足当前时间预算 → 收集
    取试探集里 performance 最好的点作 candidate
    若 candidate.FIM > current.FIM + 1e-15 :
        current = candidate          # 有改进就前进
    else:
        step /= 2                    # 没改进就缩小步长，细挖
```
这就是"改进则走、否则缩小步长"的经典模式搜索，最终停留在局部最好处。

**③ 评估缓存**：以 `round(点,8)` 为键缓存评估结果，避免重复算时间/距离。

---

## 6. 本版新增：三档时间预算，防"跑太远"

FIM 可能选到几何好但**太远**的点。上一代问题就在这里：远点信息高，但要多跑几十秒。

新版（`planner.py` 传入 `action_time_limits_s`）让 `optimize_continuous_fim`
**一次性跑三档绝对动作时间上限**，共享场景和评估缓存：

```python
action_time_limits = [ T_baseline + 15,  T_baseline + 30,  T_baseline + 60 ]
```

- 每一档是一个 budget：只允许 `T(s) ≤ 该上限` 的点进来参加选优；
- 每档各自选出一个最优候选，写入 `budget_solutions`；
- 邻居试探也被当前预算过滤（太慢的点即使信息更高也不算）。

demo 的三档结果（基线 T=132.5 s）：
| 预算上限 | 实取 | 点 | 鲁棒FIM |
|---|---|---|---|
| +15 s (148) | 147.5 s | (111.2, −260.4) | 4.65e−4 |
| +30 s (163) | 162.5 s | (−358.0, 449.3) | 6.04e−4 |
| +60 s (193) | 192.5 s | (322.9, −136.5) | 1.01e−3 |

可以清楚看到：**预算越宽，能追的信息越高**——这就是"时间换精度"的权衡曲面。

同时有 CPU 墙钟保护 `cpu_time_limit_s`（8 秒真实时间），超时则带着现有最优返回并标记 `timed_out`。

---

## 7. 附注：为什么信息 ∝ sin²Δθ/(d₁²d₂²)（可选）

测一个目标，观测是"方向角 θ"，方差 σ²。方向角 θ 对位置 (x,y) 的偏导数量级是 1/d。
一次性测量的费雪信息 ≈ (∂θ/∂pos)² ≈ 1/d²。两次独立观测的**信息矩阵的行列式**，
近似等于两条"距离尺度后的法向量"围成平行四边形的面积平方，即 `∝ sin²Δθ/(d₁²d₂²)`。
这是贝叶斯下界（CRB）的来源——"能榨出的定位精度下限"反比于它。直觉：夹角 90°、目标近 → 信息最大。

---

## 8. 代码位置速查

| 目的 | 文件:函数 |
|---|---|
| 单点 FIM 值 | `q2/continuous_fim.py:bearing_fim_index` |
| 边界场景抽样 | `q2/continuous_fim.py:build_boundary_scenarios` |
| 投影回多边形 | `q2/continuous_fim.py:project_to_polygon` |
| 完整多起点模式搜索 + 时间预算 | `q2/continuous_fim.py:optimize_continuous_fim` |

下一篇 [06_混合裁决与推荐.md](06_混合裁决与推荐.md)：把离散基线的点 + 三档 FIM 点摆在一起，
用"同一把尺子"比，再做 Pareto 与安全推荐。
