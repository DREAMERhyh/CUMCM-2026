"""按 Q1 API 生成可复现的随机、边界和对抗测试数据。"""

import argparse
import json
import math
import random
from pathlib import Path

DOMAIN_RADIUS = 1800.0
DETECTOR_COUNTS = (1, 2, 3, 4, 6, 10)


def _bearing(sensor, source):
    return math.degrees(math.atan2(source[1] - sensor[1],
                                   source[0] - sensor[0])) % 360.0


def _random_case(rng, index):
    source_radius = DOMAIN_RADIUS * math.sqrt(rng.random())
    angle = rng.random() * 2.0 * math.pi
    source = (source_radius * math.cos(angle), source_radius * math.sin(angle))
    count = DETECTOR_COUNTS[index % len(DETECTOR_COUNTS)]
    sensors = []
    for _ in range(count):
        distance = rng.uniform(100.0, 1450.0)
        direction = rng.random() * 2.0 * math.pi
        sensors.append((source[0] + distance * math.cos(direction),
                        source[1] + distance * math.sin(direction)))
    errors = [rng.uniform(-1.0, 1.0) for _ in sensors]
    return source, sensors, errors


def _boundary_case(rng, index):
    angle = (index * 47.0) % 360.0
    radius = 1800.0 - (index % 3) * 1e-3
    source = (radius * math.cos(math.radians(angle)),
              radius * math.sin(math.radians(angle)))
    count = (2, 3, 4, 6)[index % 4]
    sensors = []
    for j in range(count):
        back = math.radians(angle + 180.0 + (j - count / 2) * 18.0)
        distance = 700.0 + 80.0 * j
        sensors.append((source[0] + distance * math.cos(back),
                        source[1] + distance * math.sin(back)))
    errors = [1.0 if (index + j) % 2 == 0 else -1.0
              for j in range(count)]
    return source, sensors, errors


def _adversarial_case(rng, index):
    source = (100.0 + index, 50.0 - index)
    count = (2, 3, 4, 6)[index % 4]
    sensors = []
    for j in range(count):
        y_jitter = (j - count / 2) * (1e-3 if index % 2 == 0 else 0.2)
        sensors.append((-900.0 + 70.0 * j, source[1] + y_jitter))
    errors = [(-1.0, 0.0, 1.0)[(index + j) % 3] for j in range(count)]
    return source, sensors, errors


def generate_case(mode, seed, index):
    rng = random.Random(seed + index)
    builders = {
        "random": _random_case,
        "boundary": _boundary_case,
        "adversarial": _adversarial_case,
    }
    source, sensors, errors = builders[mode](rng, index)
    bearings = [(_bearing(sensor, source) + error) % 360.0
                for sensor, error in zip(sensors, errors)]
    return {
        "case_id": f"{mode}_{seed}_{index:04d}",
        "mode": mode,
        "input": {
            "detector_points": [[round(x, 9), round(y, 9)] for x, y in sensors],
            "bearings_deg": [round(value, 9) for value in bearings],
            "error_deg": 1.0,
        },
        "oracle": {
            "source_position": [round(source[0], 9), round(source[1], 9)],
            "bearing_errors_deg": [round(value, 9) for value in errors],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成符合 Q1 API 的 JSON 测试数据。")
    parser.add_argument("--mode", choices=("random", "boundary", "adversarial"),
                        required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("--count 必须为正整数")
    output = args.out or Path(__file__).with_name("data") / args.mode
    output.mkdir(parents=True, exist_ok=True)
    names = []
    for index in range(args.count):
        case = generate_case(args.mode, args.seed, index)
        name = f"case_{index + 1:04d}.json"
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
