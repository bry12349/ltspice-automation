# LTspice Automation

LTspice Automation is a local Codex plugin and MCP server for constrained,
verifiable circuit simulation. It generates visible LTspice schematics, runs
LTspice or ngspice, exports waveform data to CSV, creates SVG curves, computes
engineering metrics, and writes PASS/FAIL reports.

Version 0.6.0 adds a bounded asynchronous Buck converter, RC and Buck parameter
sweeps, waveform export, and a Linux-compatible ngspice backend. The project
still favors deterministic templates over arbitrary circuit generation.

## Supported Workflows

- RC low-pass step response.
- RL series step response.
- Underdamped series RLC step response.
- Constrained asynchronous Buck converter.
- RC resistance or capacitance sweep.
- Buck duty-cycle sweep.
- LTspice binary/ASCII RAW and ngspice ASCII RAW export to CSV/SVG.
- Explicit caller-provided SPICE netlists.
- Theory/metric validation and Markdown reports.

## Requirements

- Python 3.9 or newer.
- LTspice for macOS GUI and LTspice batch workflows.
- ngspice for portable macOS/Linux workflows and CI.
- No third-party Python packages.

Install ngspice:

```bash
# macOS
brew install ngspice

# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y ngspice
```

See [INSTALL.md](INSTALL.md) for plugin installation and troubleshooting.

## Quick Verification

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile mcp/*.py scripts/*.py tests/*.py

# Existing LTspice regressions
python3 scripts/smoke_test.py
python3 scripts/rl_smoke_test.py
python3 scripts/rlc_smoke_test.py

# v0.6 workflows
python3 scripts/buck_smoke_test.py
python3 scripts/ngspice_smoke_test.py
python3 scripts/sweep_smoke_test.py
```

## MCP Tools

Existing tools remain compatible:

- `detect_ltspice`
- `create_netlist`
- `run_simulation`
- `create_rc_schematic`
- `create_rl_schematic`
- `create_rlc_schematic`
- `create_schematic_from_description`
- `open_schematic`
- `parse_log`

Version 0.6 adds:

- `detect_simulators`: discover LTspice and ngspice.
- `create_buck_schematic`: create `.asc` and `.cir`, simulate, export CSV/SVG,
  calculate metrics, validate, and report.
- `export_waveform`: normalize a supported RAW file into CSV/SVG and optionally
  compute RC or Buck metrics.
- `run_parameter_sweep`: run a bounded point-by-point RC or Buck sweep.

## Buck Converter

The supported topology is one asynchronous Buck:

```text
Vin -> controlled switch -> L -> Vout
                         |       |
                    freewheel D  C || Rload
                         |       |
                        GND     GND
```

Defaults:

| Parameter | Value |
| --- | ---: |
| Input | 12 V |
| Duty cycle | 5/12 |
| Switching frequency | 100 kHz |
| Inductor | 100 µH |
| Output capacitor | 220 µF |
| Load | 5 Ω |
| Stop time | 10 ms |
| Maximum timestep | 100 ns |

Example MCP arguments:

```json
{
  "output_dir": "work/buck-demo",
  "filename": "buck-demo",
  "backend": "ngspice",
  "simulate": true,
  "overwrite": true,
  "vin": 12,
  "duty_cycle": 0.4166666667
}
```

Outputs include:

- visible `buck-demo.asc`;
- portable `buck-demo.cir`;
- `buck-demo_waveform.csv`;
- `buck-demo_waveform.svg`;
- `buck-demo_metrics.json`;
- `buck-demo_report.md`.

Default real-simulator results are approximately 4.69 V average output with
about 0.4% ripple. The ideal `D * Vin` target is 5 V; the difference reflects
the simplified diode/switch model.

## Parameter Sweeps

Exactly one parameter and 2–20 explicit values are supported:

| Circuit | Parameter |
| --- | --- |
| `rc_lowpass` | `resistance` |
| `rc_lowpass` | `capacitance` |
| `buck_converter` | `duty_cycle` |

RC example:

```json
{
  "circuit_type": "rc_lowpass",
  "parameter": "resistance",
  "values": ["500", "1k", "2k"],
  "parameters": {
    "capacitance": "1u",
    "vin": "1"
  },
  "backend": "ltspice",
  "output_dir": "work/rc-r-sweep",
  "overwrite": true
}
```

Buck example:

```json
{
  "circuit_type": "buck_converter",
  "parameter": "duty_cycle",
  "values": [0.35, 0.4166666667, 0.5],
  "backend": "ngspice",
  "output_dir": "work/buck-duty-sweep",
  "overwrite": true
}
```

Every value has an isolated point directory. Aggregate artifacts are:

- `sweep_summary.csv`;
- `sweep_plot.svg`;
- `sweep_report.md`.

One failed point does not stop remaining simulations, but aggregate status is
FAIL unless every point passes simulation, waveform analysis, and validation.

## Waveform Metrics

RC:

- final voltage;
- 10–90% rise time;
- measured 63.212% time constant;
- theory time constant;
- tau error.

Buck steady state:

- average/min/max output voltage;
- peak-to-peak and percentage ripple;
- average/min/peak inductor current;
- ideal `D * Vin`;
- conversion error.

CSV files use `time_s` as the first column. Tables must contain finite numeric
values and strictly increasing time. SVG plotting is implemented with the
Python standard library and retains endpoints and extrema when downsampling.

## Architecture

```text
MCP request
  -> validated RC/Buck template
  -> portable .cir and optional visible .asc
  -> LTspice or ngspice backend
  -> normalized waveform table
  -> CSV + SVG + metrics + validation
  -> Markdown report
```

Key modules:

- `mcp/server.py`: MCP JSON-RPC surface and existing templates.
- `mcp/backends.py`: simulator detection and normalized execution.
- `mcp/waveforms.py`: RAW parsing, CSV/SVG, and metrics.
- `mcp/portable.py`: portable RC workflow.
- `mcp/buck.py`: bounded Buck generation and analysis.
- `mcp/sweeps.py`: point-by-point sweep orchestration.

## CI

`.github/workflows/ci.yml` runs on Ubuntu and installs ngspice. It executes:

- all unit tests;
- Python compilation;
- real ngspice RC and Buck smoke tests;
- whitespace checks;
- failure artifact upload.

LTspice-only smoke tests remain local because LTspice is not available on the
Linux runner.

## Boundaries

- No arbitrary circuit synthesis.
- No arbitrary or multi-parameter sweeps.
- No synchronous Buck, boost, flyback, or closed-loop control design.
- No STM32 firmware or op-amp sensor template in v0.6.
- RLC remains a constrained underdamped series topology.
- Buck models omit gate-drive loss, parasitics, magnetic saturation,
  temperature, control-loop dynamics, and PCB effects.
- Generated circuits remain engineering drafts until simulation and validation
  evidence has been checked.

## License

MIT. See [LICENSE](LICENSE).
