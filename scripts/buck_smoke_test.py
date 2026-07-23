#!/usr/bin/env python3
import json
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from mcp import buck
from mcp import server
from mcp import waveforms


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

    visible_run = server.tool_run_simulation(
        {"input_path": result["path"], "timeout_seconds": 120}
    )
    if not visible_run.get("ok"):
        raise RuntimeError(f"Visible Buck schematic simulation failed: {visible_run}")
    visible_log = server.tool_parse_log(
        {"log_path": str(Path(result["path"]).with_suffix(".log"))}
    )
    if visible_log["warnings"] or visible_log["errors"]:
        raise RuntimeError(
            "Visible Buck schematic has simulator diagnostics: "
            f"warnings={visible_log['warnings']}, errors={visible_log['errors']}"
        )
    visible_table = waveforms.read_waveform(
        Path(result["path"]).with_suffix(".raw"),
        "ltspice",
    )
    visible_metrics = waveforms.buck_metrics(
        visible_table,
        result["parameters"]["vin_v"],
        result["parameters"]["duty_cycle"],
        result["parameters"]["steady_from_s"],
    )
    if visible_metrics["conversion_error_percent"] > 10.0:
        raise RuntimeError(
            f"Visible Buck schematic metrics failed: {visible_metrics}"
        )

    print("Buck smoke test passed")
    print(
        json.dumps(
            {
                "portable_metrics": result["metrics"],
                "visible_schematic_metrics": visible_metrics,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(result["path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
