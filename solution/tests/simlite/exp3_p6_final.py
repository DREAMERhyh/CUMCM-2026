"""[实验轮3-P6] 最终组合：interleaved+TSPN vs 晨间基线（官方口径对照）。"""
import os, sys, time
from pathlib import Path
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from q3.policy import Q3Policy
from q3.batch_policy import Q3BatchPolicy
from simlite.paired import paired_compare, write_paired_report


def make_morning_baseline():
    return Q3Policy(use_optimal_stop=False, interleaved_scan_refine=False)


def make_final():
    return Q3BatchPolicy(tspn_clear=True)


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    seed_start = int(sys.argv[2]) if len(sys.argv) > 2 else 20940000
    workers = max(1, (os.cpu_count() or 4) - 2)
    seeds = list(range(seed_start, seed_start + count))
    started = time.perf_counter()
    payload = paired_compare(make_morning_baseline, make_final, seeds,
                             workers=workers)
    payload["meta"] = {
        "arm_a": "morning_baseline(interleaved off, no A3)",
        "arm_b": "final(interleaved default + tspn_clear)",
        "count": count, "seed_start": seed_start, "workers": workers,
        "elapsed_s": round(time.perf_counter() - started, 1),
    }
    out = Path(__file__).with_name("analysis") / "exp3_p6_final.json"
    write_paired_report(payload, out)
    summary, gate = payload["summary"], payload["gate"]
    print(f"局数 {count}，墙钟 {payload['meta']['elapsed_s']}s")
    for key, item in summary.items():
        if key == "episode_count":
            continue
        diff = item["difference"]
        print(f"- {item['label']}: A med {item['a']['median']} / "
              f"B med {item['b']['median']}（中位差 {diff['median']}），"
              f"B 更优 {item['b_better']} / 持平 {item['tie']} / "
              f"更差 {item['b_worse']}，最坏恶化 {item['max_b_minus_a']}")
    print(f"门1: {gate}")
    print(f"wrote: {out}")


if __name__ == "__main__":
    main()
