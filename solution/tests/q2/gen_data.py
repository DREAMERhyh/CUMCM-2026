"""按 Q2 API 生成可复现的第一观测测试数据。"""

import argparse
import json
import math
import random
from pathlib import Path


def _bearing(sensor, source):
    return math.degrees(math.atan2(source[1] - sensor[1],
                                   source[0] - sensor[0])) % 360.0


def _random_case(rng, index):
    radius = 1750.0 * math.sqrt(rng.random())
    angle = rng.random() * 2.0 * math.pi
    source = (radius * math.cos(angle), radius * math.sin(angle))
    distance = rng.uniform(50.0, 1490.0)
    direction = rng.random() * 2.0 * math.pi
    sensor = (source[0] + distance * math.cos(direction),
              source[1] + distance * math.sin(direction))
    error = rng.uniform(-1.0, 1.0)
    return source, sensor, error, rng.randint(1, 20), {}


def _boundary_case(rng, index):
    angle = math.radians((index * 53.0) % 360.0)
    source = ((1800.0 - 1e-4) * math.cos(angle),
              (1800.0 - 1e-4) * math.sin(angle))
    distance = (1000.0, 1500.0)[index % 2]
    sensor = (source[0] - distance * math.cos(angle),
              source[1] - distance * math.sin(angle))
    error = 1.0 if index % 2 == 0 else -1.0
    return source, sensor, error, (1, 20)[index % 2], {}


def _adversarial_case(rng, index):
    source = (0.0, (-1.0, 0.0, 1.0)[index % 3] * 1e-4)
    sensor = (-1499.999, (index % 5 - 2) * 1e-5)
    error = (-1.0, 0.0, 1.0)[index % 3]
    overrides = {"min_receive_radius": 10.0} if index % 4 == 0 else {}
    return source, sensor, error, 1 + index % 20, overrides


def generate_case(mode, seed, index):
    rng = random.Random(seed + index)
    builders = {
        "random": _random_case,
        "boundary": _boundary_case,
        "adversarial": _adversarial_case,
    }
    source, sensor, error, channel, config = builders[mode](rng, index)
    measured = (_bearing(sensor, source) + error) % 360.0
    return {
        "case_id": f"{mode}_{seed}_{index:04d}",
        "mode": mode,
        "input": {
            "first_observation": {
                "position": [round(sensor[0], 9), round(sensor[1], 9)],
                "channel": channel,
                "result": "direction",
                "bearing_deg": round(measured, 9),
            },
            "current_channel": channel,
            "config_overrides": config,
        },
        "oracle": {
            "source_position": [round(source[0], 9), round(source[1], 9)],
            "bearing_error_deg": error,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成符合 Q2 API 的 JSON 测试数据。")
    parser.add_argument("--mode", choices=("random", "boundary", "adversarial"),
                        required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("--count 必须为正整数")
    output = args.out or Path(__file__).with_name("data") / args.mode
    output.mkdir(parents=True, exist_ok=True)
    names = []
    for index in range(args.count):
        name = f"case_{index + 1:04d}.json"
        case = generate_case(args.mode, args.seed, index)
        (output / name).write_text(json.dumps(case, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        names.append(name)
    manifest = {"mode": args.mode, "seed": args.seed, "total": len(names),
                "cases": names}
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {len(names)} 个 {args.mode} 用例 -> {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
