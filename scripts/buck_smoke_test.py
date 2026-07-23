#!/usr/bin/env python3
import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from mcp import buck


OUT = PLUGIN_ROOT / "work" / "buck-smoke"


def main() -> int:
    result = buck.create_buck(
        OUT,
        "buck-smoke",
        {},
        overwrite=True,
        simulate=True,
        backend="ltspice",
        timeout_seconds=120,
    )
    if not result.get("simulation_status", {}).get("ok"):
        raise RuntimeError(f"LTspice Buck simulation failed: {result}")
    if result.get("validation", {}).get("status") != "PASS":
        raise RuntimeError(f"Buck validation did not pass: {result.get('validation')}")
    for key in ("waveform_csv", "metrics_json"):
        if not Path(result[key]).exists():
            raise RuntimeError(f"Missing Buck artifact: {key}")
    for key in ("plot", "report"):
        if not Path(result[key]["path"]).exists():
            raise RuntimeError(f"Missing Buck artifact: {key}")
    print("Buck smoke test passed")
    print(json.dumps(result["metrics"], indent=2, sort_keys=True))
    print(result["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
