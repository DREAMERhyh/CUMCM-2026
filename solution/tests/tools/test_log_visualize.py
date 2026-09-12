import json
from pathlib import Path
import sys
import tempfile
import unittest

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tools.log_visualize.app import _format_virtual_clock
from tools.log_visualize.model import load_replay, resolve_log_path


class LogVisualizeTests(unittest.TestCase):
    def _write_log(self, directory):
        records = [
            {
                "sequence": 1,
                "recorded_at_utc": "2026-09-12T00:00:00+00:00",
                "action": {
                    "kind": "enter", "request_id": "enter-1",
                    "position": None, "channel": None,
                },
                "response": {"accepted": True, "virtual_time_s": 0},
            },
            {
                "sequence": 2,
                "recorded_at_utc": "2026-09-12T00:00:01+00:00",
                "action": {
                    "kind": "measure", "request_id": "measure-2",
                    "position": {"x": 3.0, "y": 4.0}, "channel": 2,
                },
                "response": {
                    "accepted": True, "virtual_time_s": 7.0,
                    "measure_result": "direction", "svd_deg": 45.0,
                },
            },
            {
                "sequence": 3,
                "recorded_at_utc": "2026-09-12T00:00:02+00:00",
                "action": {
                    "kind": "clear", "request_id": "clear-3",
                    "position": {"x": 3.0, "y": 4.0}, "channel": 2,
                },
                "response": {
                    "accepted": True, "virtual_time_s": 12.0,
                    "clear_result": "success",
                },
            },
            {
                "sequence": 4,
                "recorded_at_utc": "2026-09-12T00:00:03+00:00",
                "action": {
                    "kind": "clear", "request_id": "clear-4",
                    "position": {"x": 8.0, "y": 4.0}, "channel": 3,
                },
                "response": {
                    "accepted": True, "virtual_time_s": 18.0,
                    "clear_result": "success",
                },
            },
            {
                "sequence": 5,
                "recorded_at_utc": "2026-09-12T00:00:04+00:00",
                "action": {
                    "kind": "exit", "request_id": "exit-5",
                    "position": None, "channel": None,
                },
                "response": {
                    "accepted": True, "virtual_time_s": 18.0,
                    "exit_reason": "user_exit",
                },
            },
        ]
        path = Path(directory) / "q3_synthetic.jsonl"
        path.write_text(
            "".join(json.dumps(item) + "\n" for item in records),
            encoding="utf-8",
        )
        return path

    def test_replay_builds_regions_markers_and_time_breakdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_log(directory)
            replay = load_replay(path)

        self.assertEqual(len(replay.records), 5)
        self.assertEqual(len(replay.frames), 6)
        self.assertIn(2, replay.frames[2].regions)
        self.assertIn(2, replay.frames[2].active_sources)
        self.assertNotIn(2, replay.frames[3].active_sources)
        self.assertIn(2, replay.frames[3].cleared_sources)
        self.assertEqual(
            replay.frames[4].successful_clear_positions,
            ((3.0, 4.0), (8.0, 4.0)),
        )
        self.assertEqual(replay.clear_successes, 2)
        self.assertEqual(replay.clear_failures, 0)
        summary = replay.time_summary
        self.assertAlmostEqual(summary.movement_s, 2.0)
        self.assertAlmostEqual(summary.switching_s, 1.0)
        self.assertAlmostEqual(summary.measurement_s, 5.0)
        self.assertAlmostEqual(summary.optical_s, 6.0)
        self.assertAlmostEqual(summary.laser_s, 4.0)
        self.assertAlmostEqual(summary.total_virtual_s, 18.0)
        self.assertAlmostEqual(summary.unaccounted_s, 0.0)

    def test_resolve_explicit_name_and_latest_log(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write_log(directory)
            self.assertEqual(
                resolve_log_path(path.name, log_dir=directory), path.resolve()
            )
            self.assertEqual(
                resolve_log_path(log_dir=directory), path.resolve()
            )

    def test_virtual_clock_starts_at_zero_seconds(self):
        self.assertEqual(_format_virtual_clock(0), "00s")
        self.assertEqual(_format_virtual_clock(5), "05.00s")
        self.assertEqual(_format_virtual_clock(7539.751579), "02:05:39.75")


if __name__ == "__main__":
    unittest.main()
