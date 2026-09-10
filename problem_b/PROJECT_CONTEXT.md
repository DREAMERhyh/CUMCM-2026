# B-Q1 Project Context

## 1. Mission

- Final goal: 在 `problem_b/` 内完成 B 题问题1的可运行、可复核实现。
- Success criteria: 输入若干检测点坐标和实测示向度，正确构造正向误差扇区交集，分类空集/无界/有界区域，输出有界区域顶点、直径及端点，并判断以该直径线段为直径的圆能否覆盖定位区域；提供图形、自动化 testbench 和 `test_res.md`。
- Highest-priority metrics: 几何正确性、退化状态不误报、主算法与独立 oracle 一致、结果可复现。

## 2. Hard Constraints

- 当前工作根目录是 `problem_b/`；不实现 Q2 的第二测点策略或 Q3/Q4 模拟器状态机。
- Q1 纯定位区域只使用检测点与示向度，不用真实源位置、接收半径或 1800 m 圆域裁剪求解结果。
- 方位角从正东逆时针计，题面误差界默认 ±1°；实测读数在 `[0,360)`。
- 同一地点重复观测不能当作独立噪声平均。
- 任意画幅裁剪只用于显示，不得参与真实直径计算。

## 3. User Requirements

- 实现完整 B-Q1。
- 编写一个或多个 testbench 测试实现。
- 生成 `test_res.md` 说明验证结果，用于验收。
- 使用本文件作为可恢复的项目上下文。

## 4. Current State

**Confirmed:**

- `code/geometry.py` 已整合可配置误差扇区、交点枚举、凸包、空/无界/有界分类、旋转卡壳主算法、全点对 oracle、直径圆覆盖判定和最小包围圆。
- `code/plot_cli.py` 已成为实测示向度 Q1 入口，可输出顶点、直径、覆盖结论、逐次收缩表、JSON 和图形。
- `code/bearing_plot.py` 已显示全局测向几何、定位区域局部放大、直径及直径圆。
- 旧浏览器环境可展示合成场景的定位区域，但不是当前实测 Q1 的统一入口。
- 新增两组 testbench；当前33项测试全部通过，其中旋转卡壳与全点对在2000个固定种子随机凸包上结果一致，单观测无界 CLI 分支也已端到端通过。

**Current assessment:** Q1 实现、文档、稳定示例与验收记录均已形成。

**Main issue:** 无阻塞问题；任务已完成并可交付。

## 5. Architecture / Mental Model

```text
检测点 + 实测/示向度
  -> geometry.bearing_planes
  -> intersect_halfplanes（真实区域分类与顶点）
  -> rotating calipers 主直径算法 + all-pairs oracle
  -> 直径圆覆盖判定（Q1结论）
  -> minimum enclosing circle（补充量，供后续问题复用）
  -> CLI 文本/JSON + Matplotlib 图
```

## 6. Important Files

| File | Purpose | Important notes |
|---|---|---|
| `code/geometry.py` | Q1 纯几何内核 | 不得依赖真值或显示边界 |
| `code/plot_cli.py` | 实测示向度命令行入口 | Q1 统一入口 |
| `code/bearing_plot.py` | Q1 图形输出 | 显示区域、直径和覆盖圆 |
| `code/tests/test_geometry.py` | 原有回归测试 | 保持兼容 |
| `code/tests/test_q1_algorithms.py` | 算法 testbench | 随机 oracle、解析反例、误差裕量 |
| `code/tests/test_q1_cli.py` | 端到端 testbench | CLI、JSON、PNG、SVG 和非法输入 |
| `test_res.md` | 最终验收记录 | 只写实际执行的命令与结果 |

## 7. Decisions

### D001 — 双算法直径结构

**Decision:** 旋转卡壳作为正式主算法，保留全点对枚举作为独立 oracle。

**Reason:** 符合既定调研路线，同时降低优化实现悄然出错的风险。

**Evidence/Result:** 现有全点对实现和研究原型可直接形成交叉验证。

**Implication:** testbench 必须在解析、退化与随机凸包上比较两者。

**Status:** Active

### D002 — Q1 与后续题边界

**Decision:** 默认按题面 ±1°求纯测向交集；最小包围圆作为补充输出，不把其必要性冒充为 Q1 原文要求。

**Reason:** Q1 要求的是区域直径算法和直径圆覆盖判断；最小包围圆对 Q3 清除判停有用，但不是替代答案。

**Evidence/Result:** B题问题1原文及调研第2节。

**Implication:** 报告同时给出“直径圆是否覆盖”和可选最小包围圆，但区分二者语义。

**Status:** Active

## 8. Validation Status

- [x] 原有回归测试：22项通过
- [x] 旋转卡壳与全点对随机交叉验证：2000个随机凸包通过
- [x] 解析图形与直径圆反例
- [x] CLI 文本、JSON、PNG/SVG、有界与无界分支端到端测试
- [x] JavaScript 兼容性回归：`node --check` 通过
- [x] `test_res.md` 完成并与实际输出一致

## 9. Environment

- OS: Windows，PowerShell。
- Python: 3.12；Matplotlib 3.x。
- Reproduction commands: `python -B -m unittest discover -s code/tests -v`。

## 10. Current Working Set

- Files currently being changed: 无待实现文件；准备最终交付。
- Immediate issue: 无。
- Next check: 如继续工作，从论文表述或 Q2 接口复用开始，不重复 Q1 实现。

## 11. Next Actions

- [x] 扩展 `geometry.py` 并保持旧调用兼容。
- [x] 升级 CLI/绘图输出完整 Q1 结果。
- [x] 完成 README、稳定示例和 `test_res.md`。

## 12. Context Handoff Summary

Q1 端到端实现、README、稳定示例及两组 testbench 已完成，最终33项测试通过；采用旋转卡壳主算法加全点对 oracle，纯定位不使用真值或物理圆域。JSON语义、JavaScript语法、图形目视检查和 diff 检查均通过，可直接交付。

## 13. Decision / Progress Log

`2026-09-10 23:23 — 用户要求完整实现 B-Q1、增加 testbench 和 test_res.md，并将当前工作根目录设为 problem_b/。`

`2026-09-10 23:45 — 完成几何主算法、Q1 CLI、局部放大可视化和两组 testbench；32项测试通过。首次回归发现直径端点顺序不兼容，已改为稳定字典序并复测通过。`

`2026-09-11 00:21 — 补充单观测无界 CLI 端到端测试；README、VERIFICATION、test_res.md 和稳定 PNG/SVG/JSON 示例完成，33项测试通过。`

`2026-09-11 00:23 — 最终复跑33项测试通过；JSON语义检查、Node语法检查、图形目视检查、diff检查和临时文件检查均通过，任务完成。`
