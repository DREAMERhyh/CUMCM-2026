"""Cross-check (duipai) the Q1 solver against independent oracles.

Reads deterministic cases produced by gen_cases.py, re-derives every bearing from
the ground-truth source, then verifies the solver's region, diameter and circle
coverage using independent all-pairs and direct-vertex oracles. The solver itself
only ever receives detector coordinates and measured bearings.

Usage:
    python code/q1/testbench/duipai.py --dir output/q1_cases
"""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from q1 import analyze_q1, localize
from q1.geometry import contains, diameter_bruteforce, hull

TOL = 1e-7
DOMAIN_RADIUS = 1800.0


def _wrap(delta):
    return (delta + 180.0) % 360.0 - 180.0


def _observations(case):
    return [dict(position=[d["x"], d["y"]], status="direction", bearing_deg=b)
            for d, b in zip(case["detectors"], case["bearings"])]


def _check_data(case):
    checks = []
    sx, sy = case["source"]["x"], case["source"]["y"]
    checks.append(("源在分布域内", math.hypot(sx, sy) <= DOMAIN_RADIUS + 1e-6,
                   f"r={math.hypot(sx, sy):.6f}"))
    reception = case["source"]["radius"]
    for i, detector in enumerate(case["detectors"]):
        x, y = detector["x"], detector["y"]
        distance = math.hypot(sx - x, sy - y)
        checks.append((f"检测点{i+1}在接收范围内", 5.0 < distance <= reception + 1e-6,
                       f"d={distance:.6f} radius={reception}"))
        true = math.degrees(math.atan2(sy - y, sx - x)) % 360.0
        measured = case["bearings"][i]
        delta = _wrap(measured - true)
        checks.append((f"示向度{i+1}误差在±1°内", abs(delta) <= 1.0 + 1e-9,
                       f"error={delta:.9f}"))
        checks.append((f"示向度{i+1}与记录误差一致",
                       abs(delta - case["errors"][i]) <= 1e-9,
                       f"{delta:.9f} vs {case['errors'][i]:.9f}"))
    return checks


def _check_region(case, region):
    checks = []
    sx, sy = case["source"]["x"], case["source"]["y"]
    planes = region.get("planes", [])
    checks.append(("真值源位于定位区域内", contains(planes, (sx, sy)),
                   f"source=({sx},{sy}) status={region['status']}"))
    if region["status"] != "bounded":
        if case["detector_count"] == 1:
            checks.append(("单观测应为无界", region["status"] == "unbounded",
                           region["status"]))
        checks.append(("非有界区域不返回有限直径", region["diameter"] is None,
                       f"diameter={region['diameter']}"))
        checks.append(("非有界区域无直径圆结论", region["diameter_circle"] is None,
                       "ok"))
        return checks

    vertices = region["vertices"]
    diameter = region["diameter"]
    pair = region["diameter_pair"]

    oracle_diameter, oracle_pair = diameter_bruteforce(vertices)
    checks.append(("直径=全点对oracle", math.isclose(diameter, oracle_diameter, rel_tol=1e-9, abs_tol=1e-8),
                   f"{diameter:.12f} vs {oracle_diameter:.12f}"))
    checks.append(("直径端点距离一致",
                   math.isclose(math.dist(pair[0], pair[1]), diameter, rel_tol=1e-9, abs_tol=1e-8),
                   f"{math.dist(pair[0], pair[1]):.12f}"))
    checks.append(("直径端点属于顶点集", all(p in vertices for p in pair),
                   f"pair={pair}"))

    center = [(pair[0][i] + pair[1][i]) / 2.0 for i in (0, 1)]
    radius = diameter / 2.0
    farthest = max(math.dist(center, p) for p in vertices)
    expected_covers = farthest <= radius + TOL
    expected_excess = max(0.0, farthest - radius)
    circle = region["diameter_circle"]
    checks.append(("直径圆覆盖结论一致", circle["covers"] == expected_covers,
                   f"{circle['covers']} vs {expected_covers}"))
    checks.append(("直径圆超出量一致",
                   math.isclose(circle["excess"], expected_excess, rel_tol=1e-9, abs_tol=1e-8),
                   f"{circle['excess']:.12f} vs {expected_excess:.12f}"))

    mec = region["minimum_enclosing_circle"]
    r = mec["radius"]
    checks.append(("最小包围圆半径>=直径/2", r >= diameter / 2.0 - TOL,
                   f"{r:.12f} vs {diameter/2:.12f}"))
    checks.append(("最小包围圆半径<=直径/sqrt(3) (Jung)", r <= diameter / math.sqrt(3.0) + TOL,
                   f"{r:.12f} vs {diameter/math.sqrt(3):.12f}"))
    checks.append(("最小包围圆覆盖全部顶点",
                   all(math.dist(mec["center"], p) <= r + TOL for p in vertices),
                   "ok"))

    ordered = hull(vertices)
    checks.append(("顶点为严格逆时针凸包", ordered == vertices, f"{len(ordered)} vs {len(vertices)}"))
    checks.append(("每个顶点满足全部约束", all(contains(planes, v) for v in vertices), "ok"))

    area = abs(sum(p[0] * q[1] - p[1] * q[0]
                   for p, q in zip(vertices, vertices[1:] + vertices[:1]))) / 2.0
    checks.append(("区域面积与鞋带公式一致",
                   math.isclose(region["area"], area, rel_tol=1e-9, abs_tol=1e-8),
                   f"{region['area']:.12f} vs {area:.12f}"))
    return checks


def _check_contraction(case):
    observations = _observations(case)
    bounds = [-2100.0, -2100.0, 2100.0, 2100.0]
    last = math.inf
    for count in range(1, len(observations) + 1):
        region = localize(observations[:count], bounds, error_deg=1.0)
        if region["status"] == "bounded":
            if region["diameter"] > last + 1e-6:
                return [("有界区域直径逐次收缩", False,
                         f"n={count} 直径 {region['diameter']} > 前值 {last}")]
            last = region["diameter"]
    return [("有界区域直径逐次收缩", True, "ok")]


def check_case(case):
    checks = list(_check_data(case))
    try:
        region = analyze_q1([(d["x"], d["y"]) for d in case["detectors"]],
                            list(case["bearings"]), 1.0)["region"]
    except Exception as error:
        return checks + [("求解器无异常", False, f"{type(error).__name__}: {error}")]
    checks.append(("求解器无异常", True, "ok"))
    checks.extend(_check_region(case, region))
    checks.extend(_check_contraction(case))
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="对拍核验 Q1 求解器：与全点对直径、直接顶点覆盖等独立 oracle 交叉验证。")
    parser.add_argument("--dir", default="output/q1_cases",
                        help="测试用例目录，默认 output/q1_cases")
    args = parser.parse_args(argv)

    case_dir = Path(args.dir)
    manifest_path = case_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"未找到 {manifest_path}，请先运行 gen_cases.py。", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = [json.loads((case_dir / name).read_text(encoding="utf-8"))
             for name in manifest["cases"]]

    failures = []
    status_counts = {}
    total_checks = 0
    for case in cases:
        checks = check_case(case)
        for name, ok, detail in checks:
            total_checks += 1
            if not ok:
                failures.append((case["case_id"], name, detail))
        region_status = None
        try:
            region_status = analyze_q1(
                [(d["x"], d["y"]) for d in case["detectors"]],
                list(case["bearings"]), 1.0)["region"]["status"]
        except Exception:
            region_status = "error"
        status_counts[region_status] = status_counts.get(region_status, 0) + 1

    print("Q1 对拍结果")
    print(f"用例总数：{len(cases)}")
    print(f"检查总数：{total_checks}")
    print(f"失败：{len(failures)}")
    print("区域状态分布：", status_counts)
    if failures:
        print("\n失败明细：")
        for case_id, name, detail in failures:
            print(f"  [{case_id}] {name} -> {detail}")
        return 1
    print("全部检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
