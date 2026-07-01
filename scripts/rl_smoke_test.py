#!/usr/bin/env python3
import json
import math
import re
import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVER = PLUGIN_ROOT / "mcp" / "server.py"
OUT = PLUGIN_ROOT / "work" / "rl-smoke"


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
            "description": "Generate a 5V step RL circuit with R=10 and L=10mH",
            "output_dir": str(OUT),
            "filename": "rl-step-smoke",
            "overwrite": True,
            "open": False,
            "simulate": True,
        },
    )
    if result["simulation"]["returncode"] != 0:
        raise RuntimeError("LTspice RL simulation failed")
    errors = result["log"]["errors"]
    if errors:
        raise RuntimeError(f"LTspice RL log errors: {errors}")
    measurements = result["log"]["measurements"]
    measured_1tau = parse_first_number(measurements.get("i_at_1tau", ""))
    expected_1tau = 0.5 * (1 - math.exp(-1))
    if abs(measured_1tau - expected_1tau) > 0.002:
        raise RuntimeError(f"Unexpected i_at_1tau measurement: {measurements.get('i_at_1tau', '')}")
    report = result.get("report") or {}
    report_path = Path(report.get("path", ""))
    if not report_path.exists():
        raise RuntimeError(f"Expected RL report was not generated: {report_path}")
    print("RL smoke test passed")
    print(result["path"])


if __name__ == "__main__":
    main()
