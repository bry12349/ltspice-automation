import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import reporting
from mcp import server


class RcReportTests(unittest.TestCase):
    def test_rc_default_report_is_saved_next_to_schematic(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "rc-default.log"
            log_path.write_text("placeholder\n", encoding="utf-8")
            fake_log = {
                "warnings": [],
                "errors": [],
                "measurements": {
                    "vout_at_1ms": "V(out) =0.631937 at 0.001",
                    "vout_at_5ms": "V(out) =0.993259 at 0.005",
                    "tau_cross": "V(out)=0.632121 AT 0.0010005",
                },
            }
            with mock.patch.object(server, "tool_run_simulation", return_value={"returncode": 0}), mock.patch.object(
                server, "tool_parse_log", return_value=fake_log
            ), mock.patch.object(reporting, "generate_rc_lowpass_report", return_value={"path": "ignored"}) as generate:
                server.tool_create_schematic_from_description(
                    {
                        "description": "Generate a 1V step RC low-pass circuit",
                        "output_dir": tmp,
                        "filename": "rc-default",
                        "overwrite": True,
                        "open": False,
                        "simulate": True,
                    }
                )

        self.assertEqual(generate.call_args.args[1], Path(tmp).resolve() / "rc-default_report.md")

    def test_generate_rc_report_writes_required_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "rc_lowpass_report.md"
            result = {
                "path": str(Path(tmp) / "rc.asc"),
                "circuit_type": "rc_lowpass",
                "component_values": {
                    "R1": "1k",
                    "C1": "1u",
                    "V1": "PULSE(0 1 0 1u 1u 10m 20m)",
                },
                "analysis": ".tran 0 6m 0 10u",
                "simulation_status": {"ok": True, "reason": "simulation_passed"},
                "log": {
                    "warnings": [],
                    "errors": [],
                    "measurements": {
                        "vout_at_1ms": "V(out) =0.631937031823 at 0.001",
                        "vout_at_5ms": "V(out) =0.993258907545 at 0.005",
                        "tau_cross": "V(out)=0.632120558  AT 0.00100049696698",
                    },
                },
            }

            generated = reporting.generate_rc_lowpass_report(result, report_path)
            text = Path(generated["path"]).read_text(encoding="utf-8")

        self.assertEqual(generated["path"], str(report_path))
        required_sections = [
            "# RC Low-Pass Simulation Report",
            "## Circuit Parameters",
            "## Simulation Settings",
            "## Measurement Results",
            "## Theory vs Simulation",
            "## Warning/Error Summary",
            "## Engineering Conclusion",
            "## Follow-Up Improvements",
        ]
        for section in required_sections:
            self.assertIn(section, text)
        self.assertIn("## Validation Summary", text)
        self.assertIn("Overall result: `PASS`", text)
        self.assertIn("## Reproduction", text)
        self.assertIn("tau = R * C = 0.001 s", text)
        self.assertIn("vout_at_1ms", text)
        self.assertIn("0.631937", text)
        self.assertIn("0.632121", text)

    def test_create_schematic_from_description_generates_report_after_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "reports" / "rc_lowpass_report.md"
            log_path = Path(tmp) / "rc-report.log"
            log_path.write_text("placeholder\n", encoding="utf-8")
            fake_log = {
                "warnings": [],
                "errors": [],
                "measurements": {
                    "vout_at_1ms": "V(out) =0.631937031823 at 0.001",
                    "vout_at_5ms": "V(out) =0.993258907545 at 0.005",
                    "tau_cross": "V(out)=0.632120558  AT 0.00100049696698",
                },
            }
            with mock.patch.object(server, "tool_run_simulation", return_value={"returncode": 0}), mock.patch.object(
                server, "tool_parse_log", return_value=fake_log
            ):
                result = server.tool_create_schematic_from_description(
                    {
                        "description": "Generate a 1V step RC low-pass circuit with R=1k and C=1uF",
                        "output_dir": tmp,
                        "filename": "rc-report",
                        "overwrite": True,
                        "open": False,
                        "simulate": True,
                        "report_path": str(report_path),
                    }
                )

            text = report_path.read_text(encoding="utf-8")

        self.assertEqual(result["report"]["path"], str(report_path.resolve()))
        self.assertIn("# RC Low-Pass Simulation Report", text)
        self.assertIn("## Engineering Conclusion", text)

    def test_create_schematic_from_description_skips_report_without_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = server.tool_create_schematic_from_description(
                {
                    "description": "Generate a 1V step RC low-pass circuit with R=1k and C=1uF",
                    "output_dir": tmp,
                    "filename": "rc-report",
                    "overwrite": True,
                    "open": False,
                    "simulate": False,
                }
            )

        self.assertIsNone(result["report"])
