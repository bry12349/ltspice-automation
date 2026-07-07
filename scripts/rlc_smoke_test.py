#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVER = PLUGIN_ROOT / "mcp" / "server.py"
OUT = PLUGIN_ROOT / "work" / "rlc-smoke"


def call_tool(name, arguments):
    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input=json.dumps(request) + "\n",
        text=True,
        capture_output=True,
        check=True,
    )
    response = json.loads(proc.stdout)
    if "error" in response:
        raise RuntimeError(response["error"]["message"])
    text = response["result"]["content"][0]["text"]
    return json.loads(text)


def parse_first_number(text):
    match = re.search(r"=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", text)
    if not match:
        raise RuntimeError(f"Could not parse numeric measurement from: {text}")
    return float(match.group(1))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = call_tool(
        "create_schematic_from_description",
        {
            "description": "Generate a 5V step RLC circuit with R=10, L=10mH, and C=10uF",
            "output_dir": str(OUT),
            "filename": "rlc-series-smoke",
            "overwrite": True,
            "open": False,
            "simulate": True,
            "timeout_seconds": 90,
        },
    )
    if result["simulation"]["returncode"] != 0:
        raise RuntimeError("LTspice RLC simulation failed")
    errors = result["log"]["errors"]
    if errors:
        raise RuntimeError(f"LTspice RLC log errors: {errors}")
    measurements = result["log"]["measurements"]
    peak = parse_first_number(measurements.get("peak_voltage", ""))
    if not 7.5 <= peak <= 8.5:
        raise RuntimeError(f"Unexpected peak_voltage measurement: {measurements.get('peak_voltage', '')}")
    validation = result.get("validation") or {}
    if validation.get("status") != "PASS":
        raise RuntimeError(f"Validation did not pass: {validation}")
    report = result.get("report") or {}
    report_path = Path(report.get("path", ""))
    if not report_path.exists():
        raise RuntimeError(f"Expected RLC report was not generated: {report_path}")
    report_text = report_path.read_text(encoding="utf-8")
    for required in [
        "# RLC Series Step Response Simulation Report",
        "## Validation Summary",
        "Overall result: `PASS`",
        "## Reproduction",
    ]:
        if required not in report_text:
            raise RuntimeError(f"RLC report missing required section: {required}")
    print("RLC smoke test passed")
    print(result["path"])


if __name__ == "__main__":
    main()
