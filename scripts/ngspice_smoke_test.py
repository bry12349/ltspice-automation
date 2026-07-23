#!/usr/bin/env python3
import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from mcp import backends
from mcp import buck
from mcp import portable


OUT = PLUGIN_ROOT / "work" / "ngspice-smoke"


def main() -> int:
    detected = backends.detect_simulators()
    if not detected["ngspice"]["found"]:
        raise RuntimeError("ngspice is required for this smoke test")

    rc_result = portable.run_rc_case(
        OUT / "rc",
        {"resistance": "1k", "capacitance": "1u", "vin": "1"},
        "ngspice",
        timeout_seconds=60,
    )
    if not rc_result.get("ok"):
        raise RuntimeError(f"ngspice RC simulation failed: {rc_result}")
    if rc_result["metrics"]["tau_error_percent"] > 2.0:
        raise RuntimeError(f"ngspice RC tau validation failed: {rc_result['metrics']}")

    buck_result = buck.create_buck(
        OUT / "buck",
        "buck",
        {},
        overwrite=True,
        simulate=True,
        backend="ngspice",
        timeout_seconds=120,
    )
    if not buck_result.get("simulation_status", {}).get("ok"):
        raise RuntimeError(f"ngspice Buck simulation failed: {buck_result}")
    if buck_result.get("validation", {}).get("status") != "PASS":
        raise RuntimeError(f"ngspice Buck validation failed: {buck_result.get('validation')}")

    print("ngspice smoke test passed")
    print(
        json.dumps(
            {
                "ngspice_version": detected["ngspice"]["version"],
                "rc_metrics": rc_result["metrics"],
                "buck_metrics": buck_result["metrics"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
