# 官方模拟器通信层

本目录实现 B 题附件1、附件2已经给出的机器狗 HTTP 接口。模块导入不会连接模拟器；只有人工启动 `cli.py`、显式确认接口就绪后才会发送请求。当前已完成本地协议与回环 HTTP 检查，尚未连接官方模拟器。

## 文件与职责

| 文件 | 对外接口 | 职责 |
|---|---|---|
| `protocol.py` | `validate_action(action)`、`build_request_payload(action, robot_id)`、`encode_request_payload(payload)`、`decode_response_body(body)`、`validate_response(action, http_status, response)` | 严格校验附件规定的字段、类型、范围和条件返回值。 |
| `client.py` | `SimulatorExchange`、`HttpRobotClient.request(action)`、`HttpRobotClient.execute(action)` | 只访问本机回环 HTTP；串行请求；网络故障时保持同路径、同正文、同 request_id 重试。 |
| `errors.py` | `SimulatorError` 及其子类 | 区分传输失败、HTTP错误、业务拒绝、协议错误、并发和幂等冲突。 |
| `fake.py` | `FakeSource`、`FakeSimulator.execute(action)` | 供离线策略测试使用的规则替身，不冒充官方模拟器。 |
| `live_runner.py` | `JsonlActionLogger`、`run_live_policy(...)` | 使用现实剩余时间、动作上限和安全余量运行策略，并逐动作刷新 JSONL 日志。 |
| `smoke.py` | `SmokePolicy` | 只执行 `/enter → /measure(0,0,频道1) → /exit`，用于首次演练联通检查。 |
| `cli.py` | `main(argv=None)` | 现场入口；默认 smoke，完整策略需二次显式确认。 |

`runtime/runner.py` 仍是通用离线策略驱动器。原 `runtime/http_client.py` 和 `runtime/fake_simulator.py` 只保留兼容导出，新代码应从 `sim` 导入。

## 已实现的协议约束

- 只允许 `POST /enter`、`POST /measure`、`POST /clear`、`POST /exit`。
- 公共请求字段是 `arena_id="default"`、当前登录参赛队号 `robot_id`、本次会话内的 `request_id`。
- `/measure` 和 `/clear` 额外包含 `position={x,y}` 与 `channel`；坐标必须有限且绝对值不超过 2000000 米，频道为 `1..20` 整数。
- 请求为无 BOM 的 UTF-8 JSON，`Content-Type` 为 `application/json; charset=utf-8`，无未知字段、重复键、NaN 或无穷值。
- 所有完整 JSON 响应都检查 `accepted`、`real_timestamp_ms`、`virtual_time_s`；`accepted=false` 时动作不生效且 `virtual_time_s=0`。
- 检测结果只接受 `no_signal`、`near`、`direction`；仅 `direction` 读取 `[0,360)` 内的 `svd_deg`。
- 清除结果只接受 `success`、`no_target_in_range`；主动退出结果只接受 `user_exit`。
- 已接受、传输结果不确定，或收到 HTTP 200 但响应结构异常的 request_id，会在客户端绑定到原路径和原正文，禁止改动后复用。
- 新动作并发会在本地拒绝，不会排队后发送。

## 本地检查

在 `solution/` 下运行：

```powershell
python -B -m unittest discover -s tests/sim -t . -v
python -B -m unittest discover -s tests -t . -v
```

这些检查使用内存规则模型和本机临时回环服务器，不需要、也不会访问官方模拟器。

## 下一阶段的演练测试

以下命令仅在人工打开模拟器、选择正确的 Q3 或 Q4 演练测试，并看到机器狗接口就绪后执行：

```powershell
python src/sim/cli.py --problem 3 --robot-id "参赛队号" --confirm-ready
```

默认只执行三动作 smoke，并在 `output/sim/` 新建逐动作 JSONL。未提供 `--confirm-ready` 时，程序在创建客户端前终止，不发送任何请求。

完整 Q3/Q4 原型会产生较多动作，必须额外写明：

```powershell
python src/sim/cli.py --problem 3 --mode policy --robot-id "参赛队号" --q2-version new --max-refinements 5 --fim-cpu-time-limit-s 10 --joint-batch-mode guaranteed --failed-clear-remeasure-mode gated --rolling-time-mode scenario --rolling-risk-metric cvar --rolling-cpu-time-limit-s 3 --confirm-ready --confirm-policy
python src/sim/cli.py --problem 4 --mode policy --robot-id "参赛队号" --q2-version new --max-refinements 2 --q4-scan-mode triangular25 --failed-clear-remeasure-mode gated --rolling-time-mode scenario --rolling-risk-metric cvar --rolling-cpu-time-limit-s 3 --q4-long-clear-tail-mode adaptive --multi-source-route-mode off --confirm-ready --confirm-policy
```

`--fim-cpu-time-limit-s 10` 是每次 Q2 连续 FIM 规划允许的真实 CPU 墙钟上限，不是机器狗虚拟动作时间。Q3 默认关闭近优域绘图计算，因此该时限只用于产生实际细化测点。Q4 当前不调用全向 Q2 单点回退，保留这一参数仅为构造接口兼容。

`--q2-version` 可取 `new/legacy`，默认 `new`。它在策略启动前统一选择 Q2 源区域几何，Q3/Q4 的实际观测更新与 Q3 的滚动测后分支都会沿用同一版本；切换版本后应重新开始测试，不应复用进行中的策略状态。

Q4 的 `--max-refinements 2` 表示每源最多两个完整定向探测组，不是两个单独测点；单组收到 `no_signal` 后会在剩余认证点与安全清除之间重新滚动选择。`--q4-scan-mode triangular25` 是当前 25 点默认扫描，`triangular37` 与 `grid121` 只用于离线或人工回归比较。`--failed-clear-remeasure-mode gated` 启用失败清除点原地补测；`--rolling-time-mode scenario` 在 Q4 中映射为方向探测组有限场景滚动，而不是调用 Q3 的全向判断。

`--q4-long-clear-tail-mode adaptive` 在同源连续 8 次清除失败后最多开放一次收益门控的移动方向探测，默认启用。Q4 的多源路线只支持 `off/insertion_2opt`；8 场景配对虽降低均值但有 2 场退化，因此当前在线建议显式保持 `--multi-source-route-mode off`。只有人工另行决定复测路线时才改为 `insertion_2opt`，Q4 不接受 `beam_cached`。

`--rolling-cpu-time-limit-s 3` 是每次 Q3/Q4 有限场景评价的额外真实墙钟软截止。默认使用 `cvar`；超时并不发送异常动作，而是使用截止前最佳完整候选或直接清除。Q4 的失败点原地补测单独使用期望值门控，因为该动作没有移动成本，且 `no_signal` 分支仍保留原安全清除路线。

Q3/Q4 每次在线运行结束后，控制台会输出 `平均用时`，计算为总虚拟时间除以清除成功的信号源数；若没有清除成功的信号源，则明确显示无法计算，不进行除零。

正式测试各有次数限制。必须先由人工按 `tests/sim/verify_manual.md` 完成演练核对；本程序不会操作模拟器界面，也不能判断当前选中的是演练还是正式测试。

## 失败处理

- 如果收到 HTTP 或 `accepted=false`，保存 JSONL 并停止，不自行生成新动作。
- 如果同一动作在保持原 request_id 和原正文重试后仍没有完整响应，该动作是否已执行无法确定；程序保存错误并停止，禁止换 request_id 猜测重发。
- 倒计时、测试结束或接口未开放时连接失败属于协议允许的情况，应先核对模拟器界面。
- 运行日志不得覆盖已有文件。若默认秒级时间戳发生重名，显式使用 `--log` 指定新文件名。
