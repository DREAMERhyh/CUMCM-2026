"""Q1 acceptance testbench: CLI, JSON and rendered artifact integration."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "code" / "q1" / "cli.py"


class Q1CliTestbench(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run([sys.executable, "-B", str(CLI), *map(str, arguments)],
                              cwd=ROOT, capture_output=True, text=True,
                              errors="replace", timeout=30)

    def test_demo_exports_png_and_json(self):
        with tempfile.TemporaryDirectory() as folder:
            png = Path(folder) / "q1.png"
            result_path = Path(folder) / "q1.json"
            completed = self.run_cli("--demo", "--no-show", "--output", png,
                                     "--result-json", result_path)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertGreater(png.stat().st_size, 20_000)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["region"]["status"], "bounded")
            self.assertEqual(len(result["progress"]), 3)
            self.assertIsInstance(result["region"]["diameter_circle"]["covers"], bool)
            self.assertIn("直径圆能否覆盖定位区域", completed.stdout)

    def test_direct_measurements_export_svg(self):
        with tempfile.TemporaryDirectory() as folder:
            svg = Path(folder) / "q1.svg"
            completed = self.run_cli(
                "--point", -600, -300, 35.89,
                "--point", 850, -250, 139.44,
                "--point", -200, 1000, 300.56,
                "--no-show", "--output", svg)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            content = svg.read_text(encoding="utf-8")
            self.assertIn("localization-region", content)
            self.assertIn("diameter-circle", content)

    def test_single_measurement_reports_unbounded_region(self):
        with tempfile.TemporaryDirectory() as folder:
            png = Path(folder) / "unbounded.png"
            result_path = Path(folder) / "unbounded.json"
            completed = self.run_cli("--point", 0, 0, 0,
                                     "--no-show", "--output", png,
                                     "--result-json", result_path)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["region"]["status"], "unbounded")
            self.assertIsNone(result["region"]["diameter"])
            self.assertTrue(png.exists())

    def test_invalid_bearing_fails_without_artifact(self):
        with tempfile.TemporaryDirectory() as folder:
            png = Path(folder) / "invalid.png"
            completed = self.run_cli("--point", 0, 0, 360,
                                     "--no-show", "--output", png)
            self.assertEqual(completed.returncode, 1)
            self.assertFalse(png.exists())
            self.assertIn("[0, 360)", completed.stderr)


if __name__ == "__main__":
    unittest.main()
