"""Offline-only Q3 demonstration.  It never connects to the official API."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    code_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(code_root))

from q3.coverage import SCAN_LAYOUTS
from q3.policy import Q3Policy
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource


def main(argv=None):
    parser = argparse.ArgumentParser(description="B-Q3 离线规则演示（非官方模拟器）")
    parser.add_argument("--output", default="output/q3_offline/demo.json")
    parser.add_argument("--max-actions", type=int, default=1000)
    parser.add_argument("--max-refinements", type=int, default=2)
    parser.add_argument("--fim-cpu-time-limit-s", type=float, default=6.0)
    parser.add_argument("--scan-layout", choices=sorted(SCAN_LAYOUTS),
                        default="ring7",
                        help="扫描停点布局（默认 ring7，保持线上行为）")
    args = parser.parse_args(argv)
    if args.max_actions < 1:
        parser.error("--max-actions 必须为正整数。")
    if args.max_refinements < 0:
        parser.error("--max-refinements 不能为负数。")
    if args.fim_cpu_time_limit_s <= 0:
        parser.error("--fim-cpu-time-limit-s 必须为正数。")
    client = FakeSimulator([FakeSource(3, (1200.0, 100.0), 1000.0)])
    policy = Q3Policy(
        max_refinements=args.max_refinements,
        fim_cpu_time_limit_s=args.fim_cpu_time_limit_s,
        scan_layout=args.scan_layout,
    )
    summary = run_policy(policy, client, max_actions=args.max_actions)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.as_dict(), ensure_ascii=False,
                               indent=2), encoding="utf-8")
    print("这是本地规则模拟，不是官方测试。")
    print(f"动作数：{len(summary.actions)}")
    print(f"清除频道：{summary.cleared_channels}")
    print(f"离线虚拟时间：{summary.virtual_time_s:.3f} s")
    print(f"细化上限：{args.max_refinements}；单次FIM墙钟上限：{args.fim_cpu_time_limit_s:.3f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
