import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import sweeps
from mcp import waveforms


def _request(output_dir, values=None):
    return {
        "circuit_type": "rc_lowpass",
        "parameter": "resistance",
        "values": values or ["1k", "2k", "3k"],
        "parameters": {"capacitance": "1u", "vin": "1"},
        "output_dir": str(output_dir),
        "backend": "ltspice",
    }


def _successful_point(point_dir, value):
    table = {
        "columns": ["time_s", "V(out)"],
        "rows": [[0.0, 0.0], [0.001, 0.63], [0.005, 0.99]],
    }
    csv_path = point_dir / "waveform.csv"
    waveforms.write_csv(table, csv_path)
    return {
        "ok": True,
        "reason": "simulation_passed",
        "backend": "ltspice",
        "waveform_csv": str(csv_path),
        "metrics": {
            "theory_tau_s": 0.001,
            "measured_tau_s": 0.001,
            "tau_error_percent": 0.0,
        },
        "validation": {"status": "PASS"},
    }


class SweepValidationTests(unittest.TestCase):
    def test_supported_sweep_matrix_and_limits(self):
        validated = sweeps.validate_request(
            {
                "circuit_type": "rc_lowpass",
                "parameter": "resistance",
                "values": ["1k", "2k"],
            }
        )
        self.assertEqual(validated["values"], ["1k", "2k"])

        for parameter in ("inductance", "vin"):
            with self.assertRaisesRegex(RuntimeError, "supported sweep"):
                sweeps.validate_request(
                    {
                        "circuit_type": "rc_lowpass",
                        "parameter": parameter,
                        "values": ["1", "2"],
                    }
                )

        with self.assertRaisesRegex(RuntimeError, "2 through 20"):
            sweeps.validate_request(
                {
                    "circuit_type": "buck_converter",
                    "parameter": "duty_cycle",
                    "values": [0.4],
                }
            )

    def test_duplicates_are_rejected_after_numeric_normalization(self):
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            sweeps.validate_request(
                {
                    "circuit_type": "rc_lowpass",
                    "parameter": "resistance",
                    "values": ["1k", "1000"],
                }
            )

    def test_invalid_duty_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "0 < duty_cycle < 1"):
            sweeps.validate_request(
                {
                    "circuit_type": "buck_converter",
                    "parameter": "duty_cycle",
                    "values": [0.4, 1.0],
                }
            )


class SweepExecutionTests(unittest.TestCase):
    def test_sweep_writes_summary_plot_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            def fake_run(request, point_dir, value):
                return _successful_point(point_dir, value)

            with mock.patch.object(sweeps, "_run_point", side_effect=fake_run):
                result = sweeps.run_sweep(_request(tmp, ["1k", "2k"]))
                artifacts_exist = all(
                    Path(path).exists()
                    for path in (
                        result["summary_csv"],
                        result["plot"]["path"],
                        result["report"]["path"],
                    )
                )
                summary = Path(result["summary_csv"]).read_text(encoding="utf-8")

        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["ok"])
        self.assertTrue(artifacts_exist)
        self.assertIn("tau_error_percent", summary.splitlines()[0])
        self.assertEqual([point["value"] for point in result["points"]], ["1k", "2k"])

    def test_sweep_continues_after_one_failed_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []

            def fake_run(request, point_dir, value):
                calls.append(value)
                if value == "2k":
                    return {
                        "ok": False,
                        "reason": "simulation_failed",
                        "backend": "ltspice",
                    }
                return _successful_point(point_dir, value)

            with mock.patch.object(sweeps, "_run_point", side_effect=fake_run):
                result = sweeps.run_sweep(_request(tmp))

        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["ok"])
        self.assertEqual(calls, ["1k", "2k", "3k"])
        self.assertEqual(len(result["points"]), 3)
        self.assertEqual(result["points"][1]["reason"], "simulation_failed")

    def test_point_directories_are_collision_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            directories = []

            def fake_run(request, point_dir, value):
                directories.append(point_dir.name)
                return _successful_point(point_dir, value)

            with mock.patch.object(sweeps, "_run_point", side_effect=fake_run):
                sweeps.run_sweep(_request(tmp, ["1k", "2k"]))

        self.assertEqual(directories, ["point-01-1k", "point-02-2k"])

    def test_existing_summary_requires_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "sweep_summary.csv").write_text("existing\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                sweeps.run_sweep(_request(tmp, ["1k", "2k"]))


if __name__ == "__main__":
    unittest.main()
