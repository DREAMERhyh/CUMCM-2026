"""一键对接官方模拟器：启动 Q3/Q4 策略演练，落盘摘要并对账虚拟时间。

用法（配合《docs/操作手册_演练对账.md》）：
    python run_drill.py --problem 3 --robot-id <参赛队号> --confirm-ready
    python run_drill.py --problem 3 --robot-id <参赛队号> --mode policy \
        --scan-layout pure_ring8 --confirm-ready --confirm-policy

本脚本只是 sim/cli.py 的安全包装：保留全部确认门禁（--confirm-ready /
--confirm-policy），运行结束后额外从逐动作 JSONL 中统计 cleared/absent、
用 common/time_model 重算各动作耗时拆分并与官方 virtual_time_s 对账，
并把摘要写入 output/sim/drill/ 下的人类可读 JSON。
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    code_root = Path(__file__).resolve().parent / "src"
    sys.path.insert(0, str(code_root))

from common.time_model import clear_cost, measure_cost
from q3.batch_policy import Q3BatchPolicy
from q3.coverage import SCAN_LAYOUTS
from q4.policy import Q4Policy
from sim.client import HttpRobotClient
from sim.errors import SimulatorError
from sim.live_runner import run_live_policy
from sim.smoke import SmokePolicy


def build_client(robot_id, *, base_url="http://127.0.0.1:2026",
                 timeout_s=5.0, retry_count=2, retry_delay_s=0.2):
    """构造串行回环 HTTP 客户端；测试可 patch 本工厂。"""
    return HttpRobotClient(
        robot_id=robot_id,
        base_url=base_url,
        timeout_s=timeout_s,
        retry_count=retry_count,
        retry_delay_s=retry_delay_s,
    )


def build_policy(problem, *, max_refinements=2, fim_cpu_time_limit_s=6.0,
                 scan_layout=None):
    """构造 Q3/Q4 策略；scan_layout 仅 Q3 生效（None 跟随策略默认值）。

    Q3 默认使用批量解耦策略（B2 夜间晋级，TSP 清除顺序）；交错流程保留在
    ``q3.policy.Q3Policy``。
    """
    if problem == 3:
        kwargs = dict(max_refinements=max_refinements,
                      fim_cpu_time_limit_s=fim_cpu_time_limit_s)
        if scan_layout is not None:
            kwargs["scan_layout"] = scan_layout
        return Q3BatchPolicy(**kwargs)
    return Q4Policy(max_refinements=max_refinements,
                    fim_cpu_time_limit_s=fim_cpu_time_limit_s)


def recon_from_log(log_path):
    """逐动作重算耗时拆分并与官方虚拟时间对账（时间全部复用 time_model）。"""
    movement = switching = measurement = optical = laser = 0.0
    clear_channels = []
    previous_position = (0.0, 0.0)
    previous_channel = 1
    official_total = None
    measure_count = clear_count = direction_count = 0
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        action = record["action"]
        response = record.get("response") or {}
        if action["kind"] == "measure":
            position = (action["position"]["x"], action["position"]["y"])
            channel = action["channel"]
            timing = measure_cost(previous_position, position,
                                  previous_channel, channel)
            movement += timing.movement_s
            switching += timing.switching_s
            measurement += timing.measurement_s
            previous_position = position
            previous_channel = channel
            measure_count += 1
            if response.get("measure_result") == "direction":
                direction_count += 1
            if response:
                official_total = response.get("virtual_time_s",
                                              official_total)
        elif action["kind"] == "clear":
            position = (action["position"]["x"], action["position"]["y"])
            timing = clear_cost(previous_position, position,
                                response.get("clear_result") == "success")
            movement += timing.movement_s
            optical += timing.optical_s
            laser += timing.laser_s
            previous_position = position
            clear_count += 1
            if response.get("clear_result") == "success":
                clear_channels.append(action["channel"])
            if response:
                official_total = response.get("virtual_time_s",
                                              official_total)
    recon_total = movement + switching + measurement + optical + laser
    difference = None
    if official_total is not None:
        difference = official_total - recon_total
    return {
        "official_virtual_time_s": official_total,
        "recon_total_s": recon_total,
        "difference_s": difference,
        # 官方按微秒整数累计、响应保留 6 位小数；浮点重算与官方各动作
        # 舍入差最多数微秒量级，阈值取 1e-3s 以吸收累计舍入（与 simlite
        # 对账口径一致）；秒级差异才视为真实不一致。
        "matches": (difference is not None and abs(difference) <= 1e-3),
        "movement_s": movement,
        "switching_s": switching,
        "measurement_s": measurement,
        "optical_s": optical,
        "laser_s": laser,
        "recon_measure_action_s": switching + measurement,
        "recon_clear_action_s": optical + laser,
        "measure_count": measure_count,
        "clear_count": clear_count,
        "direction_count": direction_count,
        "clear_success_channels": clear_channels,
    }


def _default_log(problem):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"output/sim/q{problem}_{stamp}.jsonl"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B题 Q3/Q4 官方模拟器演练一键启动与对账。",
    )
    parser.add_argument("--problem", type=int, choices=(3, 4), required=True)
    parser.add_argument("--robot-id", default=None,
                        help="当前登录的参赛队号（也可用环境变量 ROBOT_ID）")
    parser.add_argument("--mode", choices=("smoke", "policy"), default="policy")
    parser.add_argument("--scan-layout", choices=sorted(SCAN_LAYOUTS),
                        default=None,
                        help="Q3 扫描驻留点布局（缺省跟随 Q3Policy 当前默认）")
    parser.add_argument("--base-url", default="http://127.0.0.1:2026")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument("--retry-count", type=int, default=2)
    parser.add_argument("--retry-delay-s", type=float, default=0.2)
    parser.add_argument("--max-actions", type=int)
    parser.add_argument("--max-refinements", type=int, default=2)
    parser.add_argument("--fim-cpu-time-limit-s", type=float, default=6.0)
    parser.add_argument("--exit-safety-margin-s", type=float, default=15.0)
    parser.add_argument("--log", help="逐动作 JSONL 路径（默认 output/sim/）")
    parser.add_argument("--summary", help="摘要 JSON 路径（默认 output/sim/drill/）")
    parser.add_argument("--confirm-ready", action="store_true",
                        help="确认已在模拟器中启动测试并看到接口就绪")
    parser.add_argument("--confirm-policy", action="store_true",
                        help="policy 模式额外确认运行 Q3/Q4 策略原型")
    args = parser.parse_args(argv)
    robot_id = args.robot_id or os.environ.get("ROBOT_ID")
    if not robot_id:
        parser.error("需要 --robot-id <参赛队号>（或设置环境变量 ROBOT_ID）。")
    if not args.confirm_ready:
        parser.error("未发送任何请求：请确认模拟器接口就绪后添加 --confirm-ready。")
    if args.max_refinements < 0:
        parser.error("--max-refinements 不能为负数。")
    if args.fim_cpu_time_limit_s <= 0:
        parser.error("--fim-cpu-time-limit-s 必须为正数。")
    if args.mode == "policy" and not args.confirm_policy:
        parser.error("policy 模式还必须添加 --confirm-policy。")

    if args.mode == "smoke":
        policy = SmokePolicy()
        max_actions = args.max_actions or 10
    else:
        policy = build_policy(args.problem, max_refinements=args.max_refinements,
                              fim_cpu_time_limit_s=args.fim_cpu_time_limit_s,
                              scan_layout=args.scan_layout)
        # 演练实证：14-16 源局 resolve（含 fallback）可超 1000 动作。
        max_actions = args.max_actions or (8000 if args.problem == 3 else 4000)

    log_path = args.log or _default_log(args.problem)
    try:
        client = build_client(robot_id, base_url=args.base_url,
                              timeout_s=args.timeout_s,
                              retry_count=args.retry_count,
                              retry_delay_s=args.retry_delay_s)
        summary = run_live_policy(
            policy, client, log_path=log_path, max_actions=max_actions,
            exit_safety_margin_s=args.exit_safety_margin_s,
        )
    except (SimulatorError, OSError, RuntimeError, ValueError) as error:
        print(f"现场运行停止：{error}", file=sys.stderr)
        print(f"若日志已创建，请保留并人工核对：{log_path}", file=sys.stderr)
        return 2

    recon = recon_from_log(log_path)
    recon["clear_success_count"] = len(recon["clear_success_channels"])
    cleared_count = len(summary.cleared_channels)
    absent_count = len(summary.absent_channels)
    average_clear_time_s = (
        summary.virtual_time_s / cleared_count if cleared_count else None
    )
    payload = {
        "problem": args.problem,
        "robot_id": robot_id,
        "mode": args.mode,
        "scan_layout": getattr(policy, "scan_layout", None),
        "log_path": str(Path(log_path).resolve()),
        "exit_reason": summary.exit_reason,
        "action_count": len(summary.actions),
        "cleared_channels": summary.cleared_channels,
        "cleared_count": cleared_count,
        "absent_channels": summary.absent_channels,
        "absent_count": absent_count,
        "virtual_time_s": summary.virtual_time_s,
        "average_clear_time_s": average_clear_time_s,
        "recon": recon,
        "time_accounting_matches_official": recon.get("matches"),
    }
    summary_path = args.summary or (
        str(Path(log_path).with_suffix("")) + "_summary.json"
    )
    if str(summary_path) != "-":
        path = Path(summary_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        print(f"摘要：{path}")
    print("=" * 64)
    print(f"退出原因：{payload['exit_reason']}")
    print(f"动作数：{payload['action_count']}（检测 {recon['measure_count']}、"
          f"清除 {recon['clear_count']}）")
    print(f"清除频道：{payload['cleared_channels']}（{cleared_count} 个）")
    print(f"缺席判定频道：{payload['absent_channels']}（{absent_count} 个）")
    if average_clear_time_s is not None:
        print(f"虚拟时间：{summary.virtual_time_s:.3f} s；"
              f"平均定位清除时间：{average_clear_time_s:.3f} s/源")
    else:
        print(f"虚拟时间：{summary.virtual_time_s:.3f} s（无成功清除）")
    if recon["matches"]:
        print(f"时间对账：一致（重算 {recon['recon_total_s']:.6f} s = 官方 "
              f"{recon['official_virtual_time_s']:.6f} s）")
    else:
        print(f"时间对账：不一致！重算 {recon['recon_total_s']:.6f} s vs 官方 "
              f"{recon['official_virtual_time_s']} s，差 "
              f"{recon['difference_s']} s", file=sys.stderr)
    print(f"日志：{log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())