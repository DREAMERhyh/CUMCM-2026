# PROJECT_CONTEXT

## Mission

维护 B 题 Q1/Q2 建模与测试体系、Q3/Q4 离线策略原型，以及按官方附件实现的模拟器通信层。当前工作根目录为 `solution/`。

## Hard constraints

- 禁止 AI 执行任何 Git 操作。
- Q1–Q4 当前状态一律为【待验证】；只有人工按清单验收后才能改状态。AI 不得标记【已验证】或【模拟器未测试】。
- Q1/Q2 API 必须归纳自真实函数签名；接口语义或官方协议不确定时必须暂停询问。
- 不修改题目 PDF、附件或其他原始材料。
- 用户已授权新增 Q3 自适应策略、同点多频道联合批测、第一部分多源路线与离线配对测试；Q4 只做兼容回归，不改变其既有四向探测逻辑。缓存和有限束搜索仍须另行授权。

## Confirmed decisions

- `src/runtime/` 保留与传输无关的策略执行器；`src/sim/` 是官方协议、HTTP客户端、离线替身和现场入口的唯一正式位置。旧 `runtime/http_client.py`、`runtime/fake_simulator.py` 只作兼容导出。
- 现场 CLI 默认只执行 `/enter → /measure(0,0,频道1) → /exit` smoke；必须显式传入 `--confirm-ready` 才能联网，完整 Q3/Q4 原型还必须传入 `--confirm-policy`。
- 旧浏览器/合成环境归入 `src/legacy/`，环境回归归入 `tests/legacy/`。
- Q2 对拍只核验连续域包含关系、时间记账、有限候选评分与选择，不声称连续空间全局最优。
- Q2 保留原离散搜索在 `baseline.selected_point/selected`，连续结果放在 `continuous_fim`；两种选点都用原集合评分器复算。顶层 `selected_point/selected` 是按 `(R_wc,T)` 从两者作出的最终推荐。Q3 默认滚动模式会把顶层、离散、连续多预算、Pareto 与保证接收域候选合并重评；只有关闭滚动模式的回归分支才由 `prefer_continuous_fim` 决定使用连续点或顶层结果。Q4 的四向探测不可用时走该关闭滚动的回归分支。
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
- **Implemented on `q2-optimize-wjc`:** 共享源区域构造器保留原 16/24 边整圆粗外包，再用可行线—圆/圆—圆交点加入圆弧端点切线，并按多边形顶点相对真实圆盘的径向超差迭代补切线；所有新增半平面均包含原圆盘，故新区间嵌套于旧外包且不漏真实源。Q2 测后评分的新增接收圆也通过 `extend_region_with_observation` 使用相同细化，Q3/Q4 接口不变。
- Q2 演示图同图显示离散基线红星、连续 FIM 蓝菱形、最终推荐黑圈、5%/10%近优域及局部放大、两方案综合分数、`T-R` Pareto 前沿。示例产物为 `output/q2_pareto_regions.png`、`output/q2_pareto_regions.json`。
- Q3 已加入“自适应 FIM + 27 m 后验清除网格 + 保证接收联合批测 + 清除失败条件复测 + 有限场景总虚拟时间滚动优化”，并完成第一部分“多源服务块 + 最便宜插入 + 2-opt”。路线层只排序下一主服务源，不改 Q2、单源 measure/clear 结论、联合批测、后验或清除点集合；每个真实响应后重算，超时/异常回退原一步策略。`multi_source_route_mode` 正式默认仍为 `off`，显式设置 `insertion_2opt` 才启用，路线软截止默认 0.25 s。其余默认参数仍为每源顺便测量上限 3、`joint_batch_mode=guaranteed`、`failed_clear_remeasure_mode=gated`、`rolling_time_mode=scenario`、风险口径 `cvar`、滚动软截止 1 s、FIM 上限 10 s。Q4 显式关闭路线及所有 Q3 新分支。
- Q1/Q2 已有分题 README、单元测试、三模式数据生成器、对拍器、人工验收清单和人工结果模板。
- Q3/Q4 README 明确为待验证原型；已有离线测试位于 `tests/q3/test_offline.py` 与 `tests/q4/test_offline.py`。
- `src/sim/` 已实现严格请求/响应校验、回环HTTP客户端、幂等与并发保护、现实时间安全退出、逐动作JSONL、离线规则替身和三动作smoke；Q3/Q4 在线策略结束时还会输出“平均用时 = 总虚拟时间 / 清除成功的信号源数”，零个成功源时显示无法计算。人工步骤见 `tests/sim/verify_manual.md`。
- 2026-09-12 路线修改后，Q3 定向测试 32/32 通过（原 22 项加 10 项路线/兼容回归）；显式设置 `NO_PROXY=127.0.0.1,localhost` 后，最终文件状态下全项目 `unittest` 107/107 通过，耗时 53.549 s。此前两次失败分别来自沙箱禁止创建本机 socket、代理劫持 localhost，并非断言失败。全部检查只使用单元测试、本机回环假服务器和 `FakeSimulator`；当前环境没有官方模拟器，Q1-Q4 状态仍为【待验证】。
- 路线配对使用种子 20263912 的 4 个相同场景，FIM/滚动/路线软截止为 10/1/0.25 s，27 m 网格、CVaR、每源顺便测量上限 3、失败清除复测开启。current 与 insertion_2opt 均 4/4 完整清除；新路线 3/4 胜，平均总虚拟时间 5966.309→5377.612 s，P90/最坏值 6717.235→5876.333 s，平均 resolve 移动 17285.294→14399.309 m，跨源移动 14914.362→12767.182 m，长跳 4.50→3.25；平均真实墙钟 137.362→149.947 s。第 2 场反增 391.246 s；118 次路线调用 `ok/partial/fallback=72/7/39`。结果见 `output/q3_offline/route_benchmark.{json,md}`，小样本不足以自动打开正式默认。
- 固定种子 20260911 的 200 个合法首测案例全部可比较：以有限场景最坏后验半径为主指标，分时限连续 FIM 优于离散基线 200/200（100%），均值由 119.037 m 降至 70.082 m；以 `T+0.5R` 为指标仅 76/200（38%）更优。连续点平均多 29.706 s 虚拟动作时间。16 进程墙钟 122.015 s。结果文件为 `tests/q2/analysis/q2_200_case_comparison.{md,json}`。
- 当前机器单案例粗测：仅离散且不生成近优域 3.741 s；分时限 FIM 且不生成近优域 4.115 s；默认在线近优域 6.919 s；离线较密近优域 17.227 s。它们是 CPU/墙钟时间，不是机器狗虚拟时间。
- 固定种子 20260912 的局部圆弧外接离线比较使用 200 个合成首测案例、20 个离散规划案例，构造计时交错执行并重复 7 次取中位数。24 边时嵌套/真值/径向目标失败均 0/200，平均面积为旧法 98.8843%，MEC 半径 200/200 下降且平均降 3.0455 m，平均最大圆外扩 5.9533→0.1993 m；同序纯细化使区域构造增加 9.35%、离散规划增加 15.03% 墙钟。16 边时对应面积 97.6401%，MEC 平均降 6.8922 m，外扩 13.1618→0.2039 m，构造和规划墙钟分别增加 21.61% 与 22.38%。早期一次显示加速的结果已废弃，原因是新旧半平面排序不同造成短路检查混杂。结果见 `output/q2_arc_refinement_benchmark.{json,md}`；未启用连续 FIM/近优域，未使用官方模拟器。
- 论文问题二正文已与问题一圆弧讨论衔接：$K_1$ 用 24 边外切圆多边形得到保守外近似 $\widehat K_1$，保证接收域使用 72 边内近似，可能接收域使用 72 个支撑方向外近似；最小包围圆已展开为一、二、三支撑点候选及逐顶点覆盖检查，FIM 首次使用处引用 Fisher 1922。绘图脚本 `../paper/code/q2_region_figures.py` 生成 `q2-k1-outer-approx` 和 `q2-reception-regions` 两组 PDF/PNG，并断言示例中 174 个高密度 $K_1$ 边界点均在 $\widehat K_1$ 内。2026-09-12 重跑 Q2 单元测试 9/9 通过；当前环境无 XeLaTeX，整篇排版仍待 Windows 双次编译和人工检查。

## Important interfaces and nesting

- Q1：`analyze_q1` → `localize` → 半平面交、凸包、旋转卡壳。
- Q2：`plan_second_point` → `build_region_from_observations`（复用 Q1 几何）→ `plan_measurement` → 离散候选评分 + 多预算 `optimize_continuous_fim` → 集合复评分/Pareto → `_near_optimal_outputs`。顶层 `selected_point` 是最终混合推荐。
- Q3/Q4：策略由 `runtime.runner.run_policy(policy, client)` 驱动；Q4 继承 Q3。Q3 的 Q2 规划只负责生成候选，`q3.rolling_time.evaluate_total_time_decision` 保留单源 measure/clear 结论；`q3.route` 将这些结论物化为有入口、保守出口和本地成本的服务块，完整重算开放路线，用最便宜插入和确定性 2-opt 排序。固定扫描、强制 near 清除、未完成联合批次及失败点同点复测优先于路线层。Q4 默认细化上限和 FIM 上限仍为 2 和 6 s，并显式设置联合批测、失败复测、滚动评价和多源路线均为 `off`。
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
python -B tests/q2/benchmark_arc_refinement.py --count 200 --plan-count 20 --repeats 7 --seed 20260912
python -B tests/q3/benchmark_adaptive.py --cases 8 --workers 4 --output output/q3_offline/strategy_benchmark.json
python -B tests/q3/benchmark_joint.py --cases 8 --workers 4 --output output/q3_offline/joint_benchmark.json
python -B tests/q3/benchmark_failed_clear_remeasure.py --cases 8 --workers 4 --fim-cpu-time-limit-s 10 --output output/q3_offline/failed_clear_remeasure_benchmark.json
python -B tests/q3/benchmark_rolling_time.py --train-cases 2 --validation-cases 4 --train-seed 20260912 --validation-seed 20262912 --workers 4 --fim-cpu-time-limit-s 10 --rolling-cpu-time-limit-s 1 --output output/q3_offline/rolling_time_benchmark.json
python -B tests/q3/benchmark_route.py --cases 4 --seed 20263912 --workers 4 --fim-cpu-time-limit-s 10 --rolling-cpu-time-limit-s 1 --route-cpu-time-limit-s 0.25 --output output/q3_offline/route_benchmark.json
```

人工改变 Q1/Q2 状态前，必须执行对应 `tests/qN/verify_manual.md` 的完整清单并填写 `test_res.md`。

## Open decisions / next steps

- **Confirmed geometry:** `ring7` 的原点加半径1500 m正六边形六顶点，以1000 m接收圆完整覆盖半径1800 m目标圆。最坏位置为外圆边界与相邻环点角平分线，最近距离 `sqrt(1800^2+1500^2-2*1800*1500*cos30°)=901.921737 m`，有98.078263 m距离余量。
- **Implemented Part 1:** Q3 扫描阶段仍用 `ring7()` 形成完整发现证书，发现频道后进入自适应单源处理。半径小于等于 19.9 m 直接清除；否则比较当前后验区域网格的实际最坏清除成本与“一次 FIM 检测 + 按预测半径比例缩放后的清除成本”，预计至少节省 10 s 才检测。最多 5 次，连续两次实际收缩不足 5% 时停止。保底采用覆盖当前后验多边形的 27 m 方格点，理论覆盖半径约 19.092 m，相对 20 m 清除半径保留约 0.908 m 余量；失败点被记录并继续有限点列。
- **Rejected Part 2:** “每完成一个扫描站后最多处理两个局部动作”只留在 `tests/q3/benchmark_adaptive.py` 的 `InterleavedQ3Policy`。8 组离线配对虽都完整清除，但只赢 1 组，平均多 1359.270 s；原因是局部动作打断扫描路线后产生额外往返。因此正式 `src/q3/policy.py` 不含交错阶段或开关。
- **Implemented Part 2 v2:** Q3 以虚拟时间为目标实现同点多频道联合批测。扫描阶段只在既定 `ring7` 站点顺便复测：只要该点对已发现源的整个当前后验区域保证接收就追加一次，不再要求边际节省；扫描结束后，对所有可细化源生成 Q2/FIM 目标点，先选择从当前位置动作时间最短且预计值得复测的目标。到点后目标频道必测，其他频道仍需同时满足保证接收、预计清除成本节省超过追加检测成本且未超过每源三次顺便测量。扫描和后续联合规划共用每源三次上限，顺便测量不占五次专用 FIM 配额。固定 8 场景中的旧联合基准早于本次固定站规则与参数调整，需重跑后才能评价新规则；`all_active` 保留为激进离线对照。
- **Implemented two-task plan:** 任务一“每次保底清除失败后条件复测”和任务二“用 Q2 候选推演测量后验并按总虚拟时间滚动决策”均已作为独立开关编码、测试和基准。任务二首版把跨源续程视为零，在种子 20261912 的 4 场景中仅赢 2 场且均值/P90变差；逐场证据显示动作减少但移动变长。修正为加入“清除路线终点到最近其他源中心”的续程后，使用新验证种子 20262912 达到 4/4 胜出，故 Q3 默认同时启用两个任务。不得把此结果称为严格全局最优。
- **Implemented grid thinning and route Part 1:** Q3 默认清除方格为 27 m，最远格点距离 `27/sqrt(2)=19.0919... m`，相对 20 m 清除半径保留约 0.908 m 几何余量。第一部分小规模路径规划已替代“只按最近中心一步续程”作为可选源排序层，并完成当前 27 m 参数下的独立配对；正式默认仍关闭。缓存与有限束搜索未实施，详见 `src/TODO.md`。
- **Q4 audit:** `four_sided_points` 在满足条件时构造圆心东/北/西/南四个点，四点整体才有未知发射方向下至少一点可见的保证；但 `Q4Policy` 默认 `max_refinements=2`，实际最多只试前两个点，因此当前代码没有完整兑现四点证明。四点不可用时回退 Q2，而 Q2 的保证接收只含距离、不含未知方向可见性。Q4 正式在线测试前应优先补齐这一缺口。
- **Current assessment for adaptive arc refinement:** 几何收益在 200/200 随机案例中稳定，但同序消融显示有 9%--22% 的本地墙钟代价，且有限场景离散推荐半径并非逐例单调（24 边 17/20 改善、3/20 变差；16 边 16/20 改善、4/20 变差）。在决定写入正式论文或成为最终默认前，应进一步运行完整连续 FIM 与 Q3/Q4 同场景性能配对；现有单元/离线流程回归只证明兼容性，不是官方成绩。
- **Confirmed rolling policy:** 默认 `rolling_time_mode="scenario"` 时，Q3 把 Q2 的离散基线、连续 FIM 多预算解、Pareto、顶层推荐及保证接收域候选放入同一池，按有限场景预计总虚拟时间选择测点或直接清除，并不固定执行单纯 FIM 或顶层推荐。`prefer_continuous_fim=True` 只在关闭滚动模式时生效；若必须在顶层混合推荐与单纯 FIM 之间选，保留含离散安全后备的顶层推荐。
- **Implemented multi-source route Part 1 and paused:** `src/q3/route.py` 已实现服务规格/块、开放路线估值、最便宜插入和确定性 2-opt；`policy.py` 接入显式开关和安全回退，`benchmark_route.py` 输出配对 JSON/Markdown。已观察到平均跨源移动和总虚拟时间下降，但有 1/4 反例和 39 次路线回退。正式默认是否开启由用户决定；只有用户随后明确要求，才实施缓存和有限束搜索。完整说明见 `src/q3/路径规划修改.md`。
- 队员可按 `tests/q2/verify_manual.md` 人工验收两种确切点、分时限预算、Pareto 前沿、5%/10%近优域和局部放大图；正式报告不得把 200 例的 100% 写成全局最优概率。
- 若后续需要标量化，可对归一化 lambda 做训练集网格扫描、Pareto拐点和独立种子验证；当前正式实现优先采用硬时间预算，未引入 lambda。
- 队员决定 Q3/Q4 的独立对拍判据、参考实现与人工验收流程后，再建立完整测试体系。
- 队员按 `tests/sim/verify_manual.md` 启动 Q3、Q4 演练，先分别完成三动作 smoke 并核对模拟器界面与本地 JSONL；此前不要运行正式测试。
- Q3 smoke 通过后，在线完整策略显式使用 `--max-refinements 5 --fim-cpu-time-limit-s 10 --joint-batch-mode guaranteed --failed-clear-remeasure-mode gated --rolling-time-mode scenario --rolling-risk-metric cvar --rolling-cpu-time-limit-s 1`；10 s 与 1 s 都是真实墙钟限制，不是虚拟动作时间，其中 1 s 为滚动评价软截止。
- 正式提交前由人工审核历史记录、AI 使用日志、状态总表和生成测试数据。

## Handoff

从 `快速上手指南.md` 查看结构和状态，从分题 README 找算法到代码的映射，从 API.md 获取测试数据契约。`q2-optimize-wjc` 已实现局部圆弧混合细化并完成首轮几何/离散规划消融，下一步若继续应先比较完整连续 FIM 和 Q3/Q4 同场景总时间，再决定是否同步修改论文。Q3 多源路线第一部分已完成并暂停；先查看 `src/q3/路径规划修改.md` 与 `output/q3_offline/route_benchmark.{json,md}`，未经用户后续明确授权不得开始第二部分缓存和有限束搜索。当前环境没有官方模拟器；不要把自动测试、合成数据或离线配对理解为人工验收或官方模拟器成绩。
