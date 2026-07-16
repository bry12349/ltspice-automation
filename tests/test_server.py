import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import server


class ValueParsingTests(unittest.TestCase):
    def test_normalize_spice_value_preserves_mega_ohm(self):
        self.assertEqual(server._normalize_spice_value("1MΩ"), "1Meg")
        self.assertEqual(server._normalize_spice_value("2.2 MΩ"), "2.2Meg")

    def test_normalize_spice_value_handles_inductance_units(self):
        self.assertEqual(server._normalize_spice_value("10mH"), "10m")
        self.assertEqual(server._normalize_spice_value("2H"), "2")


class RcMeasurementTests(unittest.TestCase):
    def test_description_without_step_keyword_uses_a_step_pulse(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = server.tool_create_schematic_from_description(
                {
                    "description": "Generate a basic RC low-pass with R=1k and C=1uF",
                    "output_dir": tmp,
                    "simulate": False,
                    "open": False,
                }
            )

        self.assertTrue(result["component_values"]["V1"].startswith("PULSE(0 1 "))

    def test_create_rc_schematic_rejects_zero_capacitance(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "C must be positive"):
                server.tool_create_rc_schematic({"output_dir": tmp, "capacitance": "0"})

            self.assertEqual(list(Path(tmp).glob("*.asc")), [])

    def test_description_rejects_ac_source_before_writing_a_schematic(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "DC or step transient"):
                server.tool_create_schematic_from_description(
                    {
                        "description": "Generate an AC RC low-pass frequency response",
                        "output_dir": tmp,
                        "open": False,
                        "simulate": False,
                    }
                )

            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_description_schematic_uses_parameterized_tau_measurements(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = server.tool_create_schematic_from_description(
                {
                    "description": "Generate a 5V step RC low-pass circuit with R=2k and C=1uF",
                    "output_dir": tmp,
                    "filename": "rc-custom",
                    "overwrite": True,
                    "open": False,
                    "simulate": False,
                }
            )

            lines = Path(result["path"]).read_text(encoding="utf-8").splitlines()

        self.assertIn("TEXT 80 384 Left 2 !.meas tran vout_at_1tau FIND V(out) AT=2m", lines)
        self.assertIn("TEXT 80 416 Left 2 !.meas tran vout_at_5tau FIND V(out) AT=10m", lines)
        self.assertIn("TEXT 80 448 Left 2 !.meas tran tau_cross WHEN V(out)=3.160603 RISE=1", lines)
        self.assertIn("TEXT 80 352 Left 2 !.tran 0 12m 0 10u", lines)
        self.assertEqual(result["simulation_status"]["ok"], None)
        self.assertEqual(result["simulation_status"]["reason"], "simulation_not_requested")

    def test_default_description_schematic_keeps_existing_measurement_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = server.tool_create_schematic_from_description(
                {
                    "description": "Generate a 1V step RC low-pass circuit with R=1k and C=1uF",
                    "output_dir": tmp,
                    "filename": "rc-default",
                    "overwrite": True,
                    "open": False,
                    "simulate": False,
                }
            )

            lines = Path(result["path"]).read_text(encoding="utf-8").splitlines()

        self.assertIn("TEXT 80 384 Left 2 !.meas tran vout_at_1ms FIND V(out) AT=1m", lines)
        self.assertIn("TEXT 80 416 Left 2 !.meas tran vout_at_5ms FIND V(out) AT=5m", lines)
        self.assertIn("TEXT 80 448 Left 2 !.meas tran tau_cross WHEN V(out)=0.632121 RISE=1", lines)


class SimulationStatusTests(unittest.TestCase):
    def test_run_simulation_stages_whitespace_path_and_copies_outputs_back(self):
        with tempfile.TemporaryDirectory(prefix="ltspice test ") as tmp:
            schematic = Path(tmp) / "test circuit.asc"
            schematic.write_text("Version 4\n", encoding="utf-8")

            def fake_run(cmd, cwd, text, capture_output, timeout):
                staged = Path(cmd[-1])
                self.assertNotIn(" ", str(staged))
                staged.with_suffix(".log").write_text("measurement: value=1\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, "", "")

            with mock.patch.object(server, "_ltspice_executable", return_value=Path("/tmp/LTspice")), mock.patch.object(
                server.subprocess, "run", side_effect=fake_run
            ):
                result = server.tool_run_simulation({"input_path": str(schematic)})

            self.assertTrue(result["ok"])
            self.assertEqual(result["reason"], "simulation_passed")
            self.assertTrue(result["staged_for_whitespace"])
            self.assertTrue(schematic.with_suffix(".log").exists())

    def test_run_simulation_does_not_accept_a_stale_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            schematic = Path(tmp) / "stale.asc"
            schematic.write_text("Version 4\n", encoding="utf-8")
            schematic.with_suffix(".log").write_text("old measurement\n", encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, "", "")
            with mock.patch.object(server, "_ltspice_executable", return_value=Path("/tmp/LTspice")), mock.patch.object(
                server.subprocess, "run", return_value=completed
            ):
                result = server.tool_run_simulation({"input_path": str(schematic)})

            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "log_missing")
            self.assertFalse(schematic.with_suffix(".log").exists())

    def test_simulation_status_honors_explicit_failed_run_with_existing_log(self):
        status = server._simulation_status(
            {"returncode": 0, "ok": False, "reason": "log_missing"},
            {"errors": [], "measurements": {"peak_voltage": "8.0"}},
        )

        self.assertEqual(status, {"ok": False, "reason": "log_missing"})

    def test_description_forwards_ltspice_path_to_simulation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(server, "tool_run_simulation", return_value={"returncode": 1}) as run:
                server.tool_create_schematic_from_description(
                    {
                        "description": "Generate a 1V step RC low-pass circuit",
                        "output_dir": tmp,
                        "filename": "forward-path",
                        "overwrite": True,
                        "open": False,
                        "simulate": True,
                        "ltspice_path": "/custom/LTspice.app",
                    }
                )

        self.assertEqual(run.call_args.args[0]["ltspice_path"], "/custom/LTspice.app")

    def test_simulation_status_reports_success_from_returncode_and_clean_log(self):
        status = server._simulation_status(
            {"returncode": 0},
            {"errors": [], "measurements": {"vout_at_1ms": "V(out)=0.631"}},
        )
        self.assertEqual(status, {"ok": True, "reason": "simulation_passed"})

    def test_simulation_status_reports_missing_log(self):
        status = server._simulation_status({"returncode": 0}, None)
        self.assertEqual(status, {"ok": False, "reason": "log_missing"})


class OpenSchematicTests(unittest.TestCase):
    def test_open_schematic_reports_unsupported_platform(self):
        with tempfile.TemporaryDirectory() as tmp:
            schematic = Path(tmp) / "test.asc"
            schematic.write_text("Version 4\n", encoding="utf-8")
            with mock.patch.object(server.sys, "platform", "linux"):
                result = server.tool_open_schematic({"path": str(schematic)})

        self.assertEqual(result["returncode"], 1)
        self.assertEqual(result["unsupported_platform"], True)
        self.assertIn("macOS", result["stderr"])


if __name__ == "__main__":
    unittest.main()
