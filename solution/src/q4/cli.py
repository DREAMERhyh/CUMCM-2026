"""Offline-only Q4 demonstration.  It never connects to the official API."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    code_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(code_root))

from q4.policy import Q4Policy
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource


def main(argv=None):
    parser = argparse.ArgumentParser(description="B-Q4 离线规则演示（非官方模拟器）")
    parser.add_argument("--output", default="output/q4_offline/demo.json")
    parser.add_argument(
        "--scan-mode", choices=("triangular25", "triangular37", "grid121"),
        default="triangular25",
        help="Q4发现扫描网（25点三角网默认，37/121点回归可选）",
    )
    parser.add_argument(
        "--max-refinements", type=int, default=2,
        help="每源完整定向探测组上限",
    )
    parser.add_argument(
        "--failed-clear-remeasure-mode", choices=("off", "gated"),
        default="gated", help="清除失败后的Q4原地补测门控",
    )
    parser.add_argument(
        "--directional-rolling-mode", choices=("off", "scenario"),
        default="scenario", help="Q4方向探测组有限场景滚动决策",
    )
    parser.add_argument(
        "--directional-rolling-risk-metric",
        choices=("mean", "p90", "cvar", "worst"), default="cvar",
    )
    parser.add_argument(
        "--directional-rolling-cpu-time-limit-s", type=float, default=3.0,
    )
    parser.add_argument(
        "--long-clear-tail-mode", choices=("off", "adaptive"),
        default="adaptive",
    )
    parser.add_argument(
        "--clear-cover", choices=("probe_plan", "posterior_grid", "strip"),
        default="probe_plan",
        help="保底清除点列构造：probe_plan(B2蜂窝有界) / posterior_grid(27m网格) / strip(条带)",
    )
    parser.add_argument(
        "--use-optimal-stop", choices=("on", "off"), default=None,
        help="A3 最优停止；缺省跟随策略默认（开）",
    )
    parser.add_argument(
        "--tspn-clear", choices=("on", "off"), default=None,
        help="证书清除端点朝下一目标偏移；缺省跟随策略默认（开）",
    )
    args = parser.parse_args(argv)
    q4_kwargs = dict(
        max_refinements=args.max_refinements, scan_mode=args.scan_mode,
        failed_clear_remeasure_mode=args.failed_clear_remeasure_mode,
        directional_rolling_mode=args.directional_rolling_mode,
        directional_rolling_risk_metric=(
            args.directional_rolling_risk_metric
        ),
        directional_rolling_cpu_time_limit_s=(
            args.directional_rolling_cpu_time_limit_s
        ),
        long_clear_tail_mode=args.long_clear_tail_mode,
        clear_cover=args.clear_cover,
    )
    if args.use_optimal_stop == "off":
        q4_kwargs["use_optimal_stop"] = False
    if args.tspn_clear == "off":
        q4_kwargs["tspn_clear"] = False
    client = FakeSimulator([
        FakeSource(7, (1700.0, 0.0), 1000.0, direction_deg=0.0)
    ])
    summary = run_policy(Q4Policy(**q4_kwargs), client, max_actions=4000)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.as_dict(), ensure_ascii=False,
                               indent=2), encoding="utf-8")
    print("这是本地规则模拟，不是官方测试。")
    print(f"动作数：{len(summary.actions)}")
    print(f"清除频道：{summary.cleared_channels}")
    print(f"离线虚拟时间：{summary.virtual_time_s:.3f} s")
    print(f"扫描网：{args.scan_mode}")
    print(f"清除失败原地补测：{args.failed_clear_remeasure_mode}")
    print(f"方向探测组滚动：{args.directional_rolling_mode}")
    print(f"长清除尾优化：{args.long_clear_tail_mode}")
    print(f"保底清除构造：{args.clear_cover}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())