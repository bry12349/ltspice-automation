import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import reporting
from mcp import server
from mcp import validation


class RlcTemplateTests(unittest.TestCase):
    def test_create_rlc_schematic_rejects_non_underdamped_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "zeta < 1"):
                server.tool_create_rlc_schematic(
                    {
                        "output_dir": tmp,
                        "resistance": "100",
                        "inductance": "10m",
                        "capacitance": "10u",
                        "source": "PULSE(0 5 0 1u 1u 100m 200m)",
                    }
                )

            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_description_rejects_non_underdamped_rlc_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "zeta < 1"):
                server.tool_create_schematic_from_description(
                    {
                        "description": "Generate a 5V step RLC circuit with R=100, L=10mH, and C=10uF",
                        "output_dir": tmp,
                        "open": False,
                        "simulate": False,
                    }
                )

            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_create_rlc_schematic_generates_expected_directives(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = server.tool_create_rlc_schematic(
                {
                    "output_dir": tmp,
                    "filename": "rlc-default",
                    "overwrite": True,
                    "resistance": "10",
                    "inductance": "10m",
                    "capacitance": "10u",
                    "source": "PULSE(0 5 0 1u 1u 100m 200m)",
                }
            )
            lines = Path(result["path"]).read_text(encoding="utf-8").splitlines()

        self.assertEqual(result["circuit_type"], "rlc_series_step")
        self.assertIn("SYMATTR InstName R1", lines)
        self.assertIn("SYMATTR InstName L1", lines)
        self.assertIn("SYMATTR InstName C1", lines)
        self.assertIn("TEXT 80 352 Left 2 !.tran 0 16m 0 10u", lines)
        self.assertIn("TEXT 80 384 Left 2 !.meas tran vout_at_peak FIND V(out) AT=1.006115m", lines)
        self.assertIn("TEXT 80 416 Left 2 !.meas tran peak_voltage MAX V(out) FROM=0 TO=16m", lines)
        self.assertIn("TEXT 80 448 Left 2 !.meas tran vout_at_settle FIND V(out) AT=8m", lines)

    def test_description_can_create_rlc_report_after_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "reports" / "rlc_series_report.md"
            log_path = Path(tmp) / "rlc-report.log"
            log_path.write_text("placeholder\n", encoding="utf-8")
            fake_log = {
                "warnings": [],
                "errors": [],
                "measurements": {
                    "vout_at_peak": "V(out) =8.023 at 0.001006115",
                    "peak_voltage": "MAX(v(out))=8.0 FROM 0 TO 0.016",
                    "vout_at_settle": "V(out) =4.912 at 0.008",
                },
            }
            with mock.patch.object(server, "tool_run_simulation", return_value={"returncode": 0}), mock.patch.object(
                server, "tool_parse_log", return_value=fake_log
            ):
                result = server.tool_create_schematic_from_description(
                    {
                        "description": "Generate a 5V step RLC circuit with R=10, L=10mH, and C=10uF",
                        "output_dir": tmp,
                        "filename": "rlc-report",
                        "overwrite": True,
                        "open": False,
                        "simulate": True,
                        "report_path": str(report_path),
                    }
                )
            text = report_path.read_text(encoding="utf-8")

        self.assertEqual(result["circuit_type"], "rlc_series_step")
        self.assertEqual(result["simulation_status"]["ok"], True)
        self.assertEqual(result["report"]["path"], str(report_path.resolve()))
        self.assertIn("# RLC Series Step Response Simulation Report", text)
        self.assertIn("Damping ratio", text)
        self.assertIn("## Validation Summary", text)

    def test_rlc_validation_checks_peak_and_settle_points(self):
        result = {
            "circuit_type": "rlc_series_step",
            "component_values": {
                "R1": "10",
                "L1": "10m",
                "C1": "10u",
                "V1": "PULSE(0 5 0 1u 1u 100m 200m)",
            },
            "log": {
                "measurements": {
                    "vout_at_peak": "V(out) =8.023 at 0.001006115",
                    "peak_voltage": "MAX(v(out))=8.023 FROM 0 TO 0.016",
                    "vout_at_settle": "V(out) =4.912 at 0.008",
                }
            },
        }

        summary = validation.validate_result(result, tolerance_percent=3.0)

        self.assertEqual(summary["status"], "PASS")
        self.assertTrue(any(check["measurement"] == "peak_voltage" for check in summary["checks"]))

    def test_generate_rlc_report_writes_required_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "rlc_report.md"
            result = {
                "path": str(Path(tmp) / "rlc.asc"),
                "circuit_type": "rlc_series_step",
                "component_values": {
                    "R1": "10",
                    "L1": "10m",
                    "C1": "10u",
                    "V1": "PULSE(0 5 0 1u 1u 100m 200m)",
                },
                "analysis": ".tran 0 16m 0 10u",
                "simulation_status": {"ok": True, "reason": "simulation_passed"},
                "log": {
                    "warnings": [],
                    "errors": [],
                    "measurements": {
                        "vout_at_peak": "V(out) =8.023 at 0.001006115",
                        "peak_voltage": "MAX(v(out))=8.023 FROM 0 TO 0.016",
                        "vout_at_settle": "V(out) =4.912 at 0.008",
                    },
                },
            }

            generated = reporting.generate_rlc_series_report(result, report_path)
            text = Path(generated["path"]).read_text(encoding="utf-8")

        self.assertIn("# RLC Series Step Response Simulation Report", text)
        self.assertIn("Natural frequency", text)
        self.assertIn("Damping ratio", text)
        self.assertIn("## Theory vs Simulation", text)
        self.assertIn("## Validation Summary", text)


if __name__ == "__main__":
    unittest.main()
