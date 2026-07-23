#!/usr/bin/env python3
"""Dependency-free package checks suitable for Linux CI."""

import json
import re
import subprocess
import sys
from pathlib import Path


EXPECTED_NAME = "ltspice-automation"
EXPECTED_RELEASE = "0.6.0"
REQUIRED_TOOLS = {
    "detect_simulators",
    "create_buck_schematic",
    "export_waveform",
    "run_parameter_sweep",
}


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid JSON file {path}: {exc}") from exc


def _skill_frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise RuntimeError(f"{path} must start with YAML frontmatter")
    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    return fields


def validate_package(root: Path) -> None:
    manifest_path = root / ".codex-plugin" / "plugin.json"
    manifest = _load_json(manifest_path)
    if manifest.get("name") != EXPECTED_NAME:
        raise RuntimeError(f"plugin name must be {EXPECTED_NAME}")
    version = str(manifest.get("version") or "")
    if not re.fullmatch(rf"{re.escape(EXPECTED_RELEASE)}(?:\+codex\.\d{{14}})?", version):
        raise RuntimeError(f"plugin version must identify release {EXPECTED_RELEASE}")
    for field in ("description", "author", "repository", "license", "skills", "mcpServers"):
        if not manifest.get(field):
            raise RuntimeError(f"plugin manifest is missing {field}")

    skill_path = root / "skills" / EXPECTED_NAME / "SKILL.md"
    frontmatter = _skill_frontmatter(skill_path)
    if frontmatter.get("name") != EXPECTED_NAME:
        raise RuntimeError(f"skill name must be {EXPECTED_NAME}")
    if len(frontmatter.get("description", "")) < 40:
        raise RuntimeError("skill description must explain when to use the skill")

    _load_json(root / ".mcp.json")
    server_text = (root / "mcp" / "server.py").read_text(encoding="utf-8")
    if f'"version": "{EXPECTED_RELEASE}"' not in server_text:
        raise RuntimeError("MCP server release version is out of sync")
    missing = sorted(tool for tool in REQUIRED_TOOLS if f'"{tool}":' not in server_text)
    if missing:
        raise RuntimeError(f"MCP server is missing tools: {', '.join(missing)}")

    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=str(root),
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    for relative_bytes in tracked:
        if not relative_bytes:
            continue
        relative = relative_bytes.decode("utf-8")
        path = root / relative
        if not path.is_file() or b"\0" in path.read_bytes():
            continue
        data = path.read_bytes()
        if data and not data.endswith(b"\n"):
            raise RuntimeError(f"tracked text file lacks final newline: {relative}")
        for line_number, line in enumerate(data.splitlines(), 1):
            if line.rstrip(b" \t") != line:
                raise RuntimeError(
                    f"tracked text file has trailing whitespace: {relative}:{line_number}"
                )


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        validate_package(root)
    except Exception as exc:
        print(f"PACKAGE VALIDATION FAIL: {exc}", file=sys.stderr)
        return 1
    print("PACKAGE VALIDATION PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
