"""Offline-only Q3 demonstration.  It never connects to the official API."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    code_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(code_root))

from q3.policy import Q3Policy
from runtime.runner import run_policy
from sim.fake import FakeSimulator, FakeSource


def main(argv=None):
    parser = argparse.ArgumentParser(description="B-Q3 离线规则演示（非官方模拟器）")
    parser.add_argument("--output", default="output/q3_offline/demo.json")
    args = parser.parse_args(argv)
    client = FakeSimulator([FakeSource(3, (1200.0, 100.0), 1000.0)])
    summary = run_policy(Q3Policy(max_refinements=0), client,
                         max_actions=1000)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary.as_dict(), ensure_ascii=False,
                               indent=2), encoding="utf-8")
    print("这是本地规则模拟，不是官方测试。")
    print(f"动作数：{len(summary.actions)}")
    print(f"清除频道：{summary.cleared_channels}")
    print(f"离线虚拟时间：{summary.virtual_time_s:.3f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
