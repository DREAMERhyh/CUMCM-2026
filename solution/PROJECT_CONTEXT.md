# PROJECT_CONTEXT

## Mission

按 `操作手册.md` 建立 B 题 Q1/Q2 优先的代码组织、接口文档和测试体系，并保留 Q3/Q4 离线原型供后续开发。当前工作根目录为 `solution/`。

## Hard constraints

- 禁止 AI 执行任何 Git 操作。
- Q1–Q4 当前状态一律为【待验证】；只有人工按清单验收后才能改状态。AI 不得标记【已验证】或【模拟器未测试】。
- Q1/Q2 API 必须归纳自真实函数签名；接口语义或官方协议不确定时必须暂停询问。
- 不修改题目 PDF、附件或其他原始材料。
- Q3/Q4 本轮不新增对拍策略，只保留、归位现有离线测试。

## Confirmed decisions

- `src/runtime/` 作为 Q3/Q4 共用运行层；HTTP 字段仅是协议草案，正式契约待补充。
- 旧浏览器/合成环境归入 `src/legacy/`，环境回归归入 `tests/legacy/`。
- Q2 对拍只核验连续域包含关系、时间记账、有限候选评分与选择，不声称连续空间全局最优。
- 历史 `test_res_q*.md` 和 `VERIFICATION.md` 保留，但不代表当前人工状态；新模板在 `tests/q1|q2/test_res.md`。

## Current state (2026-09-11)

- 源码已按 `src/q1`、`q2`、`q3`、`q4`、`common`、`runtime`、`legacy` 整理，所有内部导入已修复。
- Q1 对外接口：`q1.analyze_q1`、`q1.localize`；契约见 `src/q1/API.md`。
- Q2 对外接口：`Q2Config`、`build_candidate_regions`、`plan_measurement`、`plan_second_point`；契约见 `src/q2/API.md`。
- Q1/Q2 已有分题 README、单元测试、三模式数据生成器、对拍器、人工验收清单和人工结果模板。
- Q3/Q4 README 明确为待验证原型；已有离线测试位于 `tests/q3/test_offline.py` 与 `tests/q4/test_offline.py`。
- 目录重组后的全量自动回归为 52 项通过；Q1/Q2 `test_unit.py` 均可直接运行。三种 Q1 和 Q2 小规模生成/对拍冒烟均为零失败。以上仅是脚本可运行性检查，不改变状态。

## Important interfaces and nesting

- Q1：`analyze_q1` → `localize` → 半平面交、凸包、旋转卡壳。
- Q2：`plan_second_point` → `build_region_from_observations`（复用 Q1 几何）→ `plan_measurement` → 连续候选域/离散候选评分。
- Q3/Q4：策略由 `runtime.runner.run_policy(policy, client)` 驱动；Q4 继承 Q3。Q3 细化阶段可调用 Q2，但离线 CLI 当前以 `max_refinements=0` 运行。

## Verification commands

在 `solution/` 下：

```powershell
python -B -m unittest discover -s tests -t . -v
python tests/q1/test_unit.py
python tests/q2/test_unit.py
python tests/q1/gen_data.py --mode random --seed 42
python tests/q1/test_duipai.py --dir tests/q1/data/random
python tests/q2/gen_data.py --mode random --seed 42
python tests/q2/test_duipai.py --dir tests/q2/data/random
```

人工改变 Q1/Q2 状态前，必须执行对应 `tests/qN/verify_manual.md` 的完整清单并填写 `test_res.md`。

## Open decisions / next steps

- 队员决定 Q3/Q4 的独立对拍判据、参考实现与人工验收流程后，再建立完整测试体系。
- 队员提供并确认官方模拟器请求、响应、舍入和时序后，再更新 `runtime/http_client.py` 与 API 边界。
- 正式提交前由人工审核历史记录、AI 使用日志、状态总表和生成测试数据。

## Handoff

从 `快速上手指南.md` 查看结构和状态，从分题 README 找算法到代码的映射，从 API.md 获取测试数据契约。不要把自动测试“通过”理解为人工验收或官方模拟器成绩。
