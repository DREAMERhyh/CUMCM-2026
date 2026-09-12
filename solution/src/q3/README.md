# Q3：全向干扰源定位与清除

题意：机器人需要在多个频道上寻找全向干扰源，通过移动、检测、定位和清除提高规定时间内的完成效果。

当前状态：【待验证】。

策略仍是待官方模拟器验收的算法原型。7 个固定检测点继续负责形成全区域发现证书；发现源后，Q3 调用 Q2 产生离散、连续 FIM 和 Pareto 候选，再由 Q3 的总虚拟时间滚动评价决定“继续检测还是直接清除”。

单源处理不再固定检测两次。共同硬条件是：最小包围圆半径不超过 19.9 m 时直接清除；每源至多专用细化 5 次；连续两次实际半径改善不足 5% 时停止。关闭总时间滚动模式时，保留旧的半径平方成本代理作为回归基线；默认滚动模式则使用下文的真实分支网格成本。停止后都以 27 m 方格覆盖当前后验多边形，理论覆盖半径约 19.092 m，相对 20 m 清除半径保留约 0.908 m 几何余量，不再遍历首次示向产生的整条固定带状区域。

进入保底清除后，默认启用 `failed_clear_remeasure_mode="gated"`。每次 `fallback_clear` 失败只触发一次判断；当前位置保证接收、没有重复测量、距最近有效观测至少 40 m、剩余清除点不少于 3 个、预计净节省超过 2 s 且每源实际复测未超过 3 次时，机器人在失败点原地复测当前频道。有效示向会重建后验区域并废弃旧清除路线；`no_signal` 或判断不通过则继续原有限点列，不会循环复测。清除失败的 20 m 排除圆目前只记录，不直接切割凸后验区域，以免破坏覆盖保证。

在此基础上，正式默认启用 `joint_batch_mode="guaranteed"`。固定 7 点扫描期间，机器人完成本站尚未发现频道的扫描后，会对已发现且当前位置对其整个后验区域保证 1000 m 接收的其他源各追加一次测量；此处利用既定停靠点，不再设置预计节省门槛。扫描结束后的联合规划则仍为所有可细化源生成候选，优先选择从当前位置动作时间最短的有效候选；机器人到达该点后，目标频道必测，其他频道只有在“保证接收，且预计清除成本节省超过追加检测成本”时才同点批测。每源最多接受三次顺便批测，扫描阶段与联合规划阶段共用该上限；顺便批测不占其五次专用 FIM 配额。

总时间任务默认启用 `rolling_time_mode="scenario"`。它不会修改 Q2：只读取 Q2 的顶层、离散、连续多预算、Pareto 和保证接收区域候选。对每个候选，从当前后验区域确定性抽取有限源位置场景，并枚举测角误差端点和零误差；每个分支真正构造测后后验、生成 27 m 清除覆盖并计算路线。估值同时加入该路线终点到最近其他未处理源后验中心的续程时间，避免单源局部最优造成跨源长距离折返。训练种子在 P90、CVaR 和最坏值三种口径中选择了 CVaR；只有“测量动作 + CVaR 后续成本 + 10 s 余量”小于立即清除成本才测量。单次评价墙钟软截止为 1 s，截止前已有完整候选时返回 `partial` 最优候选，否则安全回退清除。该方法只能称为“有限场景下的总虚拟时间滚动优化”，不是严格全局最优。

多源路线第一部分已经实现，但正式默认保持关闭，必须显式设置 `multi_source_route_mode="insertion_2opt"` 才启用。路线层把每个活动源表示为“入口—既有单源处理—保守出口”服务块，用最便宜插入构造开放路线，再用确定性 2-opt 消除局部折返；实际每次仍只执行一个动作，响应后重新规划。它不改变 Q2 候选、单源 measure/clear 结论、联合批测、27 m 清除点集合或失败复测，路线超时和异常会回退现有一步选择器。路线排序默认有独立的 0.25 s 真实墙钟软截止；缓存和有限束搜索属于尚未获授权的第二部分，未实施。

固定种子 20263912 的 4 场景同场景离线配对中，当前策略与 `insertion_2opt` 均 4/4 完整清除。新路线 3/4 场更快：平均总虚拟时间由 5966.309 s 降至 5377.612 s，P90/最坏值由 6717.235 s 降至 5876.333 s；平均 resolve 移动由 17285.294 m 降至 14399.309 m，平均跨源移动由 14914.362 m 降至 12767.182 m，平均长跳次数由 4.50 降至 3.25。平均真实墙钟由 137.362 s 增至 149.947 s。第 2 场总虚拟时间反增 391.246 s；118 次路线调用中 `ok/partial/fallback=72/7/39`，因此小样本结果只说明路线方向有实际收益迹象，不足以自动改正式默认。完整结果见 `output/q3_offline/route_benchmark.{json,md}`。

单次 FIM 真实墙钟上限默认 10 s，5%/10%近优域计算在线关闭。较早的“扫描点后立即单频道局部折返”在 8 组配对中平均增加 1359.27 s，仍只保留在 `tests/q3/benchmark_adaptive.py`。新的共享点批测见 `tests/q3/benchmark_joint.py`：在当时 6 s 单步上限的 8 组历史基准中，三种策略均完整清除；保证接收模式平均虚拟时间由 7553.85 s 降至 6880.95 s，6/8 场景更快，因此进入正式默认；`all_active` 仅作实验对照。10 s 默认值尚未重跑该正式基准。

固定种子 20260911 的 8 场景独立配对中，当前基线和“仅清除失败条件复测”均 8/8 完整清除。任务一平均虚拟时间由 6880.952 s 降至 6679.347 s，6/8 场景更快，P90 由 8085.280 s 降至 7511.044 s；平均失败清除数由 113.750 降至 74.125。60 次复测均得到有效示向，单场平均真实墙钟仅增加约 2.344 s，因此 Q3 默认启用。完整结果见 `output/q3_offline/failed_clear_remeasure_benchmark.json` 和 `test_res_q3_failed_clear_remeasure.md`。

任务二先用训练种子 20260912 的 2 场景选择 CVaR，再用未参与选择的种子 20262912 做 4 场景验证。四种配置均 4/4 完整清除：仅任务二相对旧基线 4/4 更快，平均减少 1514.308 s，P90 从 8335.650 s 降至 6930.223 s；任务一与任务二合用相对仅任务一也 4/4 更快，平均减少 1152.946 s，P90 从 7735.944 s 降至 6769.461 s。单场平均真实墙钟由任务一的 103.847 s 增至组合策略的 133.282 s，仍远低于 20 min。完整结果见 `output/q3_offline/rolling_time_benchmark.json` 和 `test_res_q3_rolling_time.md`。这些结果使用当时的 20 m 网格；27 m 默认网格已通过几何与离线流程回归，但尚未重跑该性能基准。

## 代码对应

| 功能 | 代码位置 |
|---|---|
| 7 点扫描、固定站保证接收顺便测量、状态机及滚动接入 | `q3/policy.py` |
| Q2 候选去重、分支后验、真实清除路线、CVaR和超时回退 | `q3/rolling_time.py` |
| 清除失败后的同点条件复测 | `q3/fallback_remeasure.py` |
| 后验网格、路线和旧半径平方判据 | `q3/adaptive.py` |
| 同点多频道联合批测 | `q3/joint.py` |
| 多源服务块、开放路线估值、最便宜插入和2-opt | `q3/route.py` |
| 四策略训练/验证基准 | `tests/q3/benchmark_rolling_time.py` |
| 当前策略与多源路线同场景配对 | `tests/q3/benchmark_route.py` |

`cli.py` 仍只运行本地 `sim.fake.FakeSimulator`，但默认参数已与在线策略一致：最多五次细化、单次 FIM 10 s。上线前可运行：

```powershell
python src/q3/cli.py --max-refinements 5 --fim-cpu-time-limit-s 10 --joint-batch-mode guaranteed --failed-clear-remeasure-mode gated --rolling-time-mode scenario --rolling-risk-metric cvar --rolling-cpu-time-limit-s 1 --output output/q3_offline/online_like_demo.json
```

离线配对基准（不连接官方模拟器）：

```powershell
python -B tests/q3/benchmark_adaptive.py --cases 8 --workers 4 --output output/q3_offline/strategy_benchmark.json
python -B tests/q3/benchmark_joint.py --cases 8 --workers 4 --output output/q3_offline/joint_benchmark.json
python -B tests/q3/benchmark_failed_clear_remeasure.py --cases 8 --workers 4 --fim-cpu-time-limit-s 10 --output output/q3_offline/failed_clear_remeasure_benchmark.json
python -B tests/q3/benchmark_rolling_time.py --train-cases 2 --validation-cases 4 --train-seed 20260912 --validation-seed 20262912 --workers 4 --fim-cpu-time-limit-s 10 --rolling-cpu-time-limit-s 1 --output output/q3_offline/rolling_time_benchmark.json
python -B tests/q3/benchmark_route.py --cases 4 --seed 20263912 --workers 4 --fim-cpu-time-limit-s 10 --rolling-cpu-time-limit-s 1 --route-cpu-time-limit-s 0.25 --output output/q3_offline/route_benchmark.json
```

官方通信、三动作演练烟雾测试和现场日志入口位于 `src/sim/`。必须先按 `tests/sim/verify_manual.md` 完成 smoke；在人工核对通过前，不得把本地通过理解为 Q3 官方策略通过。
