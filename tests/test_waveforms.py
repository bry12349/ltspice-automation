import csv
import math
import struct
import tempfile
import unittest
from pathlib import Path

from mcp import waveforms


FIXTURES = Path(__file__).parent / "fixtures"


def _rc_table():
    rows = []
    for index in range(601):
        time_s = index * 0.00001
        rows.append([time_s, 1.0 - math.exp(-time_s / 0.001)])
    return {"columns": ["time_s", "V(out)"], "rows": rows}


def _buck_table():
    rows = []
    for index in range(101):
        time_s = index * 0.0001
        startup = min(1.0, time_s / 0.003)
        ripple = 0.05 * math.sin(2 * math.pi * 10_000 * time_s + math.pi / 4)
        rows.append([time_s, startup * 5.0 + ripple, startup * 1.0 + ripple])
    return {"columns": ["time_s", "V(out)", "I(L1)"], "rows": rows}


class WaveformParserTests(unittest.TestCase):
    def test_parsers_normalize_time_and_signal_names(self):
        ngspice = waveforms.read_waveform(FIXTURES / "ngspice_rc_wrdata.txt", "ngspice")
        ltspice = waveforms.read_waveform(FIXTURES / "ltspice_rc_ascii.txt", "ltspice")

        self.assertEqual(ngspice["columns"][:2], ["time_s", "V(out)"])
        self.assertEqual(ltspice["columns"], ["time_s", "V(out)"])
        self.assertAlmostEqual(ltspice["rows"][1][1], 0.6321206)

    def test_non_monotonic_time_is_rejected(self):
        table = {
            "columns": ["time_s", "V(out)"],
            "rows": [[0.0, 0.0], [1.0, 1.0], [0.5, 0.8]],
        }

        with self.assertRaisesRegex(RuntimeError, "strictly increasing"):
            waveforms.validate_table(table)

    def test_non_finite_values_are_rejected(self):
        table = {
            "columns": ["time_s", "V(out)"],
            "rows": [[0.0, 0.0], [1.0, float("nan")]],
        }

        with self.assertRaisesRegex(RuntimeError, "finite"):
            waveforms.validate_table(table)

    def test_ltspice_binary_raw_is_normalized(self):
        header = "\n".join(
            [
                "Title: binary fixture",
                "Plotname: Transient Analysis",
                "Flags: real forward",
                "No. Variables: 2",
                "No. Points: 3",
                "Variables:",
                "\t0\ttime\ttime",
                "\t1\tV(out)\tvoltage",
                "Binary:",
                "",
            ]
        ).encode("utf-16le")
        payload = b"".join(
            struct.pack("<df", time_s, voltage)
            for time_s, voltage in ((0.0, 0.0), (0.001, 0.6321206), (0.005, 0.9932621))
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.raw"
            path.write_bytes(header + payload)
            table = waveforms.read_waveform(path, "ltspice")

        self.assertEqual(table["columns"], ["time_s", "V(out)"])
        self.assertEqual(len(table["rows"]), 3)
        self.assertAlmostEqual(table["rows"][1][1], 0.6321206, places=6)


class WaveformArtifactTests(unittest.TestCase):
    def test_csv_and_svg_are_deterministic(self):
        table = {
            "columns": ["time_s", "V(out)"],
            "rows": [[0.0, 0.0], [0.001, 0.63], [0.005, 0.99]],
        }
        with tempfile.TemporaryDirectory() as tmp:
            csv_result = waveforms.write_csv(table, Path(tmp) / "wave.csv")
            svg_result = waveforms.write_svg(
                [{"label": "R=1k", "table": table, "signal": "V(out)"}],
                Path(tmp) / "wave.svg",
                "RC sweep",
                "Time (s)",
                "Voltage (V)",
            )
            csv_text = Path(csv_result["path"]).read_text(encoding="utf-8")
            svg_text = Path(svg_result["path"]).read_text(encoding="utf-8")

        self.assertEqual(csv_text.splitlines()[0], "time_s,V(out)")
        self.assertIn("<svg", svg_text)
        self.assertIn("R=1k", svg_text)
        self.assertIn("RC sweep", svg_text)

    def test_csv_round_trip_preserves_numeric_data(self):
        table = _rc_table()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "wave.csv"
            waveforms.write_csv(table, path)
            loaded = waveforms.read_csv(path)

        self.assertEqual(loaded["columns"], table["columns"])
        self.assertEqual(len(loaded["rows"]), len(table["rows"]))
        self.assertAlmostEqual(loaded["rows"][100][1], table["rows"][100][1])

    def test_downsample_keeps_endpoints_and_extrema(self):
        table = {
            "columns": ["time_s", "V(out)"],
            "rows": [[float(index), 100.0 if index == 50 else float(index % 7)] for index in range(100)],
        }

        reduced = waveforms.downsample(table, "V(out)", max_points=12)

        self.assertEqual(reduced["rows"][0], table["rows"][0])
        self.assertEqual(reduced["rows"][-1], table["rows"][-1])
        self.assertIn([50.0, 100.0], reduced["rows"])
        self.assertLessEqual(len(reduced["rows"]), 12)

    def test_export_from_args_writes_csv_plot_and_rc_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = waveforms.export_from_args(
                {
                    "input_path": str(FIXTURES / "ltspice_rc_ascii.txt"),
                    "backend": "ltspice",
                    "output_path": str(Path(tmp) / "export.csv"),
                    "plot_path": str(Path(tmp) / "export.svg"),
                    "signal": "V(out)",
                    "circuit_type": "rc_lowpass",
                    "parameters": {
                        "vin": "1",
                        "resistance": "1k",
                        "capacitance": "1u",
                    },
                }
            )
            artifacts_exist = Path(result["csv"]["path"]).exists() and Path(result["plot"]["path"]).exists()

        self.assertTrue(artifacts_exist)
        self.assertLess(result["metrics"]["tau_error_percent"], 1.0)


class MetricTests(unittest.TestCase):
    def test_rc_metrics_find_tau_and_rise_time(self):
        result = waveforms.rc_metrics(
            _rc_table(),
            vin=1.0,
            resistance=1000.0,
            capacitance=1e-6,
        )

        self.assertAlmostEqual(result["theory_tau_s"], 0.001)
        self.assertLess(result["tau_error_percent"], 1.0)
        self.assertGreater(result["rise_time_10_90_s"], 0.002)
        self.assertAlmostEqual(result["final_voltage_v"], 1.0, places=2)

    def test_buck_metrics_use_only_steady_state_window(self):
        result = waveforms.buck_metrics(
            _buck_table(),
            vin=12.0,
            duty_cycle=5.0 / 12.0,
            steady_from=0.004,
        )

        self.assertAlmostEqual(result["vout_average_v"], 5.0, places=1)
        self.assertGreater(result["vout_ripple_pp_v"], 0.0)
        self.assertIn("inductor_current_peak_a", result)
        self.assertAlmostEqual(result["ideal_vout_v"], 5.0)

    def test_buck_metrics_require_output_and_inductor_current(self):
        table = {"columns": ["time_s", "V(out)"], "rows": [[0.0, 0.0], [1.0, 5.0]]}

        with self.assertRaisesRegex(RuntimeError, r"I\(L1\)"):
            waveforms.buck_metrics(table, vin=12.0, duty_cycle=0.5, steady_from=0.5)


if __name__ == "__main__":
    unittest.main()
