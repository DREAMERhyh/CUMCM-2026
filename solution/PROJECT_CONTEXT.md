# PROJECT_CONTEXT

## Mission

维护 B 题 Q1/Q2 建模与测试体系、Q3/Q4 离线策略原型，以及按官方附件实现的模拟器通信层。当前工作根目录为 `solution/`。

## Hard constraints

- 禁止 AI 执行任何 Git 操作。
- Q1–Q4 当前状态一律为【待验证】；只有人工按清单验收后才能改状态。AI 不得标记【已验证】或【模拟器未测试】。
- Q1/Q2 API 必须归纳自真实函数签名；接口语义或官方协议不确定时必须暂停询问。
- 不修改题目 PDF、附件或其他原始材料。
- 用户已授权新增 Q3 自适应策略、同点多频道联合批测，以及多源路线第一、二部分与离线配对测试；Q3 第二部分源码虽存在但正式默认未启用。Q4 已完成正确性基线、25 点扫描、有限联合后验、清除失败原地门控补测、方向探测组滚动、长清除尾救援，并可选接入 Q3 第一部分 insertion+2opt；Q2 离散候选点、连续 FIM、Pareto 规划及 Q3 beam/cache 均未接入 Q4。

## Confirmed decisions

- `src/runtime/` 保留与传输无关的策略执行器；`src/sim/` 是官方协议、HTTP客户端、离线替身和现场入口的唯一正式位置。旧 `runtime/http_client.py`、`runtime/fake_simulator.py` 只作兼容导出。
- 现场 CLI 默认只执行 `/enter → /measure(0,0,频道1) → /exit` smoke；必须显式传入 `--confirm-ready` 才能联网，完整 Q3/Q4 原型还必须传入 `--confirm-policy`。
- 旧浏览器/合成环境归入 `src/legacy/`，环境回归归入 `tests/legacy/`。
- Q2 对拍只核验连续域包含关系、时间记账、有限候选评分与选择，不声称连续空间全局最优。
- Q2 同时保留两种源位置圆域：`q2_version="new"` 默认采用“固定边数粗外包 + 端点切线 + 径向超差切线”的自适应保守细化，`legacy` 完整保留固定外切正多边形。统一启动参数为 `--q2-version new|legacy`，默认 `new`；Q2 画图、Q3/Q4 实际观测更新和 Q3 滚动测后分支沿用同一版本，版本参与缓存键，运行中禁止混用。
- Q2 保留原离散搜索在 `baseline.selected_point/selected`，连续结果放在 `continuous_fim`；两种选点都用原集合评分器复算。顶层 `selected_point/selected` 是按 `(R_wc,T)` 从两者作出的最终推荐。Q3 默认滚动模式会把顶层、离散、连续多预算、Pareto 与保证接收域候选合并重评；只有关闭滚动模式的回归分支才由 `prefer_continuous_fim` 决定使用连续点或顶层结果。Q4 不再把四侧探测不可用时的全向 Q2 单点作为安全回退，而是进入 27 m 后验清除网格。
- 连续 FIM 只对第二测点坐标做连续多起点投影模式搜索，源位置鲁棒性仍用多边形边界场景近似，结论只能写成 FIM 替代目标的数值近似。
- Q2 题面只明确要求“较好的定位效果”，未规定时间-距离权重。当前建议以有限场景最坏后验包围半径 `worst_case_radius_m` 为主评价、动作时间为次级评价；FIM 只生成候选，最终必须由集合后验指标裁决。`score=T+0.5R` 保留为 Q3 导向的工程敏感性指标，0.5 s/m 不是题目常数。
- 题面原文要求“候选区域”而非一维区间。除物理保证/可能接收域外，建议用近优子水平集 `C_eta={s in F_g: R_wc(s)<=(1+eta)R_wc*}` 表达效果候选区域，并以多边形或多多边形输出。
- Q2 已按确认方案实现“多个时间预算下优化 FIM → 集合 `R_wc,T` 复评分 → Pareto 筛选 → 执行点选择”。默认相对离散基线的虚拟时间预算为 15/30/60 s，连续执行点最多多 30 s；CPU 墙钟另设 8 s 安全截止。
- 两个方案都保留确切点，并各自输出“5%近优域”“10%近优域”及同图可视化；名称不是置信区间。近优域分 `online/offline/off` 三档，当前多边形是达标局部采样点的凸包，仅采样点有评分验证，凸包内部不是连续证书。
- 历史 `test_res_q*.md` 和 `VERIFICATION.md` 保留，但不代表当前人工状态；新模板在 `tests/q1|q2/test_res.md`。

## Current state (2026-09-13)

- 源码已按 `src/q1`、`q2`、`q3`、`q4`、`common`、`runtime`、`sim`、`legacy` 整理，所有内部导入已修复。
- Q1 对外接口：`q1.analyze_q1`、`q1.localize`；契约见 `src/q1/API.md`。
- Q2 对外接口：`Q2Config`、`build_candidate_regions`、`optimize_continuous_fim`、`plan_measurement`、`plan_second_point`；契约见 `src/q2/API.md`。
- Q2 的 `src/q2/continuous_fim.py` 支持多个绝对动作时间上限共享场景/缓存；`src/q2/near_optimal.py` 负责局部近优域采样和凸包输出。默认规划返回 `baseline`、`continuous_fim`、`comparison`、`pareto_front`、`recommendation_source` 及两套近优域。
- Q2 已从 `q2-new-branch/CUMCM-2026/solution` 融合自适应圆弧细化，并把融合前的固定外切实现保留为 `legacy`。`Q2Config.q2_version`、三个 CLI 的 `--q2-version` 以及现场 `sim.cli` 参数默认均为 `new`；`region.approximation.q2_version/kind` 记录实际分支。公开规划函数和返回主结构不变，仅给配置及共享区域函数增加带默认值的版本参数。
- Q2 演示图同图显示离散基线红星、连续 FIM 蓝菱形、最终推荐黑圈、5%/10%近优域及局部放大、两方案综合分数、`T-R` Pareto 前沿。示例产物为 `output/q2_pareto_regions.png`、`output/q2_pareto_regions.json`。
- Q3 已完成多源路线两部分。第一部分为服务块、最便宜插入和确定性 2-opt；第二部分为策略实例内的有界状态键缓存和有限束搜索。路线层只排序下一主服务源，不改 Q2、单源 measure/clear 结论、联合批测、后验或清除点集合。`multi_source_route_mode` 支持 `off/insertion_2opt/beam_cached`，正式默认仍为 `off`。Q4 只允许 `off/insertion_2opt`，默认 `off`，不接入 beam/cache。
- Q4 默认发现网为边长 985 m、晶格分数相位 `(0.112,0.112)` 的 25 点平移三角网；任一目标圆内源位于某个保留三角形内，三顶点距离均不超过 985 m，且任意发射半平面至少包含一顶点。机器人从原点出发的固定开放路线经 2-opt 后约 24552.150 m，覆盖余量 15 m。`triangular37` 与 `grid121` 保留为回归模式；25 点只完成几何证明和本地稠密检查，尚未完成官方模拟器验收或完整策略配对。
- Q4 的 `max_refinements` 按启动的认证定向探测组计数；动态四侧偏移满足 `sqrt(2)r<rho<=1000-r`，可覆盖约 `r<414.2 m`。更大后验在方向滚动模式下使用 900 m 局部三角网，关闭滚动时仍直接使用 27 m 后验清除网格；任何分支都不调用全向 Q2 单点回退。`no_signal` 后可继续剩余认证点，也可转入独立具备连续覆盖证明的清除网格。
- `src/q4/belief.py` 维护有限 `(位置, 全向/定向类型, 接收半径, 发射方向)` 场景并回放全部检测历史；清除失败的 20 m 排除圆只过滤有限位置样本，不切割连续位置多边形。Q4 默认启用自身的 `failed_clear_remeasure_mode="gated"`、`directional_rolling_mode="scenario"` 和 `long_clear_tail_mode="adaptive"`，方向滚动软截止为 3 s；有限模型失效或超时回退 27 m 连续安全清除。Q3 的全向滚动、联合批测和 beam/cache 均保持 `off`；insertion+2opt 路线可显式开启但默认关闭。
- Q1/Q2 已有分题 README、单元测试、三模式数据生成器、对拍器、人工验收清单和人工结果模板。
- Q3/Q4 README 明确为待验证原型；已有离线测试位于 `tests/q3/test_offline.py` 与 `tests/q4/test_offline.py`。
- `src/sim/` 已实现严格请求/响应校验、回环HTTP客户端、幂等与并发保护、现实时间安全退出、逐动作JSONL、离线规则替身和三动作smoke；Q3/Q4 在线策略结束时还会输出“平均用时 = 总虚拟时间 / 清除成功的信号源数”，零个成功源时显示无法计算。人工步骤见 `tests/sim/verify_manual.md`。
- 2026-09-12 Q4 两项门控完成后，全项目 130/130 通过，耗时 91.666 s。新增检查覆盖大后验三角探测证书、方向滚动选择、原地补测同点性、Q4 默认开关及现场 CLI 传参；Q2 双版本和 Q3 原有分支回归同时通过。全部检查只使用单元测试、本机回环假服务器和 `FakeSimulator`；当前环境没有官方模拟器，Q1-Q4 状态仍为【待验证】。
- 2026-09-12 用户把 Q3/Q4 的滚动评价默认真实墙钟软截止统一由 1 s 改为 3 s；策略构造器、离线 CLI、官方入口、基准默认值、人工命令和文档已同步。2026-09-13 的 Q4 长尾/路线基准和全项目回归已使用 3 s 配置。
- 2026-09-12 官方日志 `output/sim/q4_20260912-225859-514262.jsonl` 暴露频道 9 的单源长清除尾：42 次失败后第 43 次成功，约耗时 467.2 虚拟秒。根因是首次 CVaR 滚动主动选择安全清除并永久停止探测，三次原地 `no_signal` 又不改变连续域或清除路线。现已加入低频救援：连续失败 8 次后最多一次、以有限后验均值收益门控的移动方向探测；原日志局部状态回放确认旧策略继续 clear、新策略改为 measure，且失败后仍回到完整安全清除尾。
- 2026-09-13 固定种子 20269912 的 8 场景四模式单进程配对全部 8/8 完整清除且无源证书正确。长尾单独模式与基线动作、虚拟时间完全相同（检查 2 次、启动 0 次）；路线单独模式平均虚拟时间 15450.744→15171.465 s，P90 18070.489→17742.081 s，移动 65469.345→63943.577 m，6/8 胜，但失败清除 20.500→24.125、墙钟 10.533→13.819 s；合并平均 15163.679 s、6/8 胜。结论：长尾救援默认保留；路线保留为显式实验开关，默认关闭。结果见 `output/q4_offline/long_tail_route_benchmark_sequential.{json,md}`。
- 2026-09-13 改用 25 点发现网后，定向 Q4/CLI 测试 20/20 通过；全项目 `python -B -m unittest discover -s tests -t . -v` 为 138/138 通过，耗时 87.457 s。新增测试核对 25 个探测点、33 个相交三角形的顶点闭包、985 m 边长、约 24552.150 m 原点出发路线及稠密位置/方向可见性；Q1-Q4 状态仍为【待验证】。
- Q4 发现扫描固定种子 20265912 的 8 个混合场景中，121 点与 37 点均 8/8 完整发现且无源证书正确；37 点平均检测数 1256.625→361.125、移动 63535.534→32400.000 m、扫描虚拟时间 20126.982→8611.000 s（-57.217%）。完整策略独立种子 20266912 的 8 场景中两者均 8/8 完整清除，37 点 8/8 更快，平均虚拟时间 29520.873→18240.103 s（-38.213%），但平均失败清除数 601.125→689.375，显示大后验区域仍需定向复测优化。结果见 `output/q4_offline/{scan,policy}_benchmark.{json,md}`。
- 路线配对使用种子 20263912 的 4 个相同场景，FIM/滚动/路线软截止为 10/1/0.25 s，27 m 网格、CVaR、每源顺便测量上限 3、失败清除复测开启。current 与 insertion_2opt 均 4/4 完整清除；新路线 3/4 胜，平均总虚拟时间 5966.309→5377.612 s，P90/最坏值 6717.235→5876.333 s，平均 resolve 移动 17285.294→14399.309 m，跨源移动 14914.362→12767.182 m，长跳 4.50→3.25；平均真实墙钟 137.362→149.947 s。第 2 场反增 391.246 s；118 次路线调用 `ok/partial/fallback=72/7/39`。结果见 `output/q3_offline/route_benchmark.{json,md}`，小样本不足以自动打开正式默认。
- 第二部分训练种子 20264912 的 1 个场景中束宽 1/2/4 虚拟时间相同，束宽 1 墙钟最低，故锁定束宽 1。随后用第一部分相同种子 20263912 做 4 场景三策略配对，三者均 4/4 完成。beam_cached 相对 insertion_2opt 为 0/4 胜，平均虚拟时间 5236.592→5417.769 s（+181.176 s），P90 5876.333→5918.775 s，跨源移动 +1306.861 m，现实墙钟 206.465→194.052 s；缓存命中率 77.9%，每场平均扩展 841.25 节点。结果见 `output/q3_offline/route_part2_beam_train.json` 与 `route_part2_benchmark.{json,md}`。第二部分没有稳定优于第一部分，正式候选保留 insertion_2opt，beam_cached 只作实验模式。
- 固定种子 20260911 的 200 个合法首测案例全部可比较：以有限场景最坏后验半径为主指标，分时限连续 FIM 优于离散基线 200/200（100%），均值由 119.037 m 降至 70.082 m；以 `T+0.5R` 为指标仅 76/200（38%）更优。连续点平均多 29.706 s 虚拟动作时间。16 进程墙钟 122.015 s。结果文件为 `tests/q2/analysis/q2_200_case_comparison.{md,json}`。
- 当前机器单案例粗测：仅离散且不生成近优域 3.741 s；分时限 FIM 且不生成近优域 4.115 s；默认在线近优域 6.919 s；离线较密近优域 17.227 s。它们是 CPU/墙钟时间，不是机器狗虚拟时间。
- `Q2数学建模与双方案比较.md` 已把 $K_1$ 的 24 边粗外包更新为局部自适应圆弧细化表述；保证接收域仍使用 72 边内近似，可能接收域仍使用 72 个支撑方向外近似。绘图脚本 `../paper/code/q2_region_figures.py` 与论文 TeX 尚未针对新细化重新生成和排版核对；当前环境无 XeLaTeX，整篇排版仍待 Windows 双次编译和人工检查。

## Important interfaces and nesting

- Q1：`analyze_q1` → `localize` → 半平面交、凸包、旋转卡壳。
- Q2：`Q2Config.q2_version` → `build_region_from_observations/extend_region_with_observation` 的 `new|legacy` 圆域分流；随后 `plan_second_point` → `plan_measurement` → 离散候选评分 + 多预算 `optimize_continuous_fim` → 集合复评分/Pareto → `_near_optimal_outputs`。顶层 `selected_point` 是最终混合推荐。
- Q3/Q4：策略由 `runtime.runner.run_policy(policy, client)` 驱动；Q4 继承 Q3 的动作与清除状态机。Q4 不调用 Q3 全向滚动，而由 `q4.rolling.evaluate_directional_probe_decision` 对方向探测序列、失败点同点测量和长尾一步救援估值；`q4.directional.certified_probe_points` 提供连续证书。可选路线复用 `q3.route` 的服务块、最便宜插入和 2-opt，并以 `route_active_channel` 保证选中源由原 Q4 单源策略处理完成。
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
python src/q2/cli.py --demo --q2-version new --no-show --output output/q2_new.png --result-json output/q2_new.json
python src/q2/cli.py --demo --q2-version legacy --no-show --output output/q2_legacy.png --result-json output/q2_legacy.json
python -B tests/q2/benchmark_arc_refinement.py --count 200 --plan-count 20 --repeats 7 --seed 20260912
python -B tests/q2/benchmark_200.py --count 200 --seed 20260911 --workers 16
python -B tests/q3/benchmark_adaptive.py --cases 8 --workers 4 --output output/q3_offline/strategy_benchmark.json
python -B tests/q3/benchmark_joint.py --cases 8 --workers 4 --output output/q3_offline/joint_benchmark.json
python -B tests/q3/benchmark_failed_clear_remeasure.py --cases 8 --workers 4 --fim-cpu-time-limit-s 10 --output output/q3_offline/failed_clear_remeasure_benchmark.json
python -B tests/q3/benchmark_rolling_time.py --train-cases 2 --validation-cases 4 --train-seed 20260912 --validation-seed 20262912 --workers 4 --fim-cpu-time-limit-s 10 --rolling-cpu-time-limit-s 3 --output output/q3_offline/rolling_time_benchmark.json
python -B tests/q3/benchmark_route_beam_train.py --cases 1 --seed 20264912 --widths 1 2 4 --workers 3 --output output/q3_offline/route_part2_beam_train.json
python -B tests/q3/benchmark_route.py --cases 4 --seed 20263912 --workers 4 --fim-cpu-time-limit-s 10 --rolling-cpu-time-limit-s 3 --route-cpu-time-limit-s 0.25 --beam-route-cpu-time-limit-s 1 --cache-capacity 4096 --beam-width 1 --beam-max-expansions 512 --output output/q3_offline/route_part2_benchmark.json
python -B tests/q4/benchmark_scan.py --cases 8 --seed 20265912 --output output/q4_offline/scan_benchmark.json
python -B tests/q4/benchmark_policy.py --cases 8 --seed 20266912 --max-actions 10000 --output output/q4_offline/policy_benchmark.json
python -B tests/q4/benchmark_measurement_strategy.py --cases 8 --seed 20267912 --max-actions 10000 --rolling-cpu-time-limit-s 3 --output output/q4_offline/measurement_strategy_benchmark.json
```

人工改变 Q1/Q2 状态前，必须执行对应 `tests/qN/verify_manual.md` 的完整清单并填写 `test_res.md`。

## Open decisions / next steps

- **Confirmed geometry:** `ring7` 的原点加半径1500 m正六边形六顶点，以1000 m接收圆完整覆盖半径1800 m目标圆。最坏位置为外圆边界与相邻环点角平分线，最近距离 `sqrt(1800^2+1500^2-2*1800*1500*cos30°)=901.921737 m`，有98.078263 m距离余量。
- **Implemented Part 1:** Q3 扫描阶段仍用 `ring7()` 形成完整发现证书，发现频道后进入自适应单源处理。半径小于等于 19.9 m 直接清除；否则比较当前后验区域网格的实际最坏清除成本与“一次 FIM 检测 + 按预测半径比例缩放后的清除成本”，预计至少节省 10 s 才检测。最多 5 次，连续两次实际收缩不足 5% 时停止。保底采用覆盖当前后验多边形的 27 m 方格点，理论覆盖半径约 19.092 m，相对 20 m 清除半径保留约 0.908 m 余量；失败点被记录并继续有限点列。
- **Rejected Part 2:** “每完成一个扫描站后最多处理两个局部动作”只留在 `tests/q3/benchmark_adaptive.py` 的 `InterleavedQ3Policy`。8 组离线配对虽都完整清除，但只赢 1 组，平均多 1359.270 s；原因是局部动作打断扫描路线后产生额外往返。因此正式 `src/q3/policy.py` 不含交错阶段或开关。
- **Implemented Part 2 v2:** Q3 以虚拟时间为目标实现同点多频道联合批测。扫描阶段只在既定 `ring7` 站点顺便复测：只要该点对已发现源的整个当前后验区域保证接收就追加一次，不再要求边际节省；扫描结束后，对所有可细化源生成 Q2/FIM 目标点，先选择从当前位置动作时间最短且预计值得复测的目标。到点后目标频道必测，其他频道仍需同时满足保证接收、预计清除成本节省超过追加检测成本且未超过每源三次顺便测量。扫描和后续联合规划共用每源三次上限，顺便测量不占五次专用 FIM 配额。固定 8 场景中的旧联合基准早于本次固定站规则与参数调整，需重跑后才能评价新规则；`all_active` 保留为激进离线对照。
- **Implemented two-task plan:** 任务一“每次保底清除失败后条件复测”和任务二“用 Q2 候选推演测量后验并按总虚拟时间滚动决策”均已作为独立开关编码、测试和基准。任务二首版把跨源续程视为零，在种子 20261912 的 4 场景中仅赢 2 场且均值/P90变差；逐场证据显示动作减少但移动变长。修正为加入“清除路线终点到最近其他源中心”的续程后，使用新验证种子 20262912 达到 4/4 胜出，故 Q3 默认同时启用两个任务。不得把此结果称为严格全局最优。
- **Implemented grid thinning and route Part 1:** Q3 默认清除方格为 27 m，最远格点距离 `27/sqrt(2)=19.0919... m`，相对 20 m 清除半径保留约 0.908 m 几何余量。第一部分小规模路径规划已替代“只按最近中心一步续程”作为可选源排序层，并完成当前 27 m 参数下的独立配对；正式默认仍关闭。缓存与有限束搜索未实施，详见 `src/TODO.md`。
- **Implemented Q4 phases 1-7:** 完整探测组计数、动态四侧偏移、安全后验清除、25 点发现网、有限联合后验、原地补测、方向滚动、长尾救援和可选 insertion+2opt 多源路线均已完成。长尾方案只在同源连续 8 次清除失败后最多启动一次有限后验认可的移动探测；全局单步化、逐次失败重排、空间冷却和强制绕行因退化或无收益依据被否决。路线只排源间顺序并锁定单源服务，不接入 Q2 离散候选点、连续 FIM、Pareto 规划或 Q3 beam/cache。8 场景结果支持长尾默认开启、路线仅可选保留；这些结果生成于旧 37 点发现网。
- **Confirmed rolling policy:** 默认 `rolling_time_mode="scenario"` 时，Q3 把 Q2 的离散基线、连续 FIM 多预算解、Pareto、顶层推荐及保证接收域候选放入同一池，按有限场景预计总虚拟时间选择测点或直接清除，并不固定执行单纯 FIM 或顶层推荐。`prefer_continuous_fim=True` 只在关闭滚动模式时生效；若必须在顶层混合推荐与单纯 FIM 之间选，保留含离散安全后备的顶层推荐。
- **Implemented multi-source route Part 2, retained Part 1 candidate:** `src/q3/cache.py` 已实现状态键有界缓存，`route.py` 已实现带第一部分 incumbent 的有限束搜索，CLI 可显式选择 `beam_cached`。训练选择束宽 1 后，4 场景验证没有显示相对 insertion_2opt 的额外收益，因此不把第二部分设为默认；后续若继续，应先校准服务块预测误差而不是盲目扩大束宽。
- **Current assessment for adaptive arc refinement:** 融合后的固定种子 200 例几何消融在 24/16 边下均为嵌套失败、真值包含失败和径向目标失败 0/200；24 边源域 MEC 半径平均下降 3.0455 m，16 边平均下降 6.8922 m。当前机器上区域构造墙钟分别增加约 9.34%/22.80%，离散规划增加约 10.51%/17.73%。这些结果与单元/离线回归证明兼容性，但尚未重跑完整连续 FIM 和 Q3/Q4 同场景总时间配对，不能据此声称整体策略优化。
- 队员可按 `tests/q2/verify_manual.md` 人工验收两种确切点、分时限预算、Pareto 前沿、5%/10%近优域和局部放大图；正式报告不得把 200 例的 100% 写成全局最优概率。
- 若后续需要标量化，可对归一化 lambda 做训练集网格扫描、Pareto拐点和独立种子验证；当前正式实现优先采用硬时间预算，未引入 lambda。
- 队员决定 Q3/Q4 的独立对拍判据、参考实现与人工验收流程后，再建立完整测试体系。
- 队员按 `tests/sim/verify_manual.md` 启动 Q3、Q4 演练，先分别完成三动作 smoke 并核对模拟器界面与本地 JSONL；此前不要运行正式测试。
- Q3 smoke 通过后，在线完整策略显式使用 `--q2-version new --max-refinements 5 --fim-cpu-time-limit-s 10 --joint-batch-mode guaranteed --failed-clear-remeasure-mode gated --rolling-time-mode scenario --rolling-risk-metric cvar --rolling-cpu-time-limit-s 3`；Q4 使用同一个 3 s 滚动参数。旧版回归只能在新测试启动前把 `new` 改成 `legacy`。10 s 与 3 s 都是真实墙钟限制，不是虚拟动作时间，其中 3 s 为滚动评价软截止。
- 正式提交前由人工审核历史记录、AI 使用日志、状态总表和生成测试数据。

## Handoff

从 `快速上手指南.md` 查看结构和状态，从分题 README 找算法到代码的映射，从 API.md 获取测试数据契约。Q4 默认采用 25 点认证发现网，长尾救援默认开启；Q4 insertion+2opt 已实现但旧 37 点网的 8 场景中仅 6/8 胜且失败清除增加，默认保持关闭，可在离线或人工明确决定的在线运行中显式开启。Q2 离散候选点、连续 FIM、Pareto 规划及 Q3 beam/cache 都没有接入 Q4，后续要求见 `src/TODO.md`。最新全项目回归 138/138 通过；25 点完整策略配对和官方模拟器验收均未执行，Q1-Q4 仍为【待验证】。
