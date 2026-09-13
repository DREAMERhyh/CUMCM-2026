# 官方模拟器接口人工验证清单

本清单由队员执行。AI 完成本地测试不等于官方模拟器验证，也不得据此修改 Q1–Q4 状态。

## 一 本地门禁

在 `solution/` 下执行：

```powershell
python -B -m unittest discover -s tests/sim -t . -v
python -B -m unittest discover -s tests -t . -v
```

确认所有测试通过。再执行下列命令，确认程序提示缺少 `--confirm-ready` 并退出，且没有创建现场日志、没有网络请求：

```powershell
python src/sim/cli.py --problem 3 --robot-id "仅作本地检查"
```

## 二 Q3 演练烟雾测试

1. 人工运行官方模拟器并联网登录。
2. 选择“问题3演练测试”，记录测试案例编码**WA6Q-XRC2-KVMP-2KGF**，等待界面明确显示机器狗接口已经就绪。
3. 确认端口；默认地址为 `http://127.0.0.1:2026`。
4. 执行：

```powershell
python src/sim/cli.py --problem 3 --robot-id "202601101010" --confirm-ready
```

5. 期望终端显示主动退出、动作数 3、虚拟时间约 5 秒，并给出一个新 JSONL 路径。
6. 打开 JSONL，逐行确认动作依次为 `enter`、`measure`、`exit`；请求路径/字段、HTTP状态、响应和现实时间均有记录。
7. 在模拟器“指令与反馈”区域逐条对照，确认三条请求的 request_id、位置 `(0,0)`、频道 `1` 和响应一致。
8. 记录模拟器显示的结束原因、案例编码和异常信息。若任一项不一致，不运行完整策略。

## 三 Q4 演练烟雾测试

重新开始“问题4演练测试”，重复第二节，将命令中的 `--problem 3` 改为 `--problem 4`。两次演练必须分别生成不同的 JSONL 文件。

## 四 完整策略演练前检查

完整策略仍是待人工验证的离线原型。在至少一次 smoke 完全一致后，队员先检查：

- 当前界面确为演练测试，不是正式测试。
- `max_actions` 足以保留最后一次安全 `/exit`，且动作数量不会造成异常高频循环或过大的模拟器加密日志。
- Q3/Q4 策略、终止判据和清除逻辑已经由队员审核。
- 输出目录有足够空间，目标 JSONL 文件不存在。

确认后才能使用 `--mode policy --confirm-policy`。任何 HTTP错误、`accepted=false`、连接中断、协议校验错误或本地策略异常都应立即停止，保留本地 JSONL 和模拟器日志，不要换 request_id 盲目重发不确定动作。

Q3 当前与离线演练对齐的完整策略命令为：

```powershell
python src/sim/cli.py --problem 3 --mode policy --robot-id "202601101010" --q2-version new --max-refinements 5 --fim-cpu-time-limit-s 10 --joint-batch-mode guaranteed --failed-clear-remeasure-mode gated --rolling-time-mode scenario --rolling-risk-metric cvar --rolling-cpu-time-limit-s 3 --confirm-ready --confirm-policy
```

Q4 当前与离线演练对齐、保持多源路线关闭的命令为：

```powershell
python src/sim/cli.py --problem 4 --mode policy --robot-id "202601101010" --q2-version new --max-refinements 2 --q4-scan-mode triangular25 --q4-q2-candidate-mode hybrid_pareto --failed-clear-remeasure-mode gated --rolling-time-mode scenario --rolling-risk-metric cvar --rolling-cpu-time-limit-s 3 --q4-long-clear-tail-mode adaptive --multi-source-route-mode off --confirm-ready --confirm-policy
```

其中 `--q2-version new` 是默认新版；需要回归旧版时只能在开始新测试前改成 `legacy`。Q3 的 10 s 是每次 Q2/FIM 规划真实墙钟上限；Q4 候选连续 FIM 默认子截止 0.75 s，候选生成与首次方向评价共享 3 s 软预算。Q4 默认开启 `hybrid_pareto` 候选接入与长尾救援，多源路线因尚无稳定逐场收益而保持关闭；如要测试 `insertion_2opt`，必须新开一次演练并重新核对，不能在运行中切换。运行结束后还应核对 `平均用时 = 虚拟时间 / 清除成功数`；无清除成功源时应显示无法计算。运行前检查日志目标不存在，并确认界面与 `--problem` 对应。

## 五 正式测试门禁

正式测试须由队员另行决定。只有 Q3/Q4 策略本身完成审查、两类演练结果与日志均核对通过、动作量和结束行为符合预期后，才考虑正式测试。接口烟雾测试通过本身不能证明定位与清除策略正确。
