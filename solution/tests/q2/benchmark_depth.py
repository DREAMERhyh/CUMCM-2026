"""Q2 搜索深度增益实验（只实验，不改任何默认参数）。

对 5 个代表性定位场景，把 FIM 搜索深度从当前默认档放大到 600/3000 迭代
（种子数与最小步长同比例放宽），输出 worst_radius 与墙钟对比表，用于
决定"更多计算是否带来更好点"：增益 <1% 关闭此优化线；>3% 才建议调大
默认值。

运行：python tests/q2/benchmark_depth.py
"""

from pathlib import Path
import sys
import time

SOLUTION = Path(__file__).resolve().parents[2]
SRC = SOLUTION / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json
import math

from common.models import BearingObservation
from q2.planner import Q2Config, plan_second_point

SCENARIOS = {
    "near_field": {
        "sensor": (0.0, 0.0),
        "source": (140.0, 180.0),
        "note": "第一检测点与源距离 ~228m，源区域小",
    },
    "mid_field": {
        "sensor": (-200.0, 300.0),
        "source": (800.0, 500.0),
        "note": "距离 ~1034m，中等区域",
    },
    "far_field": {
        "sensor": (200.0, 600.0),
        "source": (1400.0, 300.0),
        "note": "距离 ~1300m，大区域",
    },
    "boundary_source": {
        "sensor": (750.0, 0.0),
        "source": (1750.0, 0.0),
        "note": "源贴近 1800 圆边界",
    },
    "wide_angle_reference": {
        "sensor": (-650.0, 100.0),
        "source": (500.0, 1000.0),
        "note": "远方斜向交会参考系",
    },
}

# (fim_max_iterations, fim_seed_limit, fim_min_step_m) —— 同比例放宽。
DEPTH_LEVELS = [
    (120, 10, 2.0),
    (600, 50, 0.4),
    (3000, 250, 0.08),
]

REFERENCE_LEVEL = 120  # 与当前 Q2Config 默认一致


def _bearing_deg(sensor, source, error_deg=0.5):
    return (math.degrees(math.atan2(
        source[1] - sensor[1], source[0] - sensor[0])) + error_deg) % 360.0


def run_scenario(name, scenario, depth):
    max_iterations, seed_limit, min_step_m = depth
    observation = BearingObservation(
        tuple(scenario["sensor"]), 1, "direction",
        _bearing_deg(scenario["sensor"], scenario["source"]),
    )
    config = Q2Config(
        fim_max_iterations=max_iterations,
        fim_seed_limit=seed_limit,
        fim_min_step_m=min_step_m,
        # 保险预算足够大，保证差异来自搜索深度而非墙钟截断。
        planning_wall_clock_budget_s=360.0,
        fim_cpu_time_limit_s=360.0,
        near_optimal_region_mode="off",
    )
    started = time.perf_counter()
    plan = plan_second_point(observation, config=config)
    wall = time.perf_counter() - started
    fim = plan["continuous_fim"]
    return {
        "scenario": name,
        "max_iterations": max_iterations,
        "seed_limit": seed_limit,
        "min_step_m": min_step_m,
        "wall_s": round(wall, 2),
        "worst_radius_m": plan["selected"]["worst_case_radius_m"],
        "action_time_s": plan["selected"]["action_time_s"],
        "recommendation_source": plan["recommendation_source"],
        "fim_status": fim["status"],
        "fim_timed_out": fim.get("timed_out"),
        "fim_iteration_count": fim.get("iteration_count"),
        "fim_evaluation_count": fim.get("evaluation_count"),
        "planning_timed_out": plan["planning_timed_out"],
    }


def main(argv=None):
    results = []
    print("=" * 100)
    print(f"{'场景':<22}{'档位':>14}{'wall_s':>8}{'worst_radius':>12}"
          f"{'动作s':>8}{'推荐源':>16}{'FIM截断':>9}{'FIM迭代':>9}")
    print("-" * 100)
    for name, scenario in SCENARIOS.items():
        for depth in DEPTH_LEVELS:
            result = run_scenario(name, scenario, depth)
            results.append(result)
            print(f"{name:<22}{result['max_iterations']:>6d}/"
                  f"{result['seed_limit']:<4d}{result['wall_s']:>8.1f}"
                  f"{result['worst_radius_m']:>12.2f}"
                  f"{result['action_time_s']:>8.1f}"
                  f"{result['recommendation_source']:>16}"
                  f"{str(result['fim_timed_out']):>9}"
                  f"{result['fim_iteration_count']:>9}")
    print("=" * 100)
    gains = []
    for name in SCENARIOS:
        rows = [r for r in results if r["scenario"] == name]
        reference = next(r for r in rows
                         if r["max_iterations"] == REFERENCE_LEVEL)
        for row in rows:
            if row["max_iterations"] == REFERENCE_LEVEL:
                continue
            relative = ((reference["worst_radius_m"]
                         - row["worst_radius_m"])
                        / reference["worst_radius_m"])
            gains.append((name, row["max_iterations"], relative,
                          reference["worst_radius_m"],
                          row["worst_radius_m"]))
            print(f"{name}: 迭代 {REFERENCE_LEVEL}→{row['max_iterations']} "
                  f"worst_radius {reference['worst_radius_m']:.2f} → "
                  f"{row['worst_radius_m']:.2f} m（相对增益 "
                  f"{relative:+.2%}）")
    # 结论建议（按 4c 规则）。
    median_gain = sorted(value[2] for value in gains)[len(gains)//2]
    if median_gain <= 0.01:
        verdict = ("增益 <1%：建议关闭此优化线，保持默认 120 迭代档。")
    elif median_gain >= 0.03:
        verdict = ("增益 >3%：建议在下一次配置审查中调大默认搜索深度。")
    else:
        verdict = ("增益在 1%~3% 之间：保持默认，留待正式测试后复评。")
    payload = {
        "experiment": "q2_search_depth_gain",
        "reference_level": REFERENCE_LEVEL,
        "depth_levels": [list(level) for level in DEPTH_LEVELS],
        "scenarios": SCENARIOS,
        "results": results,
        "relative_gains": [
            {"scenario": name, "level": level, "gain": gain,
             "reference_radius_m": reference_radius,
             "deep_radius_m": deep_radius}
            for name, level, gain, reference_radius, deep_radius in gains
        ],
        "verdict": verdict,
        "verdict_rule": "增益<1% 关闭此优化线；>3% 才建议调大默认值。",
    }
    out = Path(__file__).with_name("analysis") / "depth_gain_experiment.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"结论：{verdict}")
    print(f"wrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())