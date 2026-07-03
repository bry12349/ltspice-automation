# Install LTspice Automation

This repository is a local Codex plugin with MCP tools and a bundled skill.

## Requirements

- macOS for GUI opening through `open_schematic`.
- Python 3.9 or newer.
- LTspice installed at `/Applications/LTspice.app`, or an explicit LTspice executable path.
- Codex with local plugin support.

Batch simulation can work without the shell command `LTspice` in `PATH` because the plugin checks `/Applications/LTspice.app`.

## Install From GitHub

Clone the repository into your local plugins folder:

```bash
mkdir -p ~/plugins
git clone https://github.com/bry12349/ltspice-automation.git ~/plugins/ltspice-automation
cd ~/plugins/ltspice-automation
```

Install the plugin in Codex:

```bash
codex plugin add ltspice-automation@personal
```

Start a new Codex thread after installing so the MCP tools and skill are loaded.

## Verify The Install

From the plugin root:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/smoke_test.py
python3 scripts/rl_smoke_test.py
```

Expected smoke output:

```text
Smoke test passed
RL smoke test passed
```

Generated reports:

```text
reports/rc_lowpass_report.md
reports/rl_step_response_report.md
```

In v0.3.0, these reports include validation PASS/FAIL status, max error, tolerance, and reproduction details.

## Available Workflows

- RC low-pass step response.
- RL series step response.
- Explicit SPICE netlist generation.
- LTspice batch simulation.
- `.log` and `.meas` parsing.
- RC/RL theory validation.
- Markdown report generation.

## Troubleshooting

### LTspice is not detected

Check:

```bash
ls -ld /Applications/LTspice.app
ls -l /Applications/LTspice.app/Contents/MacOS/LTspice
```

If LTspice is elsewhere, pass `ltspice_path` to the MCP tool.

### GUI open fails

GUI opening is currently macOS-only. Use `open=false` for headless generation and batch simulation.

### Plugin update is not visible in Codex

Reinstall the plugin:

```bash
codex plugin add ltspice-automation@personal
```

Then open a new Codex thread.
