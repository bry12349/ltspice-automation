#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SERVER = PLUGIN_ROOT / "mcp" / "server.py"
OUT = PLUGIN_ROOT / "work" / "smoke"


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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = call_tool(
        "create_schematic_from_description",
        {
            "description": "Generate a 1V step RC low-pass circuit with R=1k and C=1uF",
            "output_dir": str(OUT),
            "filename": "smoke-rc-lowpass",
            "overwrite": True,
            "open": False,
            "simulate": True,
        },
    )
    if result["simulation"]["returncode"] != 0:
        raise RuntimeError("LTspice simulation failed")
    errors = result["log"]["errors"]
    if errors:
        raise RuntimeError(f"LTspice log errors: {errors}")
    measurement = result["log"]["measurements"].get("vout_at_1ms", "")
    if "0.631" not in measurement and "0.632" not in measurement:
        raise RuntimeError(f"Unexpected vout_at_1ms measurement: {measurement}")
    print("Smoke test passed")
    print(result["path"])


if __name__ == "__main__":
    main()
