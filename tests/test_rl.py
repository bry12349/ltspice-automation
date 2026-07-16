import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import reporting
from mcp import server


class RlTemplateTests(unittest.TestCase):
    def test_rl_default_report_is_saved_next_to_schematic(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "rl-default.log"
            log_path.write_text("placeholder\n", encoding="utf-8")
            fake_log = {
                "warnings": [],
                "errors": [],
                "measurements": {
                    "i_at_1tau": "I(L1) =0.316060 at 0.001",
                    "i_at_5tau": "I(L1) =0.496631 at 0.005",
                    "tau_cross": "I(L1)=0.31606 AT 0.0010001",
                    "final_current": "I(L1) =0.496631 at 0.005",
                },
            }
            with mock.patch.object(server, "tool_run_simulation", return_value={"returncode": 0}), mock.patch.object(
                server, "tool_parse_log", return_value=fake_log
            ), mock.patch.object(reporting, "generate_rl_step_response_report", return_value={"path": "ignored"}) as generate:
                server.tool_create_schematic_from_description(
                    {
                        "description": "Generate a 5V step RL circuit with R=10 and L=10mH",
                        "output_dir": tmp,
                        "filename": "rl-default",
                        "overwrite": True,
                        "open": False,
                        "simulate": True,
                    }
                )

        self.assertEqual(generate.call_args.args[1], Path(tmp).resolve() / "rl-default_report.md")

    def test_create_rl_schematic_generates_expected_directives(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = server.tool_create_rl_schematic(
                {
                    "output_dir": tmp,
                    "filename": "rl-default",
                    "overwrite": True,
                    "resistance": "10",
                    "inductance": "10m",
                    "source": "PULSE(0 5 0 1u 1u 10m 20m)",
                }
            )
            lines = Path(result["path"]).read_text(encoding="utf-8").splitlines()

        self.assertEqual(result["circuit_type"], "rl_step_response")
        self.assertIn("SYMATTR InstName L1", lines)
        self.assertIn("SYMATTR Value 10m", lines)
        self.assertIn("TEXT 80 352 Left 2 !.tran 0 6m 0 10u", lines)
        self.assertIn("TEXT 80 384 Left 2 !.meas tran i_at_1tau FIND I(L1) AT=1m", lines)
        self.assertIn("TEXT 80 416 Left 2 !.meas tran i_at_5tau FIND I(L1) AT=5m", lines)
        self.assertIn("TEXT 80 448 Left 2 !.meas tran tau_cross WHEN I(L1)=0.31606 RISE=1", lines)
        self.assertIn("TEXT 80 480 Left 2 !.meas tran final_current FIND I(L1) AT=5m", lines)

    def test_description_can_create_rl_report_after_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "reports" / "rl_step_response_report.md"
            log_path = Path(tmp) / "rl-report.log"
            log_path.write_text("placeholder\n", encoding="utf-8")
            fake_log = {
                "warnings": [],
                "errors": [],
                "measurements": {
                    "i_at_1tau": "I(L1) =0.316060 at 0.001",
                    "i_at_5tau": "I(L1) =0.496631 at 0.005",
                    "tau_cross": "I(L1)=0.31606  AT 0.0010001",
                    "final_current": "I(L1) =0.496631 at 0.005",
                },
            }
            with mock.patch.object(server, "tool_run_simulation", return_value={"returncode": 0}), mock.patch.object(
                server, "tool_parse_log", return_value=fake_log
            ):
                result = server.tool_create_schematic_from_description(
                    {
                        "description": "Generate a 5V step RL circuit with R=10 and L=10mH",
                        "output_dir": tmp,
                        "filename": "rl-report",
                        "overwrite": True,
                        "open": False,
                        "simulate": True,
                        "report_path": str(report_path),
                    }
                )
            text = report_path.read_text(encoding="utf-8")

        self.assertEqual(result["circuit_type"], "rl_step_response")
        self.assertEqual(result["simulation_status"]["ok"], True)
        self.assertEqual(result["report"]["path"], str(report_path.resolve()))
        self.assertIn("# RL Step Response Simulation Report", text)
        self.assertIn("tau = L / R = 0.001 s", text)
        self.assertIn("i_at_1tau", text)


if __name__ == "__main__":
    unittest.main()
