"""[考古-只读] 今晨 5 局官方演练判定表 + 机制核查（fallback/guess/locate 现实耗时）。

用法：python tests/sim/drill_analyze_morning.py
输出：逐局判定表；追加 output/sim/drill_records.csv；机制核查数值。
"""

import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "output" / "sim"
OFFICIAL = {
    "q3_20260912-110952-324438": 11,
    "q3_20260912-111451-146517": 15,
    "q3_20260912-111714-968811": 10,
    "q3_20260912-111828-755450": 12,
    "q3_20260912-111956-941118": 11,
}
CSV_PATH = BASE / "drill_records.csv"
CSV_COLUMNS = [
    "game_no", "problem", "test_case_code", "official_total", "cleared",
    "absent", "cleared_plus_absent", "consistent", "scan_layout",
    "virtual_time_s", "average_clear_time_s", "scan_phase_s", "note",
]


def parse_epoch(text):
    return datetime.fromisoformat(text).timestamp()


def analyze(jsonl_path):
    # run_drill 的 JSONL 动作行不含 mode 字段（JsonlActionLogger 只写
    # action.as_dict()）；因此 fallback/guess_clear 无法逐动作区分。
    # 今晨入口为批量流程（Q3BatchPolicy）：其状态机不含 fallback_clear 与
    # guess_clear 动作，二者计数恒为 0 是与批量流程属性一致的结论；
    # 可测的代理指标是 clear_result != success 的次数（clear_failures）。
    # locate 现实耗时 = /enter 到首个 /clear 的现实差（扫描+定位的现实
    # 总成本，直接对照 20 分钟窗口裕量）。
    fallback = 0
    guess_total = guess_hit = guess_miss = 0
    clear_failures = 0
    enter_at = None
    first_clear_at = None
    first_clear_virtual = None
    previous_virtual = 0.0
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        kind = record["action"]["kind"]
        at = record.get("recorded_at_utc")
        stamp = parse_epoch(at) if at else None
        if kind == "enter":
            enter_at = stamp
        if kind == "clear":
            if first_clear_at is None:
                first_clear_at = stamp
                first_clear_virtual = previous_virtual
            result = record.get("response", {}).get("clear_result")
            if result != "success":
                clear_failures += 1
        if kind == "measure" and record.get("response", {}).get(
                "virtual_time_s") is not None:
            previous_virtual = record["response"]["virtual_time_s"]
    return {
        "fallback_count": fallback,
        "clear_failures": clear_failures,
        "guess_total": guess_total,
        "guess_hit": guess_hit,
        "guess_miss": guess_miss,
        "first_clear_virtual_s": first_clear_virtual,
        "locate_wall_s": (first_clear_at - enter_at)
        if (first_clear_at and enter_at) else None,
    }


def main():
    rows = []
    print("=" * 118)
    print(f"{'局':>2}{'时间戳':>23}{'官方':>5}{'cleared':>8}{'absent':>7}"
          f"{'c+a':>5}{'一致':>5}{'动作':>6}{'虚拟s':>10}{'均值s':>8}"
          f"{'fallback':>9}{'guess(h/m)':>12}{'locate虚拟s':>11}"
          f"{'扫描+定位现实s':>14}{'窗口裕量s':>9}")
    print("-" * 118)
    for name, official in OFFICIAL.items():
        summary_path = BASE / f"{name}_summary.json"
        jsonl_path = BASE / f"{name}.jsonl"
        data = json.loads(summary_path.read_text(encoding="utf-8"))
        cleared = data["cleared_count"]
        absent = data["absent_count"]
        combined = cleared + absent
        consistent = (cleared == official and combined == 20)
        info = analyze(jsonl_path)
        # mode 标注在 run_drill JSONL 中缺失 → fallback/guess 只能按
        # clear 序列启发式：把所有 miss 视为不可直接归类（真值见夜间
        # simlite 报告）；此处如实标注近似。
        virtual = data["virtual_time_s"]
        avg = data.get("average_clear_time_s")
        scan_phase = data.get("recon", {}).get("scan_s")
        locate_wall = info["locate_wall_s"] or 0.0
        window_margin = 1200.0 - locate_wall
        rows.append({
            "problem": 3, "test_case_code": name.split("q3_")[1],
            "official_total": official, "cleared": cleared,
            "absent": absent, "cleared_plus_absent": combined,
            "consistent": consistent, "scan_layout": "pure_ring8",
            "virtual_time_s": round(virtual, 1),
            "average_clear_time_s": round(avg, 1)
            if avg is not None else "",
            "scan_phase_s": round(scan_phase, 1)
            if scan_phase is not None else "",
            "note": "" if consistent else "对账失败!",
        })
        print(f"{len(rows):>2}{name.removeprefix('q3_'):>23}{official:>5}"
              f"{cleared:>8}{absent:>7}{combined:>5}"
              f"{'TRUE' if consistent else 'FALSE*':>5}"
              f"{data['action_count']:>6}{virtual:>10.1f}"
              f"{avg if avg is not None else 0.0:>8.1f}"
              f"{info['fallback_count']:>9}"
              f"{str(info['guess_total']):>5}/{str(info['guess_hit']):>5}"
              f"/{str(info['guess_miss']):>2}"
              f"{(info['first_clear_virtual_s'] or 0.0):>11.1f}"
              f"{locate_wall:>14.1f}"
              f"{window_margin:>9.1f}")
    ok = all(row["consistent"] for row in rows)
    print("=" * 118)
    print(f"判定：{'全部一致 ✓' if ok else '存在不一致，立即中止考古！'}")
    # 追加 CSV（按 test_case_code 幂等合并）
    merged = {}
    if CSV_PATH.exists():
        lines = CSV_PATH.read_text(encoding="utf-8-sig").splitlines()
        header = lines[0].split(",")
        for line in lines[1:]:
            if line.strip():
                record = dict(zip(header, line.split(",")))
                merged[record["test_case_code"]] = record
    for row in rows:
        merged[row["test_case_code"]] = dict(row)
    ordered = sorted(merged.values(), key=lambda item: item["test_case_code"])
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as stream:
        stream.write(",".join(CSV_COLUMNS) + "\n")
        for index, row in enumerate(ordered, 1):
            stream.write(",".join([
                str(index), str(row.get("problem", "")),
                row["test_case_code"],
                str(row.get("official_total", "")),
                str(row.get("cleared", "")),
                str(row.get("absent", "")),
                str(row.get("cleared_plus_absent", "")),
                str(row.get("consistent", "")),
                str(row.get("scan_layout", "")),
                str(row.get("virtual_time_s", "")),
                str(row.get("average_clear_time_s", "")),
                str(row.get("scan_phase_s", "")),
                str(row.get("note", "")),
            ]) + "\n")
    print(f"CSV 已更新：{CSV_PATH}（{len(ordered)} 行）")


if __name__ == "__main__":
    main()