import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import backends
from mcp import portable


FIXTURE = Path(__file__).parent / "fixtures" / "ltspice_rc_ascii.txt"


class PortableRcTests(unittest.TestCase):
    def test_rc_netlist_is_accepted_by_both_backends(self):
        text = portable.rc_netlist("1k", "1u", "1")

        self.assertIn("V1 in 0 PULSE(0 1", text)
        self.assertIn("R1 in out 1k", text)
        self.assertIn("C1 out 0 1u", text)
        self.assertIn(".tran 0 6m 0 10u", text)
        self.assertIn(".save V(out)", text)
        self.assertTrue(text.rstrip().endswith(".end"))

    def test_rc_netlist_rejects_non_positive_components(self):
        for resistance, capacitance in (("0", "1u"), ("1k", "-1u")):
            with self.assertRaisesRegex(RuntimeError, "must be positive"):
                portable.rc_netlist(resistance, capacitance, "1")

    def test_spice_number_supports_engineering_suffixes(self):
        self.assertEqual(portable.spice_number("2k"), 2000.0)
        self.assertAlmostEqual(portable.spice_number("10u"), 10e-6)
        self.assertEqual(portable.spice_number("3Meg"), 3e6)

    def test_run_rc_case_returns_csv_plot_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            backends,
            "run_portable",
            return_value={
                "ok": True,
                "reason": "simulation_passed",
                "backend": "ltspice",
                "raw_path": str(FIXTURE),
                "log_path": None,
            },
        ):
            result = portable.run_rc_case(
                Path(tmp),
                {"resistance": "1k", "capacitance": "1u", "vin": "1"},
                "ltspice",
            )

            metrics = json.loads(Path(result["metrics_json"]).read_text(encoding="utf-8"))
            waveform_exists = Path(result["waveform_csv"]).exists()
            plot_exists = Path(result["plot"]["path"]).exists()

        self.assertTrue(result["ok"])
        self.assertTrue(waveform_exists)
        self.assertTrue(plot_exists)
        self.assertLess(result["metrics"]["tau_error_percent"], 1.0)
        self.assertEqual(metrics, result["metrics"])

    def test_run_rc_case_propagates_simulation_failure(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            backends,
            "run_portable",
            return_value={
                "ok": False,
                "reason": "waveform_missing",
                "backend": "ngspice",
            },
        ):
            result = portable.run_rc_case(
                Path(tmp),
                {"resistance": "1k", "capacitance": "1u", "vin": "1"},
                "ngspice",
            )
            netlist_exists = Path(result["netlist_path"]).exists()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "waveform_missing")
        self.assertNotIn("metrics", result)
        self.assertTrue(netlist_exists)


if __name__ == "__main__":
    unittest.main()
