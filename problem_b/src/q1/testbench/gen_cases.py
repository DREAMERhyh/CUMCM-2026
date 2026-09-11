"""Generate deterministic Q1 test cases with ground truth for the duipai checker.

Each case stores the only inputs the Q1 solver may read (detector coordinates and
measured bearings) plus the source position, reception radius and per-observation
true errors that the checker uses exclusively to verify invariants.

Usage:
    python code/q1/testbench/gen_cases.py --out output/q1_cases --seed 20260911 --count-per-config 20
"""

import argparse
import json
import math
import random
from pathlib import Path

DOMAIN_RADIUS = 1800.0
MIN_RECEPTION = 1000.0
MAX_RECEPTION = 1500.0
DETECTOR_COUNTS = (1, 2, 3, 4, 6, 10)
ERROR_MODES = ("uniform", "endpoints", "mixed")


def sample_error(rng, mode):
    if mode == "uniform":
        return rng.uniform(-1.0, 1.0)
    if mode == "endpoints":
        return 1.0 if rng.random() < 0.5 else -1.0
    if mode == "mixed":
        if rng.random() < 0.5:
            return rng.uniform(-1.0, 1.0)
        return 1.0 if rng.random() < 0.5 else -1.0
    raise ValueError(f"未知的误差档：{mode}")


def _place_detectors(rng, source, reception, count):
    sx, sy = source
    detectors = []
    for _ in range(count):
        for _ in range(2000):
            rr = (reception - 10.0) * math.sqrt(rng.random())
            aa = rng.random() * 2.0 * math.pi
            x, y = sx + rr * math.cos(aa), sy + rr * math.sin(aa)
            if math.hypot(x, y) <= DOMAIN_RADIUS - 1e-3 and math.hypot(x - sx, y - sy) > 5.0:
                detectors.append((round(x, 4), round(y, 4)))
                break
        else:
            raise ValueError(f"未能生成检测点，seed={rng}")
    return detectors


def generate_case(seed, detector_count, error_mode):
    rng = random.Random(seed)
    r = DOMAIN_RADIUS * math.sqrt(rng.random())
    a = rng.random() * 2.0 * math.pi
    source = (round(r * math.cos(a), 4), round(r * math.sin(a), 4))
    reception = round(rng.uniform(MIN_RECEPTION, MAX_RECEPTION), 4)
    detectors = _place_detectors(rng, source, reception, detector_count)
    bearings, true_bearings, errors = [], [], []
    for x, y in detectors:
        true = math.degrees(math.atan2(source[1] - y, source[0] - x)) % 360.0
        error = sample_error(rng, error_mode)
        bearing = (true + error) % 360.0
        true_bearings.append(round(true, 9))
        errors.append(round(error, 9))
        bearings.append(round(bearing, 9))
    return dict(
        case_id=f"seed{seed:06d}_n{detector_count}_m{error_mode}",
        seed=seed,
        detector_count=detector_count,
        error_mode=error_mode,
        source=dict(x=source[0], y=source[1], radius=reception),
        detectors=[dict(x=x, y=y) for x, y in detectors],
        bearings=bearings,
        true_bearings=true_bearings,
        errors=errors,
        solver_error_deg=1.0,
    )


def build_cases(base_seed, count_per_config):
    cases = []
    for detector_count in DETECTOR_COUNTS:
        for error_mode in ERROR_MODES:
            for index in range(count_per_config):
                seed = base_seed + 1000 * DETECTOR_COUNTS.index(detector_count) + \
                    100 * ERROR_MODES.index(error_mode) + index
                cases.append(generate_case(seed, detector_count, error_mode))
    return cases


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="生成 Q1 确定性测试用例（含仅用于校验的真值源与逐点误差）。")
    parser.add_argument("--out", default="output/q1_cases",
                        help="输出目录，默认 output/q1_cases")
    parser.add_argument("--seed", type=int, default=20260911, help="基准随机种子")
    parser.add_argument("--count-per-config", type=int, default=20,
                        help="每种 检测点数×误差档 组合的用例数，默认 20")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = build_cases(args.seed, args.count_per_config)
    for index, case in enumerate(cases, 1):
        (out_dir / f"case_{index:04d}.json").write_text(
            json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = dict(
        base_seed=args.seed,
        count_per_config=args.count_per_config,
        detector_counts=list(DETECTOR_COUNTS),
        error_modes=list(ERROR_MODES),
        total=len(cases),
        cases=[f"case_{i:04d}.json" for i in range(1, len(cases) + 1)],
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {len(cases)} 个用例 -> {out_dir.resolve()}")
    print("  检测点数：", DETECTOR_COUNTS)
    print("  误差档：", ERROR_MODES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
