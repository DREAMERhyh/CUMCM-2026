"""Q2 独立对拍：核验离散基线、连续FIM、连续域和时间记账。"""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.models import BearingObservation
from q2 import Q2Config, plan_second_point


def _inside_convex(polygon, point, tolerance=1e-6):
    signs = []
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        cross = ((second[0] - first[0]) * (point[1] - first[1])
                 - (second[1] - first[1]) * (point[0] - first[0]))
        if abs(cross) > tolerance:
            signs.append(cross > 0)
    return not signs or all(sign == signs[0] for sign in signs)


def _load_plan(case):
    data = case["input"]
    observation = BearingObservation(**data["first_observation"])
    config = Q2Config(**data.get("config_overrides", {}))
    return observation, config, plan_second_point(
        observation, current_channel=data.get("current_channel"), config=config)


def check_case(case):
    observation, config, plan = _load_plan(case)
    failures = []

    def check(name, condition, detail):
        if not condition:
            failures.append((name, detail))

    candidates = plan["candidates"]
    guaranteed = [item for item in candidates if item["guaranteed_reception"]]
    pool = guaranteed or candidates
    oracle = min(pool, key=lambda item: (item["score"],
                                         -item["fim_proxy_per_s"],
                                         item["point"]))
    check("有限候选池选择", plan["selected_point"] == oracle["point"],
          {"selected": plan["selected_point"], "oracle": oracle["point"]})

    vertices = plan["region"]["vertices"]
    for item in candidates:
        point = item["point"]
        expected_guaranteed = max(math.dist(point, vertex)
                                  for vertex in vertices) <= config.min_receive_radius + 1e-7
        check("保证接收标签", item["guaranteed_reception"] == expected_guaranteed,
              {"point": point, "actual": item["guaranteed_reception"],
               "expected": expected_guaranteed})
        expected_time = (math.dist(observation.position, point) / 5.0
                         + (0.0 if case["input"].get("current_channel", observation.channel)
                            == observation.channel else 1.0) + 5.0)
        check("时间记账", math.isclose(item["action_time_s"], expected_time,
                                     rel_tol=1e-12, abs_tol=1e-9),
              {"point": point, "actual": item["action_time_s"],
               "expected": expected_time})
        expected_score = (item["action_time_s"]
                          + config.uncertainty_seconds_per_metre
                          * item["worst_case_radius_m"])
        check("有限场景评分公式", math.isclose(item["score"], expected_score,
                                             rel_tol=1e-12, abs_tol=1e-9),
              {"point": point, "actual": item["score"],
               "expected": expected_score})

    regions = plan["candidate_regions"]
    guaranteed_region = regions["guaranteed_reception"]
    for point in guaranteed_region["vertices"]:
        farthest = max(math.dist(point, source) for source in vertices)
        check("保证接收连续域为内近似",
              farthest <= config.min_receive_radius + 1e-6,
              {"point": point, "farthest": farthest})
    possible = regions["possible_reception"]["vertices"]
    for source in vertices:
        check("可能接收连续域包含源域", _inside_convex(possible, source),
              {"source_vertex": source})
    check("输出声明有限场景局限",
          any("不声称连续全局最优" in text for text in plan["limitations"]),
          plan["limitations"])
    continuous = plan["continuous_fim"]
    if guaranteed_region["status"] == "bounded":
        check("连续FIM正常返回", continuous["status"] == "ok", continuous)
        if continuous["status"] == "ok":
            point = continuous["selected_point"]
            farthest = max(math.dist(point, source) for source in vertices)
            check("连续FIM点保证接收",
                  farthest <= config.min_receive_radius + 1e-6,
                  {"point": point, "farthest": farthest})
            selected_fim = continuous["selected"]
            expected_score = (
                selected_fim["action_time_s"]
                + config.uncertainty_seconds_per_metre
                * selected_fim["worst_case_radius_m"]
            )
            check("连续FIM同口径复评分",
                  math.isclose(selected_fim["score"], expected_score,
                               rel_tol=1e-12, abs_tol=1e-9),
                  {"actual": selected_fim["score"],
                   "expected": expected_score})
            check("连续FIM不劣于最佳种子",
                  (continuous["robust_fim_index_per_s"] + 1e-15
                   >= continuous["best_seed_fim_index_per_s"]),
                  continuous)
    else:
        check("空保证域禁用连续FIM",
              continuous["status"] == "unavailable", continuous)
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description="对拍 Q2 双方案规划器。")
    parser.add_argument("--dir", type=Path,
                        default=Path(__file__).with_name("data") / "random")
    args = parser.parse_args(argv)
    manifest_path = args.dir / "manifest.json"
    if not manifest_path.exists():
        print(f"未找到 {manifest_path}，请先运行 gen_data.py。", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    total = 0
    failed = []
    for name in manifest["cases"]:
        case = json.loads((args.dir / name).read_text(encoding="utf-8"))
        try:
            problems = check_case(case)
        except Exception as error:
            problems = [("执行异常", f"{type(error).__name__}: {error}")]
        total += 1
        if problems:
            failed.append((case["case_id"], case["input"], problems))
    print(f"Q2 对拍：{total} 个用例，失败 {len(failed)} 个。")
    for case_id, input_data, problems in failed:
        print(f"\n[{case_id}] 输入={json.dumps(input_data, ensure_ascii=False)}")
        for name, detail in problems:
            print(f"  {name}: {detail}")
    if failed:
        return 1
    print("有限候选选择、连续FIM可行性、连续域和时间记账检查全部通过。")
    print("注意：连续FIM是数值近似结果，不构成原问题连续全局最优证明。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
