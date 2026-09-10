"""Command-line input -> Python canvas. No calls to geometry/environment."""

import argparse
import sys

from bearing_plot import plot_bearings, validate_inputs

DEMO_POINTS = [(-600, -300), (850, -250), (-200, 1000)]
DEMO_BEARINGS = [35.89, 139.44, 300.56]  # supplied demonstration readings
DEMO_SOURCE = (220, 280)


def prompt_scene():
    print("B题：示向度可视化（仅绘图，不进行定位求解）")
    print("输入已经确定有效的观测；示向度取 [0, 360)，误差边界固定为 ±1°。")
    print("坐标单位为米，正东 0°，正北 90°。输入 q 退出。")

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
                points.append((x, y)); bearings.append(bearing)
                break
            except ValueError as error:
                print(f"输入有误：{error}")
    while True:
        values = ask("参考源 G 的 x y（可选，直接回车不显示）：").replace(",", " ").replace("，", " ").split()
        try:
            source = None if not values else tuple(map(float, values))
            validate_inputs(points, bearings, source)
            return points, bearings, source
        except ValueError as error:
            print(f"输入有误：{error}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="输入有效示向度，画出检测点、示向射线和固定 ±1° 误差扇区；不计算定位区域。")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--point", nargs=3, type=float, action="append", metavar=("X", "Y", "BEARING"),
                       help="一个检测点及其示向度，可重复使用")
    group.add_argument("--demo", action="store_true", help="使用内置三测点示例")
    parser.add_argument("--source", nargs=2, type=float, metavar=("X", "Y"), help="可选参考源，只用于标记")
    parser.add_argument("--output", help="保存为 .png 或 .svg")
    parser.add_argument("--no-show", action="store_true", help="只保存图片，不打开桌面窗口；须同时给出 --output")
    args = parser.parse_args(argv)
    if args.no_show and not args.output:
        parser.error("--no-show 需要 --output 指定输出图片。")
    try:
        if args.demo:
            points, bearings, source = DEMO_POINTS, DEMO_BEARINGS, args.source or DEMO_SOURCE
        elif args.point:
            points, bearings, source = [p[:2] for p in args.point], [p[2] for p in args.point], args.source
        else:
            points, bearings, source = prompt_scene()
            if args.source is not None:
                source = args.source
        validate_inputs(points, bearings, source)
        print("\n测点         x / m         y / m     示向度 / °    误差界 / °")
        for i, ((x, y), bearing) in enumerate(zip(points, bearings)):
            print(f"S{i+1:<6} {x:12.3f} {y:12.3f} {bearing:12.3f}       [-1, 1]")
        plot_bearings(points, bearings, source, show=not args.no_show, output_path=args.output)
        if args.output:
            print(f"已保存：{args.output}")
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\n已退出。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
