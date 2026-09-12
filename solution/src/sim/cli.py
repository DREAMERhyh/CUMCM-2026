"""Command-line entry point for a manually prepared official simulator test."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    code_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(code_root))

from q3.policy import Q3Policy
from q4.policy import Q4Policy
from sim.client import HttpRobotClient
from sim.errors import SimulatorError
from sim.live_runner import run_live_policy
from sim.smoke import SmokePolicy


def _default_log(problem):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"output/sim/q{problem}_{stamp}.jsonl"


def _count_successful_clears(log_path):
    with Path(log_path).open("r", encoding="utf-8") as stream:
        return sum(
            1
            for line in stream
            if json.loads(line).get("response", {}).get("clear_result") == "success"
        )


def _average_time_line(virtual_time_s, source_count):
    if source_count <= 0:
        return "平均用时：无法计算（未清除信号源）"
    return f"平均用时：{virtual_time_s/source_count:.6f} s/信号源"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B题 Q3/Q4 官方模拟器接口入口；必须先由人工启动所需测试。"
    )
    parser.add_argument("--problem", type=int, choices=(3, 4), required=True)
    parser.add_argument(
        "--mode", choices=("smoke", "policy"), default="smoke",
        help="smoke 只发送 enter/measure/exit；policy 运行当前 Q3/Q4 原型",
    )
    parser.add_argument("--robot-id", required=True, help="当前登录的参赛队号")
    parser.add_argument("--base-url", default="http://127.0.0.1:2026")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument("--retry-count", type=int, default=2)
    parser.add_argument("--retry-delay-s", type=float, default=0.2)
    parser.add_argument("--max-actions", type=int)
    parser.add_argument(
        "--max-refinements", type=int,
        help="每源细化上限；Q4按完整探测组计数；未指定时 Q3=5、Q4=2",
    )
    parser.add_argument(
        "--q4-scan-mode", choices=("triangular37", "grid121"),
        default="triangular37",
        help="Q4发现扫描网；Q3忽略该参数",
    )
    parser.add_argument(
        "--fim-cpu-time-limit-s", type=float,
        help="每次Q2连续FIM规划允许的真实墙钟秒数；未指定时Q3=10、Q4=6",
    )
    parser.add_argument(
        "--q2-version", choices=("new", "legacy"), default="new",
        help="Q3/Q4调用的Q2源区域算法版本；默认new",
    )
    parser.add_argument(
        "--joint-batch-mode",
        choices=("off", "guaranteed", "all_active"),
        default="guaranteed",
        help="Q3联合批测模式；Q4忽略该参数",
    )
    parser.add_argument(
        "--failed-clear-remeasure-mode",
        choices=("off", "gated"), default="gated",
        help="Q3/Q4清除失败原地复测模式",
    )
    parser.add_argument(
        "--rolling-time-mode",
        choices=("off", "scenario"), default="scenario",
        help="Q3总时间滚动；Q4映射为方向探测组滚动",
    )
    parser.add_argument(
        "--rolling-cpu-time-limit-s", type=float, default=3.0,
        help="每次Q3/Q4滚动评价的真实墙钟秒数",
    )
    parser.add_argument(
        "--rolling-risk-metric",
        choices=("p90", "cvar", "worst", "mean"), default="cvar",
        help="Q3/Q4有限场景风险汇总口径",
    )
    parser.add_argument(
        "--multi-source-route-mode",
        choices=("off", "insertion_2opt", "beam_cached"), default="off",
        help="Q3/Q4多源顺序优化；Q4仅支持off或insertion_2opt",
    )
    parser.add_argument(
        "--route-cpu-time-limit-s", type=float, default=0.25,
        help="Q3/Q4路线排序真实墙钟软截止",
    )
    parser.add_argument(
        "--q4-long-clear-tail-mode", choices=("off", "adaptive"),
        default="adaptive", help="Q4长清除尾救援与后验引导排序；Q3忽略",
    )
    parser.add_argument("--cache-capacity", type=int, default=4096)
    parser.add_argument("--beam-width", type=int, default=1)
    parser.add_argument("--beam-max-expansions", type=int, default=512)
    parser.add_argument("--exit-safety-margin-s", type=float, default=15.0)
    parser.add_argument("--log", help="新建的逐动作 JSONL 日志路径")
    parser.add_argument(
        "--confirm-ready",
        action="store_true",
        help="确认已在模拟器中选择正确测试并看到接口就绪",
    )
    parser.add_argument(
        "--confirm-policy",
        action="store_true",
        help="额外确认要运行尚未完成官方验收的 Q3/Q4 策略原型",
    )
    args = parser.parse_args(argv)
    if not args.confirm_ready:
        parser.error("未发送任何请求：请确认模拟器接口就绪后添加 --confirm-ready。")
    if args.max_refinements is not None and args.max_refinements < 0:
        parser.error("--max-refinements 不能为负数。")
    fim_cpu_time_limit_s = args.fim_cpu_time_limit_s
    if fim_cpu_time_limit_s is None:
        fim_cpu_time_limit_s = 10.0 if args.problem == 3 else 6.0
    if fim_cpu_time_limit_s <= 0:
        parser.error("--fim-cpu-time-limit-s 必须为正数。")
    if args.rolling_cpu_time_limit_s <= 0:
        parser.error("--rolling-cpu-time-limit-s 必须为正数。")
    if args.route_cpu_time_limit_s <= 0:
        parser.error("--route-cpu-time-limit-s 必须为正数。")
    if (args.cache_capacity < 1 or args.beam_width < 1
            or args.beam_max_expansions < 1):
        parser.error("缓存容量、束宽和束搜索扩展上限必须为正数。")
    if args.mode == "policy" and not args.confirm_policy:
        parser.error("未发送任何请求：policy 模式还必须添加 --confirm-policy。")
    if (args.problem == 4
            and args.multi_source_route_mode == "beam_cached"):
        parser.error("Q4当前只接入insertion_2opt，不支持beam_cached。")

    if args.mode == "smoke":
        policy = SmokePolicy()
        max_actions = args.max_actions or 10
    else:
        q3_refinements = (5 if args.max_refinements is None
                          else args.max_refinements)
        q4_refinements = (2 if args.max_refinements is None
                          else args.max_refinements)
        policy = (Q3Policy(
                      max_refinements=q3_refinements,
                      fim_cpu_time_limit_s=fim_cpu_time_limit_s,
                      q2_version=args.q2_version,
                      joint_batch_mode=args.joint_batch_mode,
                      failed_clear_remeasure_mode=(
                          args.failed_clear_remeasure_mode
                      ),
                      rolling_time_mode=args.rolling_time_mode,
                      rolling_cpu_time_limit_s=(
                          args.rolling_cpu_time_limit_s
                      ),
                      rolling_risk_metric=args.rolling_risk_metric,
                      multi_source_route_mode=(
                          args.multi_source_route_mode
                      ),
                      route_cpu_time_limit_s=args.route_cpu_time_limit_s,
                      cache_capacity=args.cache_capacity,
                      beam_width=args.beam_width,
                      beam_max_expansions=args.beam_max_expansions,
                  )
                  if args.problem == 3
                  else Q4Policy(
                      max_refinements=q4_refinements,
                      fim_cpu_time_limit_s=fim_cpu_time_limit_s,
                       scan_mode=args.q4_scan_mode,
                       q2_version=args.q2_version,
                       failed_clear_remeasure_mode=(
                           args.failed_clear_remeasure_mode
                       ),
                       directional_rolling_mode=args.rolling_time_mode,
                       directional_rolling_cpu_time_limit_s=(
                           args.rolling_cpu_time_limit_s
                       ),
                       directional_rolling_risk_metric=(
                           args.rolling_risk_metric
                       ),
                       long_clear_tail_mode=args.q4_long_clear_tail_mode,
                       multi_source_route_mode=args.multi_source_route_mode,
                       route_cpu_time_limit_s=args.route_cpu_time_limit_s,
                   ))
        max_actions = args.max_actions or (1000 if args.problem == 3 else 4000)
    log_path = args.log or _default_log(args.problem)
    try:
        client = HttpRobotClient(
            robot_id=args.robot_id,
            base_url=args.base_url,
            timeout_s=args.timeout_s,
            retry_count=args.retry_count,
            retry_delay_s=args.retry_delay_s,
        )
        summary = run_live_policy(
            policy,
            client,
            log_path=log_path,
            max_actions=max_actions,
            exit_safety_margin_s=args.exit_safety_margin_s,
        )
        successful_clears = _count_successful_clears(log_path)
    except (SimulatorError, OSError, RuntimeError, ValueError) as error:
        print(f"现场运行停止：{error}", file=sys.stderr)
        print(f"若日志已创建，请保留并人工核对：{log_path}", file=sys.stderr)
        return 2
    print(f"运行结束：{summary.exit_reason}")
    print(f"动作数：{len(summary.actions)}")
    print(f"清除成功数：{successful_clears}")
    print(f"虚拟时间：{summary.virtual_time_s:.6f} s")
    print(_average_time_line(summary.virtual_time_s, successful_clears))
    print(f"日志：{log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
