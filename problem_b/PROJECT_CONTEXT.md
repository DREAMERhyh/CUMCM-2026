# B题 Q1至Q4 Project Context

## 1. Mission

- Final goal: 在保留已完成 Q1 的基础上，完成 Q2 第二测点规划，以及 Q3/Q4 可接入官方模拟器的策略核心。
- Success criteria: Q2 具备算法、图形、CLI、完整 testbench 和验收记录；Q3/Q4 具备共享状态机、覆盖/保底策略、离线 testbench 和诚实的验证边界；提供本科生快速上手指导书。
- Highest-priority metrics: 几何正确性、无真值泄漏、协议状态一致、有限终止保证、结果可复现。

## 2. Hard Constraints

- 当前工作根目录是 `problem_b/`；本轮禁止使用 Git。
- 采用同一工程、按 Q2/Q3/Q4 分目录、共享核心模型与运行接口，不复制三套几何和协议逻辑。
- Q2 完整 testbench 通过后才能继续 Q3/Q4。
- 当前没有接入官方模拟器；Q3/Q4 只做离线实现、回放/伪客户端测试和少量理论验证，不宣称官方清除率或真实运行性能。
- Q1 纯定位区域只使用检测点与示向度，不用真实源位置、接收半径或 1800 m 圆域裁剪求解结果。
- 方位角从正东逆时针计，题面误差界默认 ±1°；实测读数在 `[0,360)`。
- 同一地点重复观测不能当作独立噪声平均。
- 任意画幅裁剪只用于显示，不得参与真实直径计算。

## 3. User Requirements

- Q1 已完成，验收记录已重命名为 `test_res_q1.md`。
- 先完成 Q2 算法、可视化、testbench 和 `test_res_q2.md`。
- Q2 通过后完成 Q3/Q4 离线代码、测试及各自验收记录。
- 完成后编写通俗易懂的 Markdown 指导书，供本科生快速上手。
- 使用本文件作为可恢复的项目上下文。

## 4. Current State

**Confirmed:**

- `code/q1/geometry.py` 已整合可配置误差扇区、交点枚举、凸包、空/无界/有界分类、旋转卡壳主算法、全点对 oracle、直径圆覆盖判定和最小包围圆。
- `code/q1/cli.py` 已成为实测示向度 Q1 入口，可输出顶点、直径、覆盖结论、逐次收缩表、JSON 和图形。
- `code/q1/bearing_plot.py` 已显示全局测向几何、定位区域局部放大、直径及直径圆。
- 旧浏览器环境可展示合成场景的定位区域，但不是当前实测 Q1 的统一入口。
- 新增两组 testbench；当前33项测试全部通过，其中旋转卡壳与全点对在2000个固定种子随机凸包上结果一致，单观测无界 CLI 分支也已端到端通过。
- `code/common/` 已提供共享数据模型、物理圆域保守外包和官方虚拟时间模型。
- `code/q2/` 已完成连续保证/可能接收候选域、46个离散候选、有限场景最坏半径评分、FIM基准、CLI、JSON和可视化；固定示例中12个候选保证处于1000米接收范围。
- `code/q3/` 已完成7点覆盖、228点有限清除保底和全向源离线状态机。
- `code/q4/` 已在Q3状态机上完成121点定向覆盖和四方向局部复核。
- `code/runtime/` 已完成同步策略执行器、本地规则模拟器及不自动启动测试的HTTP适配器。
- 最终Q1至Q4共52项测试全部通过；新版Q2图形已目视检查。
- `快速上手指南.md` 已完成。

**Current assessment:** Q1已迁入 `code/q1/` 且本地实现完整；Q2已补齐连续接收候选域、离散选点、图形和本地testbench；Q3/Q4完成离线原型与理论覆盖检查，尚未达到正式模拟器运行与提交状态。

**Main issues:**

- Q2所谓最坏后验半径只覆盖有限代表源点和三个误差端点，必须保持“有限场景”表述，并用批量合成案例补充策略效果比较。
- Q3/Q4运行器未使用 `/enter` 的 `remaining_real_duration_s` 建立现实截止时间，也未预留 `/exit` 时间。
- Q3/Q4动作日志仅保存在内存，CLI结束时才整体写JSON；需要逐动作落盘、刷新和异常保留，并记录程序运行时间。
- 当前没有正式/演练专用入口、案例编码与表1统计汇总，也没有官方模拟器协议、吞吐、10至16源案例和异常恢复测试。
- Q3/Q4仍需各3次正式测试、原文件名导出的6份加密日志及论文表1数据；这些不能由离线测试替代。

## 5. Architecture / Mental Model

```text
Q1 geometry（纯示向区域）
  -> common（物理先验、数据模型、计时）
  -> Q2（第二测点候选、集合评分、FIM基准）
  -> Q3（全向覆盖、定位、清除状态机）
  -> Q4（定向可见性与全局保底）
  -> runtime（FakeSimulator / HttpRobotClient / 串行runner）
```

**Interface notes:** Q1的推荐Python入口是 `q1.analyze_q1`，底层为 `q1.geometry.localize`，CLI为 `code/q1/cli.py`；Q2由 `q2.__init__` 导出 `plan_second_point` 和供Q3复用的 `plan_measurement`；Q3/Q4分别导出 `Q3Policy`/`Q4Policy`，统一通过 `runtime.runner.run_policy(policy, client)` 驱动。Q4继承Q3，只替换全局覆盖点和局部复核点。默认Q3会在细化阶段调用Q2，Q2再调用Q1几何内核；但Q3/Q4的离线CLI均显式设置 `max_refinements=0`，演示运行不会覆盖这条嵌套调用链。当前 `code/` 需加入 `PYTHONPATH`，且 `runtime.__init__` 未导出公共符号。

**Legacy / optional paths:** `code/legacy/` 是旧合成浏览器实验链，不在当前Q1至Q4正式调用链上；Q1参考真值标记、Q2 FIM基准、全点对直径oracle、FakeSimulator及若干覆盖检查函数不是正式运行必需，但分别承担解释或testbench作用，清理提交包时应与生产入口分层而非直接删除。

## 6. Important Files

| File | Purpose | Important notes |
|---|---|---|
| `code/q1/geometry.py` | Q1 纯几何内核 | 不得依赖真值或显示边界 |
| `code/q1/cli.py` | 实测示向度命令行入口 | Q1 统一入口 |
| `code/q1/bearing_plot.py` | Q1 图形输出 | 显示区域、直径和覆盖圆 |
| `code/tests/test_geometry.py` | 原有回归测试 | 保持兼容 |
| `code/tests/test_q1_algorithms.py` | 算法 testbench | 随机 oracle、解析反例、误差裕量 |
| `code/tests/test_q1_cli.py` | 端到端 testbench | CLI、JSON、PNG、SVG 和非法输入 |
| `code/q1/testbench/gen_cases.py` | Q1 测试数据生成 | 确定性种子、落盘 JSON |
| `code/q1/testbench/duipai.py` | Q1 对拍核验 | 与全点对等独立 oracle 交叉验证 |
| `code/common/` | Q2至Q4共享内核 | 物理先验采用保守外包 |
| `code/q2/` | 第二测点算法与图形 | 完整本地testbench |
| `code/q3/` | 全向搜索清除策略 | 当前仅offline验收 |
| `code/q4/` | 定向源增量策略 | 当前仅offline验收 |
| `code/runtime/` | 协议、执行器和本地规则模型 | HTTP客户端不自动启动测试 |
| `test_res_q1.md` | Q1验收记录 | 原 `test_res.md` 已重命名 |
| `test_res_q2.md` | Q2验收记录 | 含CLI和图形检查 |
| `test_res_q3_offline.md` | Q3离线验收 | 不代表官方成绩 |
| `test_res_q4_offline.md` | Q4离线验收 | 不代表官方成绩 |
| `快速上手指南.md` | 本科生入门说明 | 含运行、接口和模拟器边界 |

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

### D003 — 共享工程与分题目录

**Decision:** 保留Q1几何接口，在同一工程内新增 `common/`、`q2/`、`q3/`、`q4/` 和 `runtime/`；不复制三套工程。

**Reason:** Q3复用Q2测点规划，Q4复用Q3状态机；物理先验、计时和协议必须保持一处定义。

**Evidence/Result:** 52项全量回归通过，Q1原有33项无回归。

**Implication:** 官方模拟器接入只替换客户端，不改策略接口；Q3/Q4在接入前均标记offline。

**Status:** Active

## 8. Validation Status

- [x] 原有回归测试：22项通过
- [x] 旋转卡壳与全点对随机交叉验证：2000个随机凸包通过
- [x] 解析图形与直径圆反例
- [x] CLI 文本、JSON、PNG/SVG、有界与无界分支端到端测试
- [x] JavaScript 兼容性回归：`node --check` 通过
- [x] `test_res_q1.md` 完成并与实际输出一致
- [x] Q2连续域、算法、CLI、JSON、PNG及9项专用测试
- [x] Q3覆盖、计时、幂等、负载和状态机6项offline测试
- [x] Q4定向覆盖、局部证书和状态机4项offline测试
- [x] Q1至Q4全量52项测试通过；2026-09-11本轮复跑耗时35.674秒
- [ ] 官方模拟器Q3/Q4演练与正式测试
- [x] Q2连续候选区域表达
- [ ] Q2批量策略效果对照验证
- [ ] 现实截止控制、逐动作日志、程序运行时间和表1汇总

## 9. Environment

- OS: Windows，PowerShell。
- Python: 3.12；Matplotlib 3.x。
- Reproduction commands: `python -B -m unittest discover -s code/tests -v`。

## 10. Current Working Set

- Files currently being changed: Q1目录迁移、Q2连续域、验收记录和指导书已完成。
- Immediate issue: Q2若写入论文仍应补批量策略效果对照；工程下一主线是Q3/Q4正式运行层（现实截止、流式日志、统计与安全退出）。
- Next check: 使用官方模拟器演练模式核对协议、真实RPC吞吐和日志大小，再优化Q3/Q4调度。

## 11. Next Actions

- [x] 扩展 `geometry.py` 并保持旧调用兼容。
- [x] 升级 CLI/绘图输出完整 Q1 结果。
- [x] 完成 README、稳定示例和 `test_res_q1.md`。
- [x] 完成Q2算法、可视化、testbench和 `test_res_q2.md`。
- [x] 完成Q3/Q4离线实现及各自offline验收记录。
- [x] 完成本科生 `快速上手指南.md`。
- [x] 补Q2第二检测点连续接收候选域和清晰图例。
- [ ] 补Q2批量合成对照实验。
- [ ] 补Q3/Q4正式运行入口、`remaining_real_duration_s`截止控制、逐动作日志和表1统计。
- [ ] 扩充10/13/16源、接收半径边界、定向边界及协议异常testbench。
- [ ] 接入官方模拟器并追加Q3/Q4真实演练证据；演练稳定后各完成3次正式测试并保留原名日志。

## 12. Context Handoff Summary

Q1已集中到 `code/q1/`，外部调用改为 `q1.*`。Q2已输出连续保证接收域（安全内近似）和可能接收域（保守外近似），并用46个离散候选做有限场景评分；固定示例12个保证候选，最终点约 `(4.172,-96.457)`。Q3/Q4共用有限状态机并通过offline测试，但正式运行层仍缺现实截止、流式日志、程序运行时间/案例编码统计、安全退出和官方演练。当前工作树52项测试通过（2026-09-11复跑35.674秒）；不得把离线时间当正式成绩。

## 13. Decision / Progress Log

`2026-09-10 23:23 — 用户要求完整实现 B-Q1、增加 testbench 和 test_res.md，并将当前工作根目录设为 problem_b/。`

`2026-09-10 23:45 — 完成几何主算法、Q1 CLI、局部放大可视化和两组 testbench；32项测试通过。首次回归发现直径端点顺序不兼容，已改为稳定字典序并复测通过。`

`2026-09-11 00:21 — 补充单观测无界 CLI 端到端测试；README、VERIFICATION、test_res.md 和稳定 PNG/SVG/JSON 示例完成，33项测试通过。`

`2026-09-11 00:23 — 最终复跑33项测试通过；JSON语义检查、Node语法检查、图形目视检查、diff检查和临时文件检查均通过，任务完成。`

`2026-09-11 02:45 — 用户确认共享工程、分题目录方案，要求依次完成Q2、Q3/Q4 offline测试和本科生指导书，并禁止本轮使用Git。`

`2026-09-11 — 完成Q2算法与图形、Q3/Q4离线状态机、共享runtime及四份分题验收记录；最终51项测试通过。`

`2026-09-11 10:55 — 对照B题题面、模拟器附件与2026论文格式规范复审：51项测试复跑通过（52.252秒），但确认Q2连续候选域、Q3/Q4现实截止与逐动作日志、正式入口/统计及官方演练仍是提交前缺口。`

`2026-09-11 11:26 — Q1统一迁入code/q1并修正Q2/Q3/Q4和测试引用；Q2补连续保证/可能接收域、稳定候选编号与时间分解，52项全量测试通过并完成图形目视检查。`
