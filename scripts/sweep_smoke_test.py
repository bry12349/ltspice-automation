#!/usr/bin/env python3
import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from mcp import backends
from mcp import sweeps


OUT = PLUGIN_ROOT / "work" / "sweep-smoke"


def _require_pass(result, label):
    if result.get("status") != "PASS":
        failures = [
            {
                "value": point.get("value"),
                "reason": point.get("reason"),
                "error": point.get("error"),
            }
            for point in result.get("points", [])
            if point.get("status") != "PASS"
        ]
        raise RuntimeError(f"{label} sweep failed: {failures}")
    for key in ("summary_csv",):
        if not Path(result[key]).exists():
            raise RuntimeError(f"{label} sweep missing {key}")
    for key in ("plot", "report"):
        if not Path(result[key]["path"]).exists():
            raise RuntimeError(f"{label} sweep missing {key}")


def main() -> int:
    rc_result = sweeps.run_sweep(
        {
            "circuit_type": "rc_lowpass",
            "parameter": "resistance",
            "values": ["500", "1k", "2k"],
            "parameters": {"capacitance": "1u", "vin": "1"},
            "output_dir": str(OUT / "rc-resistance"),
            "backend": "ltspice",
            "overwrite": True,
        }
    )
    _require_pass(rc_result, "RC resistance")

    detected = backends.detect_simulators()
    buck_backend = "ngspice" if detected["ngspice"]["found"] else "ltspice"
    buck_result = sweeps.run_sweep(
        {
            "circuit_type": "buck_converter",
            "parameter": "duty_cycle",
            "values": [0.35, 5.0 / 12.0, 0.5],
            "parameters": {},
            "output_dir": str(OUT / "buck-duty"),
            "backend": buck_backend,
            "overwrite": True,
            "timeout_seconds": 120,
        }
    )
    _require_pass(buck_result, "Buck duty-cycle")

    print("Sweep smoke test passed")
    print(
        json.dumps(
            {
                "rc_backend": "ltspice",
                "buck_backend": buck_backend,
                "rc_summary": rc_result["summary_csv"],
                "buck_summary": buck_result["summary_csv"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
