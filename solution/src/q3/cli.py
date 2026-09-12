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
    parser.add_argument("--max-actions", type=int, default=1000)
    parser.add_argument("--max-refinements", type=int, default=5)
    parser.add_argument("--fim-cpu-time-limit-s", type=float, default=10.0)
    parser.add_argument(
        "--q2-version", choices=("new", "legacy"), default="new",
        help="Q2源区域算法版本",
    )
    parser.add_argument(
        "--joint-batch-mode",
        choices=("off", "guaranteed", "all_active"),
        default="guaranteed",
        help="联合批测：关闭、保证接收筛选或全部活动频道",
    )
    parser.add_argument(
        "--failed-clear-remeasure-mode",
        choices=("off", "gated"), default="gated",
        help="保底清除失败后的复测：关闭或条件判断",
    )
    parser.add_argument(
        "--rolling-time-mode",
        choices=("off", "scenario"), default="scenario",
        help="总虚拟时间滚动评价：关闭或有限场景推演",
    )
    parser.add_argument("--rolling-cpu-time-limit-s", type=float, default=3.0)
    parser.add_argument(
        "--rolling-risk-metric",
        choices=("p90", "cvar", "worst", "mean"), default="cvar",
    )
    parser.add_argument(
        "--multi-source-route-mode",
        choices=("off", "insertion_2opt", "beam_cached"), default="off",
        help="多源顺序：当前策略、插入加2-opt或缓存束搜索",
    )
    parser.add_argument("--route-cpu-time-limit-s", type=float, default=0.25)
    parser.add_argument("--cache-capacity", type=int, default=4096)
    parser.add_argument("--beam-width", type=int, default=1)
    parser.add_argument("--beam-max-expansions", type=int, default=512)
    args = parser.parse_args(argv)
    if args.max_actions < 1:
        parser.error("--max-actions 必须为正整数。")
    if args.max_refinements < 0:
        parser.error("--max-refinements 不能为负数。")
    if args.fim_cpu_time_limit_s <= 0:
        parser.error("--fim-cpu-time-limit-s 必须为正数。")
    if args.rolling_cpu_time_limit_s <= 0:
        parser.error("--rolling-cpu-time-limit-s 必须为正数。")
    if args.route_cpu_time_limit_s <= 0:
        parser.error("--route-cpu-time-limit-s 必须为正数。")
    if (args.cache_capacity < 1 or args.beam_width < 1
            or args.beam_max_expansions < 1):
        parser.error("缓存容量、束宽和束搜索扩展上限必须为正数。")
    client = FakeSimulator([FakeSource(3, (1200.0, 100.0), 1000.0)])
    policy = Q3Policy(
        max_refinements=args.max_refinements,
        fim_cpu_time_limit_s=args.fim_cpu_time_limit_s,
        q2_version=args.q2_version,
        joint_batch_mode=args.joint_batch_mode,
        failed_clear_remeasure_mode=args.failed_clear_remeasure_mode,
        rolling_time_mode=args.rolling_time_mode,
        rolling_cpu_time_limit_s=args.rolling_cpu_time_limit_s,
        rolling_risk_metric=args.rolling_risk_metric,
        multi_source_route_mode=args.multi_source_route_mode,
        route_cpu_time_limit_s=args.route_cpu_time_limit_s,
        cache_capacity=args.cache_capacity,
        beam_width=args.beam_width,
        beam_max_expansions=args.beam_max_expansions,
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
    print(f"Q2版本：{args.q2_version}")
    print(f"联合批测模式：{args.joint_batch_mode}")
    print(f"清除失败复测模式：{args.failed_clear_remeasure_mode}")
    print(f"总时间滚动模式：{args.rolling_time_mode}")
    print(f"滚动风险口径：{args.rolling_risk_metric}")
    print(f"多源路线模式：{args.multi_source_route_mode}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
