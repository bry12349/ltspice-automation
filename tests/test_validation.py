import tempfile
import unittest
from pathlib import Path

from mcp import server
from mcp import validation


class ValidationTests(unittest.TestCase):
    def test_rc_validation_marks_clean_measurements_as_pass(self):
        result = {
            "circuit_type": "rc_lowpass",
            "component_values": {
                "R1": "1k",
                "C1": "1u",
                "V1": "PULSE(0 1 0 1u 1u 10m 20m)",
            },
            "log": {
                "measurements": {
                    "vout_at_1ms": "V(out) =0.631937031823 at 0.001",
                    "vout_at_5ms": "V(out) =0.993258907545 at 0.005",
                    "tau_cross": "V(out)=0.632120558  AT 0.00100049696698",
                }
            },
        }

        summary = validation.validate_result(result, tolerance_percent=1.0)

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["tolerance_percent"], 1.0)
        self.assertLess(summary["max_error_percent"], 0.1)
        self.assertEqual(summary["checks"][0]["status"], "PASS")

    def test_rl_validation_reports_missing_measurement_as_fail(self):
        result = {
            "circuit_type": "rl_step_response",
            "component_values": {
                "R1": "10",
                "L1": "10m",
                "V1": "PULSE(0 5 0 1u 1u 10m 20m)",
            },
            "log": {
                "measurements": {
                    "i_at_1tau": "I(L1) =0.316060 at 0.001",
                }
            },
        }

        summary = validation.validate_result(result, tolerance_percent=1.0)

        self.assertFalse(summary["passed"])
        missing = [check for check in summary["checks"] if check["status"] == "MISSING"]
        self.assertTrue(any(check["measurement"] == "i_at_5tau" for check in missing))

    def test_unknown_circuit_validation_returns_fail(self):
        summary = validation.validate_result({"circuit_type": "unknown"}, tolerance_percent=1.0)

        self.assertEqual(summary["status"], "FAIL")
        self.assertEqual(summary["checks"], [])


class FixtureLogParsingTests(unittest.TestCase):
    def test_parse_log_fixture_extracts_warning_error_and_measurement(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "fixture.log"
            log_path.write_text(
                "\n".join(
                    [
                        "Circuit: /tmp/example.net",
                        "solver: Normal",
                        "temp: 27",
                        "Warning: timestep reduced",
                        "vout_at_1ms: V(out)=0.631937 at 0.001",
                        "Fatal Error: node out is floating",
                    ]
                ),
                encoding="utf-8",
            )

            parsed = server.tool_parse_log({"log_path": str(log_path)})

        self.assertEqual(parsed["measurements"]["vout_at_1ms"], "V(out)=0.631937 at 0.001")
        self.assertNotIn("Circuit", parsed["measurements"])
        self.assertNotIn("solver", parsed["measurements"])
        self.assertNotIn("temp", parsed["measurements"])
        self.assertEqual(len(parsed["warnings"]), 1)
        self.assertEqual(len(parsed["errors"]), 1)


if __name__ == "__main__":
    unittest.main()
