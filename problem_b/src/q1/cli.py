"""Problem B, Q1: measured bearings -> polygon, diameter and circle test."""

import argparse
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from q1.bearing_plot import plot_bearings, validate_inputs
    from q1.geometry import localize
else:
    from .bearing_plot import plot_bearings, validate_inputs
    from .geometry import localize

DEMO_POINTS = [(-600, -300), (850, -250), (-200, 1000)]
DEMO_BEARINGS = [35.89, 139.44, 300.56]
DEMO_SOURCE = (220, 280)  # Optional reference marker; never used by the solver.


def prompt_scene():
    print("B题问题1：交会定位、区域直径与直径圆覆盖判断")
    print("输入已经取得的示向度；正东 0°、正北 90°，角度范围 [0, 360)。")
    print("输入 q 退出。")

    def ask(prompt):
        answer = input(prompt).strip()
        if answer.lower() in ("q", "quit", "exit"):
            raise KeyboardInterrupt
        return answer

    while True:
        try:
            count = int(ask("检测点数量："))
            if count < 1:
                raise ValueError
            break
        except ValueError:
            print("请输入正整数。")
    points, bearings = [], []
    for i in range(count):
        while True:
            try:
                values = ask(f"S{i+1} 的 x y 示向度（空格分隔）：").replace(",", " ").replace("，", " ").split()
                if len(values) != 3:
                    raise ValueError("请依次输入 x、y、示向度三个数。")
                x, y, bearing = map(float, values)
                validate_inputs([(x, y)], [bearing])
                points.append((x, y))
                bearings.append(bearing)
                break
            except ValueError as error:
                print(f"输入有误：{error}")
    while True:
        values = ask("参考源 G 的 x y（可选，仅画图；直接回车不显示）：").replace(",", " ").replace("，", " ").split()
        try:
            source = None if not values else tuple(map(float, values))
            validate_inputs(points, bearings, source)
            return points, bearings, source
        except ValueError as error:
            print(f"输入有误：{error}")


def _display_bounds(points):
    extent = max(2100.0, *(max(abs(x), abs(y))*1.15 for x, y in points))
    return [-extent, -extent, extent, extent]


def analyze_q1(points, bearings, error_deg=1.0):
    """Return a JSON-serializable Q1 analysis using no source ground truth."""
    points, bearings, _ = validate_inputs(points, bearings)
    if not math.isfinite(error_deg) or not 0 < error_deg < 90:
        raise ValueError("示向度误差界须在 (0, 90) 度内。")
    observations = [dict(position=list(point), status="direction", bearing_deg=bearing)
                    for point, bearing in zip(points, bearings)]
    bounds = _display_bounds(points)
    region = localize(observations, bounds, error_deg=error_deg)
    progress = []
    for count in range(1, len(observations)+1):
        partial = localize(observations[:count], bounds, error_deg=error_deg)
        progress.append(dict(observation_count=count,
                             status=partial["status"],
                             vertex_count=len(partial["vertices"]),
                             diameter=partial["diameter"],
                             minimum_enclosing_radius=(partial["minimum_enclosing_circle"]["radius"]
                                                       if partial["minimum_enclosing_circle"] else None)))
    return dict(inputs=dict(detector_points=points, bearings_deg=bearings,
                            error_deg=error_deg),
                bounds=bounds, region=region, progress=progress)


def _print_result(analysis):
    region = analysis["region"]
    names = {"bounded": "有界", "unbounded": "无界", "empty": "空集"}
    print(f"\n定位区域：{names[region['status']]}")
    if region["status"] != "bounded":
        print("当前观测不能得到有限多边形直径。")
        return
    print(f"顶点数：{len(region['vertices'])}")
    for index, point in enumerate(region["vertices"], 1):
        print(f"V{index} = ({point[0]:.9f}, {point[1]:.9f})")
    p, q = region["diameter_pair"]
    circle = region["diameter_circle"]
    enclosing = region["minimum_enclosing_circle"]
    print(f"区域直径：{region['diameter']:.9f} m")
    print(f"直径端点：({p[0]:.9f}, {p[1]:.9f}) -- ({q[0]:.9f}, {q[1]:.9f})")
    print(f"直径圆：圆心 ({circle['center'][0]:.9f}, {circle['center'][1]:.9f})，半径 {circle['radius']:.9f} m")
    print("直径圆能否覆盖定位区域：" + ("能" if circle["covers"] else "不能"))
    if not circle["covers"]:
        print(f"最大超出：{circle['excess']:.9f} m")
    print(f"补充：最小包围圆半径 {enclosing['radius']:.9f} m")
    print("\n逐次加入观测：")
    print("观测数  状态    顶点数  直径/m")
    for item in analysis["progress"]:
        diameter = "—" if item["diameter"] is None else f"{item['diameter']:.6f}"
        print(f"{item['observation_count']:>6}  {names[item['status']]:<6}  "
              f"{item['vertex_count']:>6}  {diameter}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="B题问题1：由检测点与实测示向度求定位区域、直径及直径圆覆盖结论。")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--point", nargs=3, type=float, action="append",
                       metavar=("X", "Y", "BEARING"), help="检测点及示向度，可重复")
    group.add_argument("--demo", action="store_true", help="使用内置三测点示例")
    parser.add_argument("--error-deg", type=float, default=1.0,
                        help="示向度误差半宽，默认 1.0；可用 1.005 做通信舍入敏感性检查")
    parser.add_argument("--source", nargs=2, type=float, metavar=("X", "Y"),
                        help="可选参考源，只用于画图和人工核验")
    parser.add_argument("--output", help="保存 Q1 图为 .png 或 .svg")
    parser.add_argument("--result-json", help="保存完整数值结果 JSON")
    parser.add_argument("--no-show", action="store_true",
                        help="不打开桌面窗口；须同时指定 --output")
    args = parser.parse_args(argv)
    if args.no_show and not args.output:
        parser.error("--no-show 需要 --output 指定输出图片。")
    try:
        if args.demo:
            points, bearings, source = DEMO_POINTS, DEMO_BEARINGS, args.source or DEMO_SOURCE
        elif args.point:
            points = [tuple(p[:2]) for p in args.point]
            bearings = [p[2] for p in args.point]
            source = args.source
        else:
            points, bearings, source = prompt_scene()
            if args.source is not None:
                source = args.source
        validate_inputs(points, bearings, source)
        analysis = analyze_q1(points, bearings, args.error_deg)
        _print_result(analysis)
        plot_bearings(points, bearings, source, region=analysis["region"],
                      error_deg=args.error_deg, show=not args.no_show,
                      output_path=args.output)
        if args.output:
            print(f"已保存图形：{args.output}")
        if args.result_json:
            path = Path(args.result_json)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"已保存结果：{path}")
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\n已退出。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
