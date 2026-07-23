# Install LTspice Automation

## Requirements

- Python 3.9 or newer.
- Codex with local plugin support.
- LTspice for macOS GUI/LTspice simulations.
- ngspice for portable macOS/Linux simulations and CI.

Install ngspice:

```bash
# macOS
brew install ngspice

# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ngspice
```

LTspice is detected from an explicit path, `PATH`,
`/Applications/LTspice.app`, or `~/Applications/LTspice.app`.

## Install From GitHub

```bash
mkdir -p ~/plugins
git clone https://github.com/bry12349/ltspice-automation.git ~/plugins/ltspice-automation
cd ~/plugins/ltspice-automation
codex plugin add ltspice-automation@personal
```

Open a new Codex task after installation so the MCP tools and skill reload.

## Verify

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile mcp/*.py scripts/*.py tests/*.py
python3 scripts/smoke_test.py
python3 scripts/rl_smoke_test.py
python3 scripts/rlc_smoke_test.py
python3 scripts/buck_smoke_test.py
python3 scripts/ngspice_smoke_test.py
python3 scripts/sweep_smoke_test.py
```

## Headless Linux

Linux supports portable `.cir` workflows through ngspice:

- RC simulations and R/C sweeps;
- constrained Buck simulations and duty-cycle sweeps;
- CSV, SVG, metrics, validation, and Markdown reports.

Opening `.asc` in the LTspice GUI remains macOS-only.

## Troubleshooting

Check simulator discovery:

```bash
ls -l /Applications/LTspice.app/Contents/MacOS/LTspice
ngspice --version
```

Pass `ltspice_path` or `ngspice_path` when executables are in nonstandard
locations. Use `backend=ngspice` on Linux and `backend=auto` when either
installed backend is acceptable.

If a plugin update is not visible:

```bash
codex plugin add ltspice-automation@personal
```

Then open a new Codex task.
