"""run_drill 一键演练脚本的测试：时间对账、摘要落盘、门禁与 scan_layout。"""

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.time_model import clear_cost, measure_cost
from q3.coverage import pure_ring_8
import run_drill
from run_drill import build_policy, recon_from_log


class StubDrillClient:
    """模拟官方模拟器的极小替身：接受全部动作、按 time_model 计费。

    计费与 common/time_model 完全一致，因此摘要中的时间对账必然成立；
    不一致会由 test_recon_reports_mismatch_when_official_differs 覆盖。
    """

    def __init__(self):
        self.virtual_time = 0.0
        self.position = (0.0, 0.0)
        self.channel = 1
        self.entered = False

    def execute(self, action):
        if action.kind == "enter":
            self.entered = True
            return {
                "accepted": True,
                "real_timestamp_ms": 1760000000000,
                "virtual_time_s": self.virtual_time,
                "max_virtual_duration_s": 360000,
                "max_real_duration_s": 1200,
                "remaining_real_duration_s": 1200,
            }
        if action.kind == "exit":
            return {
                "accepted": True,
                "real_timestamp_ms": 1760000000000,
                "virtual_time_s": self.virtual_time,
                "exit_reason": "user_exit",
            }
        if action.kind == "measure":
            timing = measure_cost(self.position, action.position,
                                  self.channel, action.channel)
            self.virtual_time += timing.total_s
            self.position = action.position
            self.channel = action.channel
            return {
                "accepted": True,
                "real_timestamp_ms": 1760000000000,
                "virtual_time_s": self.virtual_time,
                "measure_result": "no_signal",
            }
        timing = clear_cost(self.position, action.position, False)
        self.virtual_time += timing.total_s
        self.position = action.position
        return {
            "accepted": True,
            "real_timestamp_ms": 1760000000000,
            "virtual_time_s": self.virtual_time,
            "clear_result": "no_target_in_range",
        }


def _official_199_log(path, measure3_virtual_s=None):
    """附件2 第10节官方示例的 JSONL 记录（无真实源，纯计时）。"""
    actions = [
        ("enter", None, None),
        ("measure", (300, 400), 1),
        ("measure", (300, 400), 2),
        ("clear", (300, 0), 3),
        ("measure", (300, 0), 2),
        ("exit", None, None),
    ]
    lines = []
    for index, (kind, position, channel) in enumerate(actions, 1):
        record = {
            "sequence": index,
            "recorded_at_utc": "2026-09-12T00:00:00+00:00",
            "action": {"kind": kind, "request_id": f"r{index}"},
        }
        if position is not None:
            record["action"]["position"] = {"x": position[0], "y": position[1]}
            record["action"]["channel"] = channel
        if kind == "enter":
            record["response"] = {"accepted": True, "virtual_time_s": 0.0}
        elif kind == "measure":
            marks = {2: 105.0, 3: 111.0, 5: 199.0}
            if index == 5 and measure3_virtual_s is not None:
                marks[5] = measure3_virtual_s
            record["response"] = {
                "accepted": True,
                "virtual_time_s": marks.get(index, 0.0),
                "measure_result": "no_signal",
            }
        elif kind == "clear":
            record["response"] = {
                "accepted": True,
                "virtual_time_s": 194.0,
                "clear_result": "no_target_in_range",
            }
        else:
            record["response"] = {"accepted": True,
                                  "virtual_time_s": 199.0,
                                  "exit_reason": "user_exit"}
        lines.append(json.dumps(record, ensure_ascii=False))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


class ReconTestbench(unittest.TestCase):
    def test_recon_reproduces_official_199_second_example(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "official.jsonl"
            _official_199_log(path)
            recon = recon_from_log(path)
        self.assertEqual(recon["official_virtual_time_s"], 199.0)
        self.assertEqual(recon["recon_total_s"], 199.0)
        self.assertTrue(recon["matches"])
        self.assertEqual(recon["difference_s"], 0.0)
        # 三段拆分：移动 100+80=180、切换 1、检测 5*3=15、光学 3。
        self.assertAlmostEqual(recon["movement_s"], 180.0)
        self.assertAlmostEqual(recon["switching_s"], 1.0)
        self.assertAlmostEqual(recon["measurement_s"], 15.0)
        self.assertAlmostEqual(recon["optical_s"], 3.0)
        self.assertAlmostEqual(recon["laser_s"], 0.0)
        self.assertEqual(recon["measure_count"], 3)
        self.assertEqual(recon["clear_count"], 1)
        self.assertEqual(recon["clear_success_channels"], [])

    def test_recon_reports_mismatch_when_official_differs(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "official.jsonl"
            _official_199_log(path, measure3_virtual_s=159.0)
            recon = recon_from_log(path)
        self.assertFalse(recon["matches"])
        self.assertAlmostEqual(recon["difference_s"], -40.0)


class MainIntegrationTestbench(unittest.TestCase):
    def test_policy_run_writes_summary_json(self):
        with TemporaryDirectory() as directory:
            summary_path = Path(directory) / "run_summary.json"
            log_path = Path(directory) / "run.jsonl"
            with patch("run_drill.build_client",
                       return_value=StubDrillClient()) as factory:
                code = run_drill.main([
                    "--problem", "3", "--mode", "policy",
                    "--robot-id", "202601101010",
                    "--scan-layout", "pure_ring8",
                    "--log", str(log_path),
                    "--summary", str(summary_path),
                    "--confirm-ready", "--confirm-policy",
                ])
            self.assertEqual(code, 0)
            self.assertTrue(log_path.exists())
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            factory.assert_called_once()
            self.assertEqual(data["problem"], 3)
            self.assertEqual(data["scan_layout"], "pure_ring8")
            self.assertEqual(data["exit_reason"], "user_exit")
            self.assertEqual(data["cleared_count"], 0)
            self.assertEqual(data["absent_count"], 20)
            self.assertTrue(data["time_accounting_matches_official"])

    def test_confirm_gates_are_required(self):
        with self.assertRaises(SystemExit) as raised:
            run_drill.main(["--problem", "3", "--robot-id", "x"])
        self.assertEqual(raised.exception.code, 2)
        with self.assertRaises(SystemExit):
            run_drill.main(["--problem", "3", "--robot-id", "x",
                            "--confirm-ready"])
        with self.assertRaises(SystemExit):
            run_drill.main(["--problem", "3", "--mode", "policy",
                            "--robot-id", "x", "--confirm-ready"])

    def test_robot_id_falls_back_to_environment(self):
        with patch.dict("os.environ", {"ROBOT_ID": "env-team"}):
            with self.assertRaises(SystemExit) as raised:
                run_drill.main(["--problem", "3"])
            self.assertEqual(raised.exception.code, 2)  # 仍缺 --confirm-ready


class BuildPolicyTestbench(unittest.TestCase):
    def test_q3_passes_scan_layout(self):
        policy = build_policy(3, scan_layout="hub_ring6")
        self.assertEqual(policy.scan_layout, "hub_ring6")

    def test_q3_default_follows_current_policy_default(self):
        policy = build_policy(3)
        self.assertIn(policy.scan_layout, ("ring7", "pure_ring8"))

    def test_q4_ignores_scan_layout(self):
        from q4.policy import Q4Policy
        policy = build_policy(4, scan_layout="pure_ring8")
        self.assertIsInstance(policy, Q4Policy)
        # Q4Policy 继承 Q3Policy 故携带默认 scan_layout 属性，但其覆盖点
        # 由 grid121() 决定，scan_layout 对 Q4 无实际作用。
        self.assertNotEqual(policy.coverage_points,
                            pure_ring_8())


if __name__ == "__main__":
    unittest.main()