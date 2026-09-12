"""Command-line entry point for a manually prepared official simulator test."""

import argparse
from datetime import datetime
from pathlib import Path
import sys

if __package__ in (None, ""):
    code_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(code_root))

from q3.batch_policy import Q3BatchPolicy
from q3.coverage import SCAN_LAYOUTS
from q4.policy import Q4Policy
from sim.client import HttpRobotClient
from sim.errors import SimulatorError
from sim.live_runner import run_live_policy
from sim.smoke import SmokePolicy


def _default_log(problem):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"output/sim/q{problem}_{stamp}.jsonl"


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
    parser.add_argument("--max-refinements", type=int, default=2)
    parser.add_argument(
        "--fim-cpu-time-limit-s", type=float, default=6.0,
        help="每次Q2连续FIM规划允许的真实墙钟秒数",
    )
    parser.add_argument(
        "--scan-layout", choices=sorted(SCAN_LAYOUTS), default=None,
        help=("Q3 扫描停点布局（仅 --problem 3 生效；缺省跟随 Q3Policy "
              "当前默认值）"),
    )
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
    if args.max_refinements < 0:
        parser.error("--max-refinements 不能为负数。")
    if args.fim_cpu_time_limit_s <= 0:
        parser.error("--fim-cpu-time-limit-s 必须为正数。")
    if args.mode == "policy" and not args.confirm_policy:
        parser.error("未发送任何请求：policy 模式还必须添加 --confirm-policy。")

    if args.mode == "smoke":
        policy = SmokePolicy()
        max_actions = args.max_actions or 10
    elif args.problem == 3:
        policy_kwargs = dict(
            max_refinements=args.max_refinements,
            fim_cpu_time_limit_s=args.fim_cpu_time_limit_s,
        )
        if args.scan_layout is not None:
            policy_kwargs["scan_layout"] = args.scan_layout
        # 2026-09-12 夜间晋级：Q3 默认策略为"批量解耦"（B2，TSP 清除顺序），
        # simlite 300 局确认门1 全过（总虚拟时间 -29%、fallback→0）；
        # 交错流程可用 Q3Policy 显式选择。
        policy = Q3BatchPolicy(**policy_kwargs)
        # 2026-09-12 演练实证：14-16 源局 resolve（含 fallback）动作数可超 1000，
        # 默认 8000 保险（约 1.6MB 日志，远低于 2MB 上限；现实耗时约数分钟）。
        max_actions = args.max_actions or 8000
    else:
        policy = Q4Policy(
            max_refinements=args.max_refinements,
            fim_cpu_time_limit_s=args.fim_cpu_time_limit_s,
        )
        max_actions = args.max_actions or 4000
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
    except (SimulatorError, OSError, RuntimeError, ValueError) as error:
        print(f"现场运行停止：{error}", file=sys.stderr)
        print(f"若日志已创建，请保留并人工核对：{log_path}", file=sys.stderr)
        return 2
    print(f"运行结束：{summary.exit_reason}")
    print(f"动作数：{len(summary.actions)}")
    print(f"虚拟时间：{summary.virtual_time_s:.6f} s")
    print(f"日志：{log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
