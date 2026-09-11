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
- Q2 保留原离散搜索为兼容基线（`selected_point`/`selected`），新增结果放在 `continuous_fim`；两种选点都用原集合评分器复算后才能比较分数。
- 连续 FIM 只对第二测点坐标做连续多起点投影模式搜索，源位置鲁棒性仍用多边形边界场景近似，结论只能写成 FIM 替代目标的数值近似。
- Q2 题面只明确要求“较好的定位效果”，未规定时间-距离权重。当前建议以有限场景最坏后验包围半径 `worst_case_radius_m` 为主评价、动作时间为次级评价；FIM 只生成候选，最终必须由集合后验指标裁决。`score=T+0.5R` 保留为 Q3 导向的工程敏感性指标，0.5 s/m 不是题目常数。
- 题面原文要求“候选区域”而非一维区间。除物理保证/可能接收域外，建议用近优子水平集 `C_eta={s in F_g: R_wc(s)<=(1+eta)R_wc*}` 表达效果候选区域，并以多边形或多多边形输出。
- 用户已原则确认 Q2 后续采用“多个时间预算下优化 FIM → 集合 `R_wc,T` 复评分 → Pareto 筛选 → 按 Q3/Q4 时间预算取执行点”。此前连续方案平均多 81.706 s 指机器狗动作模型的虚拟时间，不是 CPU 时间；当前 FIM 已除以动作时间，但惩罚不足。
- 用户确认两个方案都保留确切点，并各自增加“5%近优域”“10%近优域”输出及同图可视化；不称置信区间。实现应区分在线快速近似和离线高精度绘图，避免近优域计算挤占 20 min 程序运行时间。
- 历史 `test_res_q*.md` 和 `VERIFICATION.md` 保留，但不代表当前人工状态；新模板在 `tests/q1|q2/test_res.md`。

## Current state (2026-09-11)

- 源码已按 `src/q1`、`q2`、`q3`、`q4`、`common`、`runtime`、`sim`、`legacy` 整理，所有内部导入已修复。
- Q1 对外接口：`q1.analyze_q1`、`q1.localize`；契约见 `src/q1/API.md`。
- Q2 对外接口：`Q2Config`、`build_candidate_regions`、`optimize_continuous_fim`、`plan_measurement`、`plan_second_point`；契约见 `src/q2/API.md`。
- Q2 已加入 `src/q2/continuous_fim.py`。默认规划同时返回 `baseline`、`continuous_fim` 和 `comparison`；Q3 显式关闭连续 FIM，继续使用兼容基线，避免无用计算。
- Q2 演示图已改为同图显示离散基线红星、连续 FIM 蓝菱形和两者同口径评分柱状图；示例产物为 `output/q2_comparison.png`、`output/q2_comparison.json`。
- Q1/Q2 已有分题 README、单元测试、三模式数据生成器、对拍器、人工验收清单和人工结果模板。
- Q3/Q4 README 明确为待验证原型；已有离线测试位于 `tests/q3/test_offline.py` 与 `tests/q4/test_offline.py`。
- `src/sim/` 已实现严格请求/响应校验、回环HTTP客户端、幂等与并发保护、现实时间安全退出、逐动作JSONL、离线规则替身和三动作smoke；人工步骤见 `tests/sim/verify_manual.md`。
- 2026-09-11 自动检查：Q2 单元测试 9/9 通过；random、boundary、adversarial 三组对拍各 4/4 通过；模拟器通信专项 23/23 通过；全项目 `unittest` 75/75 通过。Q3/Q4 离线CLI分别以154和2478个动作正常结束。演示中离散基线分数 207.184，连续 FIM 点的同口径分数 234.433。以上仅是程序检查，未启动或连接官方模拟器，Q1-Q4 状态仍为【待验证】。
- Q2 新增 `tests/q2/benchmark_200.py` 及 `tests/q2/analysis/q2_200_case_comparison.{md,json}`。固定种子 20260911 的 200 个合法首测案例全部可比较：按最坏后验半径，连续 FIM 优于离散基线 184/200（92%）；按当前 `T+0.5R`，连续 FIM 优于基线 0/200。16 个半径退化案例平均恶化 609.142 m，证明不能让 FIM 单独作最终裁决。
- 已有单案例粗测：仅离散 baseline 约 5.08 s CPU墙钟，baseline+当前连续 FIM 约 7.64 s，连续部分增量约 2.56 s；200例用16进程墙钟约134 s。未来多预算/Pareto/近优域开销尚未实测，必须实现后专项基准。

## Important interfaces and nesting

- Q1：`analyze_q1` → `localize` → 半平面交、凸包、旋转卡壳。
- Q2：`plan_second_point` → `build_region_from_observations`（复用 Q1 几何）→ `plan_measurement` → 离散候选评分 + `optimize_continuous_fim`；旧 `selected_point` 仍指向离散分支。
- Q3/Q4：策略由 `runtime.runner.run_policy(policy, client)` 驱动；Q4 继承 Q3。Q3 细化阶段可调用 Q2，但离线 CLI 当前以 `max_refinements=0` 运行。
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

- 实现已确认的多时间预算连续候选、集合复评分、Pareto筛选和执行点选择；建议先用相对 baseline 的 `ΔT={15,30,60}s` 做灵敏度试验，再决定 Q3/Q4 默认预算。
- 为 `baseline` 与 `continuous_fim` 增加 `near_optimal_regions.5pct/10pct` 多多边形、面积和局部坐标包络；绘图以红/蓝半透明填充、实线5%边界、虚线10%边界显示。先实现在线局部近似和离线自适应网格两档并实测CPU开销。
- 对归一化 lambda 做训练集网格扫描、Pareto拐点和独立种子验证；优先采用硬时间预算，lambda只保留作敏感性/备选标量化参数。
- 队员决定 Q3/Q4 的独立对拍判据、参考实现与人工验收流程后，再建立完整测试体系。
- 队员按 `tests/sim/verify_manual.md` 启动 Q3、Q4 演练，先分别完成三动作 smoke 并核对模拟器界面与本地 JSONL；此前不要运行正式测试。
- 正式提交前由人工审核历史记录、AI 使用日志、状态总表和生成测试数据。

## Handoff

从 `快速上手指南.md` 查看结构和状态，从分题 README 找算法到代码的映射，从 API.md 获取测试数据契约。模拟器阶段先读 `src/sim/README.md`，再由队员执行 `tests/sim/verify_manual.md`。不要把自动测试“通过”理解为人工验收或官方模拟器成绩。
