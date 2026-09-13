# PROJECT_CONTEXT

## Mission

维护 B 题 Q1/Q2 建模与测试体系、Q3/Q4 离线策略原型，以及按官方附件实现的模拟器通信层。当前工作根目录为 `solution/`。

## Hard constraints

- 禁止 AI 执行任何 Git 操作。
- Q1–Q4 当前状态一律为【待验证】；只有人工按清单验收后才能改状态。AI 不得标记【已验证】或【模拟器未测试】。
- Q1/Q2 API 必须归纳自真实函数签名；接口语义或官方协议不确定时必须暂停询问。
- 不修改题目 PDF、附件或其他原始材料。
- Q3/Q4 本轮不新增对拍策略，只保留、归位现有离线测试。

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

## Current state (2026-09-13)

- 源码已按 `src/q1`、`q2`、`q3`、`q4`、`common`、`runtime`、`sim`、`legacy` 整理，所有内部导入已修复。
- Q1 对外接口：`q1.analyze_q1`、`q1.localize`；契约见 `src/q1/API.md`。
- Q2 对外接口：`Q2Config`、`build_candidate_regions`、`optimize_continuous_fim`、`plan_measurement`、`plan_second_point`；契约见 `src/q2/API.md`。
- Q2 的 `src/q2/continuous_fim.py` 支持多个绝对动作时间上限共享场景/缓存；`src/q2/near_optimal.py` 负责局部近优域采样和凸包输出。默认规划返回 `baseline`、`continuous_fim`、`comparison`、`pareto_front`、`recommendation_source` 及两套近优域。
- Q2 演示图同图显示离散基线红星、连续 FIM 蓝菱形、最终推荐黑圈、5%/10%近优域及局部放大、两方案综合分数、`T-R` Pareto 前沿。示例产物为 `output/q2_pareto_regions.png`、`output/q2_pareto_regions.json`。
- Q3 细化规划已启用 Q2 连续 FIM，关闭绘图用近优域，单次 FIM CPU 墙钟上限按用户要求设为 6 s；正式 `sim/cli.py` 可用 `--fim-cpu-time-limit-s` 显式覆盖。Q4 继承该参数。
- Q1/Q2 已有分题 README、单元测试、三模式数据生成器、对拍器、人工验收清单和人工结果模板。
- Q3/Q4 README 明确为待验证原型；已有离线测试位于 `tests/q3/test_offline.py` 与 `tests/q4/test_offline.py`。
- `src/sim/` 已实现严格请求/响应校验、回环HTTP客户端、幂等与并发保护、现实时间安全退出、逐动作JSONL、离线规则替身和三动作smoke；人工步骤见 `tests/sim/verify_manual.md`。
- 2026-09-11 最新自动检查：Q2 单元/CLI 9/9 通过；random、boundary、adversarial 三组对拍各 4/4 通过；Q3 7/7、Q4 4/4 离线测试通过；全项目 `unittest` 76/76 通过，耗时 66.071 s。Q3 在线同款离线 CLI 执行 140 动作、两次细化，成功清除频道 3，虚拟时间 2959.614 s。以上未连接官方模拟器，Q1-Q4 状态仍为【待验证】。
- 固定种子 20260911 的 200 个合法首测案例全部可比较：以有限场景最坏后验半径为主指标，分时限连续 FIM 优于离散基线 200/200（100%），均值由 119.037 m 降至 70.082 m；以 `T+0.5R` 为指标仅 76/200（38%）更优。连续点平均多 29.706 s 虚拟动作时间。16 进程墙钟 122.015 s。结果文件为 `tests/q2/analysis/q2_200_case_comparison.{md,json}`。
- 当前机器单案例粗测：仅离散且不生成近优域 3.741 s；分时限 FIM 且不生成近优域 4.115 s；默认在线近优域 6.919 s；离线较密近优域 17.227 s。它们是 CPU/墙钟时间，不是机器狗虚拟时间。
- 2026-09-11 新增：Q2 规划统一墙钟预算 `Q2Config.planning_wall_clock_budget_s`（默认 120 s，`common/budget.py` 共享 deadline，候选评分/FIM/近优域三阶段 anytime，返回 `planning_wall_time_used_s`/`planning_timed_out`；`fim_cpu_time_limit_s` 仍作为子上限生效，默认行为不变）。基准：`tests/q2/benchmark_anytime.py`（3 区域 × 6/60/300 s，实测预算 ≥ ~5.7 s 时 FIM 自然收敛、输出逐位一致）。
- 2026-09-11 新增：Q3 扫描布局 `scan_layout ∈ {ring7, hub_ring6, pure_ring8}`（`q3/coverage.py`）。hub_ring6（原点+6 环点 r=1200）覆盖最坏 968.9 m、扫描虚拟总时 2273.0 s；pure_ring8（8 环点 r=960）覆盖最坏 984.2 m、扫描虚拟总时 2172.7 s（比 ring7 的 2633.0 s 省 460 s）。2026-09-12 决策：**默认布局切换为 pure_ring8**（覆盖解析验证 984.21 m ≤ 995 设计裕量；扫描省 460 s）；回退方式：`Q3Policy(scan_layout="ring7")` 或 `run_drill.py --scan-layout ring7`。正式测试前若演练对账出现漏检，将按手册 E 节回退/切 hub_ring6。
- 【考古修正 2026-09-12】历史文字"组合策略平均 5873.934 s"（≈6000s）来自并行策略轨道（rolling_time/adaptive/joint 全套、20m 清除网格）在 4 个合成场景上的**本地规则替身离线对拍**（见 `test_res_q3_rolling_time.md`），**从未在官方模拟器实测**；该轨道代码不在当前 HEAD 分支线。当前主线性能演进与 V 形曲线解释见 `docs/性能演进考古_20260912.md`；当前默认（pure_ring8 + max_actions 8000 + use_optimal_stop=True + Q3BatchPolicy 入口）为官方实测可比口径下的历史最优（今晨 5 局 5/5 对账通过、同源数比凌晨交错快 16%~48%），已冻结，改动须走决策表回滚路径。
- 2026-09-13 新增问题三论文初稿：`paper/sections/08_q3_model.tex` 已按当前 `Q3BatchPolicy` 的执行流程写入八点扫描、观测区域递推、Q2 补充选点、Held--Karp 开放路径、TSPN 清除点和保底清除点队列模型；`paper/sections/03_problem_analysis.tex`、`04_model_assumptions.tex`、`05_notation.tex` 已同步。图片由 `paper/code/q3_figures.py` 生成至 `paper/figures/q3-eight-point-scan.{pdf,png}` 与 `q3-decision-tree.{pdf,png}`。统一“保底清除点”术语后，已修正决策树中重复的“保底点/清除队列”字样并重新导出 `q3-decision-tree.{pdf,png}`；源码检索、PDF 文本层、PNG 预览和 PDF 重渲染均无旧称、重复词、裁切或重叠。静态检查未发现缺失引用、重复标签或 LaTeX 环境不配对，Poppler 渲染确认两张 PDF 无裁切且中文字体已嵌入；Linux 无 XeLaTeX，整篇分页和交叉引用仍须在 Windows 连续编译两次后人工检查。论文明确保留实现边界：76 个保底清除点只在进入保底时 `r<=80 m` 才保留完整覆盖证明。
- 2026-09-13 新增问题四论文初稿：按用户要求不修改 `solution/src/` 与测试代码，只更新 `paper/sections/03_problem_analysis.tex`、`04_model_assumptions.tex`、`05_notation.tex`、`09_q4_model.tex`、`main.tex` 和 `README.md`。正文以“Q3 已完成”衔接，重点写入 25 点三角网、四侧与局部三角探测组、源位置/类型/半径/方向的有限可能状态、条件尾部均值滚动选点和清除反馈；问题四正文及两张新图不使用用户排除的两个术语。`paper/code/q4_figures.py` 生成 `q4-triangular-scan.{pdf,png}` 与 `q4-decision-tree.{pdf,png}`。静态检查无重复标签、缺失引用、缺失文献或环境不配对，Q4 本地离线测试 8/8 通过；Poppler 重渲染确认两张 PDF 无裁切，整篇仍因 Linux 无 XeLaTeX 而未完成最终分页检查。

## Important interfaces and nesting

- Q1：`analyze_q1` → `localize` → 半平面交、凸包、旋转卡壳。
- Q2：`plan_second_point` → `build_region_from_observations`（复用 Q1 几何）→ `plan_measurement` → 离散候选评分 + 多预算 `optimize_continuous_fim` → 集合复评分/Pareto → `_near_optimal_outputs`。顶层 `selected_point` 是最终混合推荐。
- Q3/Q4：策略由 `runtime.runner.run_policy(policy, client)` 驱动；Q4 继承 Q3。Q3 细化阶段调用 Q2 顶层混合推荐；离线 CLI 与正式在线 CLI 默认均为 `max_refinements=2`、单次 FIM 墙钟上限 6 s，近优域关闭。
- 官方模拟器：`sim.cli` → `sim.live_runner.run_live_policy` → Q3/Q4或smoke策略 → `sim.client.HttpRobotClient.execute` → `sim.protocol` 严格校验。网络失败只用原ID和原正文重试；结果不确定时禁止把该ID绑定到其他动作。

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
```

人工改变 Q1/Q2 状态前，必须执行对应 `tests/qN/verify_manual.md` 的完整清单并填写 `test_res.md`。

## Open decisions / next steps

- 队员可按 `tests/q2/verify_manual.md` 人工验收两种确切点、分时限预算、Pareto 前沿、5%/10%近优域和局部放大图；正式报告不得把 200 例的 100% 写成全局最优概率。
- 若后续需要标量化，可对归一化 lambda 做训练集网格扫描、Pareto拐点和独立种子验证；当前正式实现优先采用硬时间预算，未引入 lambda。
- 队员决定 Q3/Q4 的独立对拍判据、参考实现与人工验收流程后，再建立完整测试体系。
- 队员按 `tests/sim/verify_manual.md` 启动 Q3、Q4 演练，先分别完成三动作 smoke 并核对模拟器界面与本地 JSONL；此前不要运行正式测试。
- Q3 smoke 通过后，在线完整策略显式使用 `--max-refinements 2 --fim-cpu-time-limit-s 6`；6 s 是每次规划墙钟上限，不是虚拟动作时间。
- 队员审阅问题三与问题四初稿中的执行参数和证明，重点核对问题四的 $0.5/0.5$ 初始相对权重、三角网参数、条件尾部均值比较和长尾补测阈值；随后在 Windows XeLaTeX 连续编译 `paper/main.tex` 两次，检查四张新增图、符号表、分页及文献引用。
- 正式提交前由人工审核历史记录、AI 使用日志、状态总表和生成测试数据。

## Handoff

从 `快速上手指南.md` 查看结构和状态，从分题 README 找算法到代码的映射，从 API.md 获取测试数据契约。问题三、问题四论文初稿及各自两张图已完成静态核验；下一步由队员核对两问的执行参数和模型边界，再在 Windows XeLaTeX 检查整篇版式。模拟器阶段先读 `src/sim/README.md`，再由队员执行 `tests/sim/verify_manual.md`。不要把自动测试“通过”理解为人工验收或官方模拟器成绩。
