"""Command-line entry point for B-Q2."""

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.models import BearingObservation
from q2.planner import Q2Config, plan_second_point


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description="B-Q2 第二检测点规划与可视化")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--first", nargs=3, type=float,
                        metavar=("X", "Y", "BEARING_DEG"))
    parser.add_argument("--channel", type=int, default=1)
    parser.add_argument("--error-deg", type=float, default=1.005)
    parser.add_argument("--output")
    parser.add_argument("--result-json")
    parser.add_argument("--no-show", action="store_true")
    args = parser.parse_args(argv)
    if args.demo:
        args.first = (-600.0, -300.0, 35.89)
    if args.first is None:
        parser.error("请提供 --first X Y BEARING_DEG，或使用 --demo。")
    if args.no_show and not args.output:
        parser.error("--no-show 必须同时指定 --output。")

    x, y, bearing = args.first
    observation = BearingObservation((x, y), args.channel, "direction", bearing)
    plan = plan_second_point(observation,
                             config=Q2Config(error_deg=args.error_deg))
    selected = plan["selected"]
    print(f"第二检测点：({selected['point'][0]:.3f}, {selected['point'][1]:.3f})")
    print(f"保证接收：{'是' if selected['guaranteed_reception'] else '否'}")
    print(f"最坏后验包围半径：{selected['worst_case_radius_m']:.3f} m")
    print(f"预计动作时间：{selected['action_time_s']:.3f} s")
    print(f"候选数：{plan['candidate_count']}，保证接收候选：{plan['guaranteed_candidate_count']}")

    if args.result_json:
        path = Path(args.result_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_jsonable(plan), ensure_ascii=False,
                                   allow_nan=False, indent=2), encoding="utf-8")
    if args.output or not args.no_show:
        if args.no_show:
            import matplotlib
            matplotlib.use("Agg")
        from q2.plot import plot_plan
        plot_plan(plan, output=args.output, show=not args.no_show)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

