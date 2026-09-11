# PROJECT_CONTEXT

## Mission

维护 B 题 Q1/Q2 建模与测试体系、Q3/Q4 离线策略原型，以及按官方附件实现的模拟器通信层。当前工作根目录为 `solution/`。

## Hard constraints

- 禁止 AI 执行任何 Git 操作。
- Q1–Q4 当前状态一律为【待验证】；只有人工按清单验收后才能改状态。AI 不得标记【已验证】或【模拟器未测试】。
- Q1/Q2 API 必须归纳自真实函数签名；接口语义或官方协议不确定时必须暂停询问。
- 不修改题目 PDF、附件或其他原始材料。
- 用户已授权新增 Q3 自适应策略、同点多频道联合批测与离线配对测试；Q4 只做兼容回归，不改变其既有四向探测逻辑。

## Confirmed decisions

- `src/runtime/` 保留与传输无关的策略执行器；`src/sim/` 是官方协议、HTTP客户端、离线替身和现场入口的唯一正式位置。旧 `runtime/http_client.py`、`runtime/fake_simulator.py` 只作兼容导出。
- 现场 CLI 默认只执行 `/enter → /measure(0,0,频道1) → /exit` smoke；必须显式传入 `--confirm-ready` 才能联网，完整 Q3/Q4 原型还必须传入 `--confirm-policy`。
- 旧浏览器/合成环境归入 `src/legacy/`，环境回归归入 `tests/legacy/`。
- Q2 对拍只核验连续域包含关系、时间记账、有限候选评分与选择，不声称连续空间全局最优。
- Q2 保留原离散搜索在 `baseline.selected_point/selected`，连续结果放在 `continuous_fim`；两种选点都用原集合评分器复算。顶层 `selected_point/selected` 是按 `(R_wc,T)` 从两者作出的最终推荐，Q3/Q4 使用顶层结果。
- 连续 FIM 只对第二测点坐标做连续多起点投影模式搜索，源位置鲁棒性仍用多边形边界场景近似，结论只能写成 FIM 替代目标的数值近似。
- Q2 题面只明确要求“较好的定位效果”，未规定时间-距离权重。当前建议以有限场景最坏后验包围半径 `worst_case_radius_m` 为主评价、动作时间为次级评价；FIM 只生成候选，最终必须由集合后验指标裁决。`score=T+0.5R` 保留为 Q3 导向的工程敏感性指标，0.5 s/m 不是题目常数。
- 题面原文要求“候选区域”而非一维区间。除物理保证/可能接收域外，建议用近优子水平集 `C_eta={s in F_g: R_wc(s)<=(1+eta)R_wc*}` 表达效果候选区域，并以多边形或多多边形输出。
- Q2 已按确认方案实现“多个时间预算下优化 FIM → 集合 `R_wc,T` 复评分 → Pareto 筛选 → 执行点选择”。默认相对离散基线的虚拟时间预算为 15/30/60 s，连续执行点最多多 30 s；CPU 墙钟另设 8 s 安全截止。
- 两个方案都保留确切点，并各自输出“5%近优域”“10%近优域”及同图可视化；名称不是置信区间。近优域分 `online/offline/off` 三档，当前多边形是达标局部采样点的凸包，仅采样点有评分验证，凸包内部不是连续证书。
- 历史 `test_res_q*.md` 和 `VERIFICATION.md` 保留，但不代表当前人工状态；新模板在 `tests/q1|q2/test_res.md`。

## Current state (2026-09-12)

- 源码已按 `src/q1`、`q2`、`q3`、`q4`、`common`、`runtime`、`sim`、`legacy` 整理，所有内部导入已修复。
- Q1 对外接口：`q1.analyze_q1`、`q1.localize`；契约见 `src/q1/API.md`。
- Q2 对外接口：`Q2Config`、`build_candidate_regions`、`optimize_continuous_fim`、`plan_measurement`、`plan_second_point`；契约见 `src/q2/API.md`。
- Q2 的 `src/q2/continuous_fim.py` 支持多个绝对动作时间上限共享场景/缓存；`src/q2/near_optimal.py` 负责局部近优域采样和凸包输出。默认规划返回 `baseline`、`continuous_fim`、`comparison`、`pareto_front`、`recommendation_source` 及两套近优域。
- Q2 演示图同图显示离散基线红星、连续 FIM 蓝菱形、最终推荐黑圈、5%/10%近优域及局部放大、两方案综合分数、`T-R` Pareto 前沿。示例产物为 `output/q2_pareto_regions.png`、`output/q2_pareto_regions.json`。
- Q3 正式策略已加入“自适应 FIM + 27 m 后验清除网格 + 保证接收联合批测 + 清除失败条件复测 + 有限场景总虚拟时间滚动优化”。滚动评价不改 Q2 输出，而是对其离散、连续多预算、Pareto、顶层及保证接收域候选真正生成测后后验、清除网格和路线，并加入当前源路线终点到最近其他活动源中心的续程。默认 `joint_batch_mode=guaranteed`、`failed_clear_remeasure_mode=gated`、`rolling_time_mode=scenario`、风险口径 `cvar`、单次滚动评价截止 0.2 s；FIM 单次上限仍为 10 s。Q4 明确关闭联合批测、Q3 自适应分支、失败条件复测和滚动评价，继续原四向探测和旧保底，以免继承全向源假设。
- Q1/Q2 已有分题 README、单元测试、三模式数据生成器、对拍器、人工验收清单和人工结果模板。
- Q3/Q4 README 明确为待验证原型；已有离线测试位于 `tests/q3/test_offline.py` 与 `tests/q4/test_offline.py`。
- `src/sim/` 已实现严格请求/响应校验、回环HTTP客户端、幂等与并发保护、现实时间安全退出、逐动作JSONL、离线规则替身和三动作smoke；Q3/Q4 在线策略结束时还会输出“平均用时 = 总虚拟时间 / 清除成功的信号源数”，零个成功源时显示无法计算。人工步骤见 `tests/sim/verify_manual.md`。
- 2026-09-12 最近一次自动检查：27 m 网格下全项目 `unittest` 93/93 通过，耗时 63.022 s，其中 Q3 21/21 通过。任务二历史性能基准使用 20 m 网格：种子 20260912 的 2 个训练场景从 P90/CVaR/最坏值中选择 CVaR，再在新种子 20262912 的 4 个验证场景对照四种开关；全部 4/4 完整清除，组合策略平均 5873.934 s。该历史结果见 `output/q3_offline/rolling_time_benchmark.json`，尚不能代表27 m版本性能。以上未连接官方模拟器，Q1-Q4 状态仍为【待验证】。
- 固定种子 20260911 的 200 个合法首测案例全部可比较：以有限场景最坏后验半径为主指标，分时限连续 FIM 优于离散基线 200/200（100%），均值由 119.037 m 降至 70.082 m；以 `T+0.5R` 为指标仅 76/200（38%）更优。连续点平均多 29.706 s 虚拟动作时间。16 进程墙钟 122.015 s。结果文件为 `tests/q2/analysis/q2_200_case_comparison.{md,json}`。
- 当前机器单案例粗测：仅离散且不生成近优域 3.741 s；分时限 FIM 且不生成近优域 4.115 s；默认在线近优域 6.919 s；离线较密近优域 17.227 s。它们是 CPU/墙钟时间，不是机器狗虚拟时间。

## Important interfaces and nesting

- Q1：`analyze_q1` → `localize` → 半平面交、凸包、旋转卡壳。
- Q2：`plan_second_point` → `build_region_from_observations`（复用 Q1 几何）→ `plan_measurement` → 离散候选评分 + 多预算 `optimize_continuous_fim` → 集合复评分/Pareto → `_near_optimal_outputs`。顶层 `selected_point` 是最终混合推荐。
- Q3/Q4：策略由 `runtime.runner.run_policy(policy, client)` 驱动；Q4 继承 Q3。Q3 的 Q2 规划只负责生成候选，`q3.rolling_time.evaluate_total_time_decision` 对保证接收候选作有限位置/误差分支推演，按“测量动作 + CVaR测后清除及续程”与立即清除比较；超时返回截止前最佳完整候选 `partial` 或安全清除 `fallback`。联合规划继续按当前位置动作时间最短选择目标，并在同点顺便测量满足边际节省的频道。失败复测判断位于 `q3.fallback_remeasure.evaluate_failed_clear_remeasure`，只在 `fallback_clear` 失败后触发一次。Q4 默认细化上限和 FIM 上限仍为 2 和 6 s，并显式设置联合批测、失败复测和滚动评价均为 `off`。
- 官方模拟器：`sim.cli` → `sim.live_runner.run_live_policy` → Q3/Q4或smoke策略 → `sim.client.HttpRobotClient.execute` → `sim.protocol` 严格校验。网络失败只用原ID和原正文重试；结果不确定时禁止把该ID绑定到其他动作。策略运行收尾从 JSONL 统计成功清除数并打印总虚拟时间和平均用时。

## Verification commands

在 `solution/` 下：

```powershell
python -B -m unittest discover -s tests -t . -v
python -B -m unittest discover -s tests/sim -t . -v
python tests/q1/test_unit.py
python tests/q2/test_unit.py
python tests/q1/gen_data.py --mode random --seed 42
python tests/q1/test_duipai.py --dir tests/q1/data/random
python tests/q2/gen_data.py --mode random --seed 42
python tests/q2/test_duipai.py --dir tests/q2/data/random
python -B tests/q2/benchmark_200.py --count 200 --seed 20260911 --workers 16
python -B tests/q3/benchmark_adaptive.py --cases 8 --workers 4 --output output/q3_offline/strategy_benchmark.json
python -B tests/q3/benchmark_joint.py --cases 8 --workers 4 --output output/q3_offline/joint_benchmark.json
python -B tests/q3/benchmark_failed_clear_remeasure.py --cases 8 --workers 4 --fim-cpu-time-limit-s 10 --output output/q3_offline/failed_clear_remeasure_benchmark.json
python -B tests/q3/benchmark_rolling_time.py --train-cases 2 --validation-cases 4 --train-seed 20260912 --validation-seed 20262912 --workers 4 --fim-cpu-time-limit-s 10 --rolling-cpu-time-limit-s 0.2 --output output/q3_offline/rolling_time_benchmark.json
```

人工改变 Q1/Q2 状态前，必须执行对应 `tests/qN/verify_manual.md` 的完整清单并填写 `test_res.md`。

## Open decisions / next steps

- **Confirmed geometry:** `ring7` 的原点加半径1500 m正六边形六顶点，以1000 m接收圆完整覆盖半径1800 m目标圆。最坏位置为外圆边界与相邻环点角平分线，最近距离 `sqrt(1800^2+1500^2-2*1800*1500*cos30°)=901.921737 m`，有98.078263 m距离余量。
- **Implemented Part 1:** Q3 扫描阶段仍用 `ring7()` 形成完整发现证书，发现频道后进入自适应单源处理。半径小于等于 19.9 m 直接清除；否则比较当前后验区域网格的实际最坏清除成本与“一次 FIM 检测 + 按预测半径比例缩放后的清除成本”，预计至少节省 10 s 才检测。最多 5 次，连续两次实际收缩不足 5% 时停止。保底采用覆盖当前后验多边形的 27 m 方格点，理论覆盖半径约 19.092 m，相对 20 m 清除半径保留约 0.908 m 余量；失败点被记录并继续有限点列。
- **Rejected Part 2:** “每完成一个扫描站后最多处理两个局部动作”只留在 `tests/q3/benchmark_adaptive.py` 的 `InterleavedQ3Policy`。8 组离线配对虽都完整清除，但只赢 1 组，平均多 1359.270 s；原因是局部动作打断扫描路线后产生额外往返。因此正式 `src/q3/policy.py` 不含交错阶段或开关。
- **Implemented Part 2 v2:** Q3 以虚拟时间为目标实现同点多频道联合批测。扫描阶段只在既定 `ring7` 站点顺便复测；扫描结束后，对所有可细化源生成 Q2/FIM 目标点，先选择从当前位置动作时间最短且预计值得复测的目标。到点后目标频道必测，其他频道仅在该点对整个后验区域保证接收、预计清除成本节省超过追加检测成本且未超过每源两次顺便测量时加入。顺便测量不占五次专用 FIM 配额。固定 8 场景中默认 `guaranteed` 8/8 完整、6/8 胜出，平均虚拟时间下降 672.897 s（8.908%），P90 也下降；因此已接入正式 Q3。`all_active` 保留为激进离线对照。
- **Implemented two-task plan:** 任务一“每次保底清除失败后条件复测”和任务二“用 Q2 候选推演测量后验并按总虚拟时间滚动决策”均已作为独立开关编码、测试和基准。任务二首版把跨源续程视为零，在种子 20261912 的 4 场景中仅赢 2 场且均值/P90变差；逐场证据显示动作减少但移动变长。修正为加入“清除路线终点到最近其他源中心”的续程后，使用新验证种子 20262912 达到 4/4 胜出，故 Q3 默认同时启用两个任务。不得把此结果称为严格全局最优。
- **Implemented grid thinning, performance to verify:** Q3 默认清除方格已从 20 m 改为 27 m；最远格点距离为 `27/sqrt(2)=19.0919... m`，相对 20 m 清除半径保留约 0.908 m 几何余量。Q3 21/21 与全项目 93/93 自动回归通过。此前平均 5873.934 s 的滚动基准使用 20 m 网格，不能作为 27 m 版本的性能成绩；下一步需独立重跑配对基准。其余优化线索为：(1) 以小规模路径规划替代最近其他源中心的单步续程；(2) 为滚动后验/网格增加含状态哈希的缓存后扩充场景。详细未实施项见 `src/TODO.md`。
- **Q4 audit:** `four_sided_points` 在满足条件时构造圆心东/北/西/南四个点，四点整体才有未知发射方向下至少一点可见的保证；但 `Q4Policy` 默认 `max_refinements=2`，实际最多只试前两个点，因此当前代码没有完整兑现四点证明。四点不可用时回退 Q2，而 Q2 的保证接收只含距离、不含未知方向可见性。Q4 正式在线测试前应优先补齐这一缺口。
- **Open decision:** Q3 技术上可固定执行 `continuous_fim.selected_point`，但必须区分“经时间预算和集合复评分后的连续点”与未经安全复评分的 `fim_surrogate_best_point`。后者不建议使用；前者仍会失去顶层离散基线的半径安全后备。用户尚未确认是否切换，当前代码继续使用顶层混合推荐。
- 队员可按 `tests/q2/verify_manual.md` 人工验收两种确切点、分时限预算、Pareto 前沿、5%/10%近优域和局部放大图；正式报告不得把 200 例的 100% 写成全局最优概率。
- 若后续需要标量化，可对归一化 lambda 做训练集网格扫描、Pareto拐点和独立种子验证；当前正式实现优先采用硬时间预算，未引入 lambda。
- 队员决定 Q3/Q4 的独立对拍判据、参考实现与人工验收流程后，再建立完整测试体系。
- 队员按 `tests/sim/verify_manual.md` 启动 Q3、Q4 演练，先分别完成三动作 smoke 并核对模拟器界面与本地 JSONL；此前不要运行正式测试。
- Q3 smoke 通过后，在线完整策略显式使用 `--max-refinements 5 --fim-cpu-time-limit-s 10 --joint-batch-mode guaranteed --failed-clear-remeasure-mode gated --rolling-time-mode scenario --rolling-risk-metric cvar --rolling-cpu-time-limit-s 0.2`；10 s 与 0.2 s 都是真实墙钟截止，不是虚拟动作时间。
- 正式提交前由人工审核历史记录、AI 使用日志、状态总表和生成测试数据。

## Handoff

从 `快速上手指南.md` 查看结构和状态，从分题 README 找算法到代码的映射，从 API.md 获取测试数据契约。Q3 两个独立优化任务均已完成，任务二结果见 `test_res_q3_rolling_time.md`；下一步是人工按 `src/sim/README.md` 和 `tests/sim/verify_manual.md` 做官方演练，或在新指令下处理 `src/TODO.md` 的未实施项。不要把自动测试“通过”理解为人工验收或官方模拟器成绩。
