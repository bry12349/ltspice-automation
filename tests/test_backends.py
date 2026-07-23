import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import backends


class BackendSelectionTests(unittest.TestCase):
    def test_ngspice_version_skips_banner_lines(self):
        completed = subprocess.CompletedProcess(
            [],
            0,
            "******\n** ngspice-46 : Circuit level simulation program\n******\n",
            "",
        )
        with mock.patch.object(backends.subprocess, "run", return_value=completed):
            version = backends._command_version(Path("/usr/bin/ngspice"))

        self.assertEqual(version, "ngspice 46")

    def test_auto_prefers_ltspice_then_ngspice(self):
        both = {
            "ltspice": {"found": True, "executable": "/Applications/LTspice"},
            "ngspice": {"found": True, "executable": "/usr/bin/ngspice"},
        }
        ngspice_only = {
            "ltspice": {"found": False, "executable": None},
            "ngspice": {"found": True, "executable": "/usr/bin/ngspice"},
        }

        with mock.patch.object(backends.sys, "platform", "darwin"):
            self.assertEqual(backends.select_backend("auto", both), "ltspice")
        self.assertEqual(backends.select_backend("auto", ngspice_only), "ngspice")

    def test_auto_prefers_ngspice_on_linux_when_both_are_available(self):
        both = {
            "ltspice": {"found": True, "executable": "/usr/bin/LTspice"},
            "ngspice": {"found": True, "executable": "/usr/bin/ngspice"},
        }
        with mock.patch.object(backends.sys, "platform", "linux"):
            self.assertEqual(backends.select_backend("auto", both), "ngspice")

    def test_explicit_missing_backend_fails(self):
        detected = {
            "ltspice": {"found": False, "executable": None},
            "ngspice": {"found": True, "executable": "/usr/bin/ngspice"},
        }

        with self.assertRaisesRegex(RuntimeError, "LTspice backend is not available"):
            backends.select_backend("ltspice", detected)

    def test_unknown_backend_fails(self):
        with self.assertRaisesRegex(RuntimeError, "auto, ltspice, or ngspice"):
            backends.select_backend("xyce", {})


class PortableRunTests(unittest.TestCase):
    def _detections(self, backend):
        return {
            "ltspice": {
                "found": backend == "ltspice",
                "executable": "/Applications/LTspice.app/Contents/MacOS/LTspice" if backend == "ltspice" else None,
            },
            "ngspice": {
                "found": backend == "ngspice",
                "executable": "/usr/bin/ngspice" if backend == "ngspice" else None,
            },
        }

    def test_ngspice_command_requires_fresh_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            circuit = Path(tmp) / "case.cir"
            circuit.write_text("* case\n.end\n", encoding="utf-8")
            circuit.with_suffix(".raw").write_text("stale", encoding="utf-8")
            completed = subprocess.CompletedProcess([], 0, "", "")

            with mock.patch.object(
                backends, "detect_simulators", return_value=self._detections("ngspice")
            ), mock.patch.object(backends.subprocess, "run", return_value=completed):
                result = backends.run_portable(circuit, backend="ngspice")

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "waveform_missing")
        self.assertNotIn("raw_path", result)

    def test_ngspice_success_returns_normalized_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            circuit = Path(tmp) / "case.cir"
            circuit.write_text("* case\n.end\n", encoding="utf-8")

            def fake_run(command, cwd, text, capture_output, timeout, env):
                self.assertEqual(env["SPICE_ASCIIRAWFILE"], "1")
                raw_path = Path(command[command.index("-r") + 1])
                raw_path.write_text("fresh waveform\n", encoding="utf-8")
                Path(command[command.index("-o") + 1]).write_text("ngspice log\n", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "done", "")

            with mock.patch.object(
                backends, "detect_simulators", return_value=self._detections("ngspice")
            ), mock.patch.object(backends.subprocess, "run", side_effect=fake_run):
                result = backends.run_portable(circuit, backend="ngspice")

        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "simulation_passed")
        self.assertEqual(result["backend"], "ngspice")
        self.assertEqual(result["command"][1:3], ["-b", "-o"])
        self.assertTrue(result["raw_path"].endswith("case.raw"))
        self.assertTrue(result["log_path"].endswith("case.log"))
        self.assertIn("duration_seconds", result)
        self.assertIn("version", result)
        self.assertEqual(result["fresh_outputs"], ["raw", "log"])

    def test_fatal_log_diagnostic_cannot_pass_with_fresh_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            circuit = Path(tmp) / "case.cir"
            circuit.write_text("* case\n.end\n", encoding="utf-8")

            def fake_run(command, cwd, text, capture_output, timeout, env):
                raw_path = Path(command[command.index("-r") + 1])
                raw_path.write_text("fresh waveform\n", encoding="utf-8")
                Path(command[command.index("-o") + 1]).write_text(
                    "Error: singular matrix\n", encoding="utf-8"
                )
                return subprocess.CompletedProcess(command, 0, "", "")

            detections = self._detections("ngspice")
            detections["ngspice"]["version"] = "ngspice 46"
            with mock.patch.object(
                backends, "detect_simulators", return_value=detections
            ), mock.patch.object(backends.subprocess, "run", side_effect=fake_run):
                result = backends.run_portable(circuit, backend="ngspice")

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "simulator_log_error")
        self.assertEqual(result["log_errors"], ["Error: singular matrix"])

    def test_ltspice_uses_binary_batch_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            circuit = Path(tmp) / "case.cir"
            circuit.write_text("* case\n.end\n", encoding="utf-8")

            def fake_run(command, cwd, text, capture_output, timeout, env):
                circuit.with_suffix(".raw").write_text("fresh waveform\n", encoding="utf-8")
                circuit.with_suffix(".log").write_text("ltspice log\n", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(
                backends, "detect_simulators", return_value=self._detections("ltspice")
            ), mock.patch.object(backends.subprocess, "run", side_effect=fake_run):
                result = backends.run_portable(circuit, backend="ltspice")

        self.assertTrue(result["ok"])
        self.assertEqual(result["command"][1], "-b")
        self.assertNotIn("-ascii", result["command"])

    def test_non_positive_timeout_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            circuit = Path(tmp) / "case.cir"
            circuit.write_text("* case\n.end\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "timeout_seconds must be positive"):
                backends.run_portable(circuit, timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()
