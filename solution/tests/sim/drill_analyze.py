"""演练对账分析脚本：读 run_drill 摘要与 JSONL，生成判定表与 CSV。

用法（在 solution/ 下）：
    python tests/sim/drill_analyze.py \
        --official '{"004941-787471": 15, "005139-833629": 14}' \
        --csv output/sim/drill_records.csv

- ``--official`` 为 {时间戳: GUI 官方干扰源总数} 映射（键取文件名的
  ``HHMMSS-ffffff`` 段即可）；缺失的局以 cleared+absent 为 unknown。
- 判定规则（手册 E 节）：cleared + absent == official_total 为一致；
  小于为漏检；cleared+absent 恒为 20（Q3 策略把未发现频道判 absent）。
- 扫描段虚拟时间 = 首个 /clear 动作之前的累计虚拟时刻（不含清除类耗时）；
  与离线基准 2172.7s 对比，偏差 >±5% 会在表中标出。
"""

import argparse
import json
from pathlib import Path
import re
import sys

BASE = Path(__file__).resolve().parents[1]
DEFAULT_CSV = Path("output/sim/drill_records.csv")
SCAN_REFERENCE_S = 2172.7
SCAN_TOLERANCE = 0.05
CSV_COLUMNS = [
    "game_no", "problem", "test_case_code", "official_total", "cleared",
    "absent", "cleared_plus_absent", "consistent", "scan_layout",
    "virtual_time_s", "average_clear_time_s", "scan_phase_s", "note",
]


def find_summary_files(problem=3, pattern=None):
    if pattern is None:
        pattern = f"q{problem}_*_summary.json"
    return sorted(Path("output/sim").glob(pattern))


def scan_phase_seconds(jsonl_path):
    """返回首次 /clear 之前（不含该次清除）的累计虚拟时间。"""
    scan_end = None
    previous_virtual = 0.0
    for line in Path(jsonl_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record["action"]["kind"] == "clear" and scan_end is None:
            scan_end = previous_virtual
        response = record.get("response") or {}
        if response.get("virtual_time_s") is not None:
            previous_virtual = response["virtual_time_s"]
    if scan_end is None:
        scan_end = previous_virtual  # 全无清除时以最终时刻近似
    return scan_end


def summarize_game(summary_path, official_total=None, scan_reference=SCAN_REFERENCE_S):
    data = json.loads(summary_path.read_text(encoding="utf-8"))
    stamp = summary_path.name.replace("_summary.json", "")
    jsonl_name = f"{stamp}.jsonl"
    jsonl_path = summary_path.with_name(jsonl_name)
    cleared = data["cleared_count"]
    absent = data["absent_count"]
    combined = cleared + absent
    official = official_total
    # 对账一致的口径：全部官方源被清除，且 20 个频道全部定性。
    consistent = (official is not None and cleared == official
                  and combined == 20)
    leak = (official is not None
            and (cleared < official or combined < 20))
    scan_s = scan_phase_seconds(jsonl_path) if jsonl_path.exists() else None
    deviation = None
    if scan_s is not None:
        deviation = (scan_s - scan_reference) / scan_reference
    notes = []
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if line.strip() and json.loads(line).get("note"):
                notes.append(json.loads(line)["note"])
    return {
        "test_case_code": stamp,
        "problem": data["problem"],
        "scan_layout": data.get("scan_layout"),
        "official_total": official,
        "cleared": cleared,
        "absent": absent,
        "cleared_plus_absent": combined,
        "consistent": consistent,
        "leak": leak,
        "unknown_totals": official is None,
        "safety_exit_note": ";".join(sorted(set(notes))) or None,
        "virtual_time_s": data["virtual_time_s"],
        "average_clear_time_s": data.get("average_clear_time_s"),
        "time_accounting_ok": data.get("time_accounting_matches_official"),
        "recon_difference_s": (data.get("recon", {}).get("difference_s")),
        "scan_phase_s": scan_s,
        "scan_deviation": deviation,
        "scan_out_of_tolerance": (deviation is not None
                                  and abs(deviation) > SCAN_TOLERANCE),
    }


def write_csv(rows, csv_path):
    """合并既有 CSV（按 test_case_code 幂等替换）并重新编号落盘。"""
    merged = {}
    if csv_path.exists():
        lines = csv_path.read_text(encoding="utf-8-sig").splitlines()
        header = lines[0].split(",")
        for line in lines[1:]:
            if line.strip():
                record = dict(zip(header, line.split(",")))
                merged[record["test_case_code"]] = record
    for row in rows:
        merged[row["test_case_code"]] = dict(row)
    ordered = sorted(merged.values(), key=lambda item: item["test_case_code"])
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        stream.write(",".join(CSV_COLUMNS) + "\n")
        for index, row in enumerate(ordered, 1):
            stream.write(",".join([
                str(index),
                str(row.get("problem", "")),
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
    return csv_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="演练对账判定表与 CSV")
    parser.add_argument("--official", type=json.loads, default="{}",
                        help='{时间戳: 官方总数} 的 JSON，如 \'{"004941-787471": 15}\'')
    parser.add_argument("--pattern", default=None,
                        help="summary glob（默认 q3_*_summary.json）")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args(argv)

    rows = []
    print("=" * 120)
    print(f"{'局':>2}{'时间戳':>21}{'官方':>5}{'清':>4}{'缺':>4}{'c+a':>5}"
          f"{'一致?':>6}{'安全退出':>14}{'对账差s':>10}{'总虚拟s':>10}"
          f"{'均值s/源':>10}{'扫描段s':>10}{'偏差':>8}")
    print("-" * 120)
    for index, summary_path in enumerate(find_summary_files(pattern=args.pattern), 1):
        stamp = summary_path.name.replace("_summary.json", "")
        official = args.official.get(stamp)
        if official is None:
            for key, value in args.official.items():
                if key in stamp:  # 键可用时间戳任意段（如 HHMMSS-ffffff）。
                    official = value
                    break
        row = summarize_game(summary_path, official_total=official)
        note = "非官方编码" if official is None else ""
        if row["safety_exit_note"]:
            note = (f"{row['safety_exit_note']}" if not note
                    else f"{note}；{row['safety_exit_note']}")
        if row["leak"]:
            note = (f"漏检/未完成！清{row['cleared']}<总{row['official_total']}"
                    if note == "" else f"{note}；清{row['cleared']}<总{row['official_total']}")
        if row["scan_out_of_tolerance"]:
            note = (note + "；扫描段超差" if note else "扫描段超差")
        row["note"] = note
        rows.append(row)
        consistent_mark = ("TRUE" if row["consistent"]
                           else ("FALSE*" if row["leak"] or row["official_total"] is not None else "?"))
        safety_mark = (row["safety_exit_note"][:12]
                       if row["safety_exit_note"] else "-")
        diff_mark = (f"{row['recon_difference_s']:+.6f}"
                     if row["recon_difference_s"] is not None else "-")
        deviation_mark = (f"{row['scan_deviation']:+.1%}"
                          if row["scan_deviation"] is not None else "-")
        print(f"{index:>2}{stamp:>21}{str(row['official_total']):>5}"
              f"{row['cleared']:>4}{row['absent']:>4}"
              f"{row['cleared_plus_absent']:>5}{consistent_mark:>6}"
              f"{safety_mark:>14}{diff_mark:>10}"
              f"{row['virtual_time_s']:>10.1f}"
              f"{(row['average_clear_time_s'] or 0.0):>10.1f}"
              f"{(row['scan_phase_s'] or 0.0):>10.1f}"
              f"{deviation_mark:>8}")
    leaked = [row for row in rows if row["leak"]]
    unknown = [row for row in rows if row["unknown_totals"]]
    if not leaked and not unknown:
        verdict = "全部一致（cleared==官方总数 且 c+a==20）：布局可锁定 pure_ring8。"
    elif leaked:
        verdict = (f"检测到漏检/未完成 {len(leaked)} 局（见上表 *），"
                   f"停止正式测试，先分析并复跑。")
    else:
        verdict = (f"{len(unknown)} 局缺少 official_total，无法完全判定，"
                   f"其余局一致。")
    csv_path = write_csv(rows, args.csv)
    print("=" * 120)
    print(f"判定：{verdict}")
    print(f"CSV：{csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())