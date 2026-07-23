import math
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import backends
from mcp import buck


class BuckParameterTests(unittest.TestCase):
    def test_defaults_target_twelve_to_five_volts(self):
        values = buck.validate_parameters({})

        self.assertEqual(values["vin_v"], 12.0)
        self.assertAlmostEqual(values["duty_cycle"], 5.0 / 12.0)
        self.assertEqual(values["switching_frequency_hz"], 100_000.0)
        self.assertGreater(values["inductance_h"], 0.0)

    def test_invalid_duty_is_rejected_before_files_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "0 < duty_cycle < 1"):
                buck.create_buck(Path(tmp), "bad", {"duty_cycle": 1.0})

            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_undersampled_switching_period_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "100 points per switching period"):
            buck.validate_parameters({"switching_frequency": "100k", "max_step": "1u"})


class BuckGenerationTests(unittest.TestCase):
    def test_buck_generates_portable_netlist_and_visible_schematic(self):
        values = buck.validate_parameters({})
        netlist = buck.render_netlist(values)
        schematic = "\n".join(buck.render_schematic(values, "Buck converter"))

        self.assertIn("S1 vin sw gate 0 SWMOD", netlist)
        self.assertIn("D1 0 sw DMOD", netlist)
        self.assertIn("L1 sw out", netlist)
        self.assertIn("C1 out 0", netlist)
        self.assertIn(".tran 100n 10m 0 100n", netlist)
        self.assertNotIn(".tran 100n 10m 0 100n startup", netlist)
        self.assertIn(".save V(out) V(gate) I(L1)", netlist)
        self.assertIn("SYMBOL sw", schematic)
        self.assertIn("SYMATTR InstName L1", schematic)
        self.assertIn("WIRE 256 224 320 224", schematic)
        self.assertIn("WIRE 384 224 496 224", schematic)
        self.assertIn("FLAG 384 224 out", schematic)
        self.assertIn("FLAG 208 160 0", schematic)

    def test_create_without_simulation_writes_both_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = buck.create_buck(Path(tmp), "buck-demo", {}, simulate=False)
            asc_text = Path(result["path"]).read_text(encoding="utf-8")
            cir_text = Path(result["netlist_path"]).read_text(encoding="utf-8")

        self.assertEqual(result["circuit_type"], "buck_converter")
        self.assertEqual(result["simulation_status"]["reason"], "simulation_not_requested")
        self.assertIn("Version 4", asc_text)
        self.assertIn("S1 vin sw gate 0 SWMOD", cir_text)

    def test_create_from_args_uses_requested_schematic_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = buck.create_buck_from_args(
                {
                    "output_dir": tmp,
                    "filename": "titled",
                    "title": "Lab Buck Sweep",
                    "simulate": False,
                }
            )
            asc_text = Path(result["path"]).read_text(encoding="utf-8")

        self.assertIn(";Lab Buck Sweep", asc_text)

    def test_existing_inputs_are_not_overwritten_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "buck.asc").write_text("existing\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Refusing to overwrite"):
                buck.create_buck(Path(tmp), "buck", {})


class BuckAnalysisTests(unittest.TestCase):
    @staticmethod
    def _fake_run(input_path, backend, **kwargs):
        raw_path = Path(input_path).with_suffix(".raw")
        rows = ["time V(out) I(L1) V(gate)"]
        for index in range(1001):
            time_s = index * 0.00001
            startup = min(1.0, time_s / 0.003)
            ripple = 0.04 * math.sin(2 * math.pi * 10_000 * time_s + math.pi / 4)
            rows.append(
                f"{time_s:.9g} {startup * 5.0 + ripple:.9g} "
                f"{startup * 1.0 + ripple:.9g} {5.0 if index % 2 else 0.0}"
            )
        raw_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        return {
            "ok": True,
            "reason": "simulation_passed",
            "backend": "ngspice",
            "raw_path": str(raw_path),
            "returncode": 0,
            "command": ["ngspice", "-b", str(input_path)],
            "cwd": str(Path(input_path).parent),
            "stdout": "",
            "stderr": "",
        }

    def test_create_buck_returns_waveform_metrics_plot_and_report(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            backends, "run_portable", side_effect=self._fake_run
        ):
            result = buck.create_buck(
                Path(tmp),
                "buck",
                {},
                simulate=True,
                backend="ngspice",
            )
            artifacts_exist = all(
                Path(path).exists()
                for path in (
                    result["waveform_csv"],
                    result["metrics_json"],
                    result["plot"]["path"],
                    result["report"]["path"],
                )
            )
            report_text = Path(result["report"]["path"]).read_text(encoding="utf-8")

        self.assertTrue(result["simulation_status"]["ok"])
        self.assertEqual(result["validation"]["status"], "PASS")
        self.assertTrue(artifacts_exist)
        self.assertAlmostEqual(result["metrics"]["vout_average_v"], 5.0, places=1)
        self.assertIn("Simplified Model Limitations", report_text)
        self.assertIn("D * Vin", report_text)

    def test_failed_simulation_does_not_create_validation_pass(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            backends,
            "run_portable",
            return_value={"ok": False, "reason": "waveform_missing", "backend": "ngspice"},
        ):
            result = buck.create_buck(
                Path(tmp),
                "buck",
                {},
                simulate=True,
                backend="ngspice",
            )

        self.assertFalse(result["simulation_status"]["ok"])
        self.assertNotIn("validation", result)


if __name__ == "__main__":
    unittest.main()
