# LTspice Automation

LTspice Automation is a local Codex plugin and MCP tool server for turning a constrained natural-language circuit request into a visible LTspice schematic, running the simulation, parsing `.log` measurements, and checking whether the generated circuit behaves like the expected first-order RC response.

The stable workflows are intentionally narrow: RC low-pass step response and RL series step response. The project favors small, verified engineering loops over broad but fragile arbitrary circuit generation.

## Core Features

- Generates visible LTspice `.asc` schematics for RC low-pass and RL step-response circuits.
- Adds LTspice `.tran` and `.meas` directives automatically.
- Opens generated schematics in the LTspice desktop app on macOS.
- Runs LTspice batch simulation with `-b`.
- Parses `.log` files for warnings, errors, and `.meas` values.
- Computes RC measurement points from `R*C` for non-default component values.
- Scales the `tau_cross` measurement target with the input step voltage.
- Returns a structured `simulation_status` summary while preserving raw simulation and log details.
- Generates Markdown simulation reports for RC and RL workflows.
- Includes smoke and unit tests for the current RC workflow.

## Project Architecture

```text
Natural Language Request
  -> Codex Plugin / MCP Tool
  -> LTspice schematic generation (.asc)
  -> LTspice batch simulation
  -> log parsing (.log)
  -> measurement extraction (.meas)
  -> theory comparison
  -> report generation
```

Current implementation layout:

```text
ltspice-automation/
├── .codex-plugin/plugin.json
├── .mcp.json
├── mcp/server.py
├── skills/ltspice-automation/SKILL.md
├── scripts/smoke_test.py
├── scripts/rl_smoke_test.py
├── tests/test_server.py
├── tests/test_reporting.py
├── tests/test_rl.py
├── examples/rc-lowpass-step.asc
├── AUDIT.md
├── TEST_REPORT.md
├── CHANGELOG.md
├── PROJECT_ROADMAP.md
├── docs/INTERVIEW_NOTES.md
├── docs/RL_TEMPLATE_DESIGN.md
├── reports/rc_lowpass_report.md
├── reports/rl_step_response_report.md
├── README.md
└── LICENSE
```

## Installation

Clone or copy the repository into a local plugin source directory.

```bash
git clone https://github.com/bry12349/ltspice-automation.git
cd ltspice-automation
```

Install the plugin in Codex from your personal plugin source:

```bash
codex plugin add ltspice-automation@personal
```

Restart Codex or open a new thread after installing or reinstalling so the MCP tools and skill are loaded.

## LTspice Path Configuration

The project detects LTspice in this order:

1. An explicit `ltspice_path` argument passed to a tool.
2. An `LTspice` executable available in `PATH`.
3. `/Applications/LTspice.app`.
4. `~/Applications/LTspice.app`.

On the verified development machine, LTspice was found at:

```text
/Applications/LTspice.app/Contents/MacOS/LTspice
```

To check your installation:

```bash
ls -ld /Applications/LTspice.app
ls -l /Applications/LTspice.app/Contents/MacOS/LTspice
```

If LTspice is installed somewhere else, pass the app bundle or executable path:

```json
{
  "ltspice_path": "/Applications/LTspice.app"
}
```

Batch simulation can work with an explicit executable path. GUI opening currently uses macOS `open`, so `open_schematic` is macOS-only.

## Quick Start

Run the current end-to-end smoke test from the repository root:

```bash
python3 scripts/smoke_test.py
```

Expected output:

```text
Smoke test passed
/path/to/ltspice-automation/work/smoke/smoke-rc-lowpass.asc
```

Run the unit tests:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

The smoke test creates an RC low-pass schematic, runs LTspice, parses the `.log`, and verifies that `V(out)` at one time constant is close to `1 - exp(-1)`.

## MCP Tools

- `detect_ltspice`: detects the local LTspice installation and version.
- `create_netlist`: writes a `.cir` file from explicit SPICE lines or a built-in RC low-pass netlist template.
- `create_rc_schematic`: writes a visible LTspice `.asc` schematic for an RC step-response circuit.
- `create_rl_schematic`: writes a visible LTspice `.asc` schematic for an RL step-response circuit.
- `create_schematic_from_description`: parses a constrained natural-language RC/RL request, generates `.asc`, optionally simulates it, optionally writes a Markdown report, and optionally opens LTspice.
- `open_schematic`: opens an existing `.asc` in the LTspice GUI on macOS.
- `run_simulation`: runs LTspice batch mode against `.cir`, `.net`, or `.asc`.
- `parse_log`: extracts warnings, errors, measurements, and log tail text from an LTspice `.log`.

## RC Low-Pass Example

Example request:

```text
Generate a 1V step RC low-pass circuit with R=1k and C=1uF
```

The generated schematic contains:

```text
V1 in 0 PULSE(0 1 0 1u 1u 10m 20m)
R1 in out 1k
C1 out 0 1u
.tran 0 6m 0 10u
.meas tran vout_at_1ms FIND V(out) AT=1m
.meas tran vout_at_5ms FIND V(out) AT=5m
.meas tran tau_cross WHEN V(out)=0.632121 RISE=1
```

An example schematic is included at:

```text
examples/rc-lowpass-step.asc
```

## Simulation Result Example

For a 1 V step input with `R=1k` and `C=1uF`:

```text
vout_at_1ms = 0.631937 V
vout_at_5ms = 0.993259 V
tau_cross   = 1.000497 ms
```

For a non-default example with `Vin=5V`, `R=2k`, `C=1uF`, the tool computes `tau = 2 ms` and sets the simulation stop time to `12 ms`:

```text
vout_at_1tau = 3.160143 V at 2 ms
vout_at_5tau = 4.966302 V at 10 ms
tau_cross    = 2.000499 ms
```

## Theory vs Simulation

RC low-pass step response:

```text
tau = R * C
Vout(t) = Vin * (1 - exp(-t / tau))
```

Default case: `Vin=1V`, `R=1k`, `C=1uF`, `tau=1ms`.

| Quantity | Theory | Simulation | Error |
| --- | ---: | ---: | ---: |
| `Vout(1 tau)` | `0.632121 V` | `0.631937 V` | about `0.03%` |
| `Vout(5 tau)` | `0.993262 V` | `0.993259 V` | about `0.0003%` |
| `tau_cross` | `1.000000 ms` | `1.000497 ms` | about `0.05%` |

The current code parses simulation values, generates parameter-aware measurement directives, and writes a Markdown report with a theory-vs-simulation table for RC low-pass simulations.

## RL Step-Response Example

Example request:

```text
Generate a 5V step RL circuit with R=10 and L=10mH
```

The generated schematic contains a series voltage source, resistor, and inductor with measurements:

```text
.tran 0 6m 0 10u
.meas tran i_at_1tau FIND I(L1) AT=1m
.meas tran i_at_5tau FIND I(L1) AT=5m
.meas tran tau_cross WHEN I(L1)=0.31606 RISE=1
.meas tran final_current FIND I(L1) AT=5m
```

RL theory:

```text
tau = L / R
I_final = Vin / R
i(t) = I_final * (1 - exp(-t / tau))
```

For `Vin=5V`, `R=10`, and `L=10mH`:

| Quantity | Theory | Simulation | Error |
| --- | ---: | ---: | ---: |
| `i_at_1tau` | `0.316060 A` | `0.315956 A` | about `0.03%` |
| `i_at_5tau` | `0.496631 A` | `0.496581 A` | about `0.01%` |
| `tau_cross` | `1.000000 ms` | `1.000564 ms` | about `0.06%` |

## Markdown Reports

After an RC low-pass simulation, the workflow writes:

```text
reports/rc_lowpass_report.md
```

After an RL step-response simulation, the workflow writes:

```text
reports/rl_step_response_report.md
```

The report includes:

- circuit name;
- circuit parameters;
- simulation settings;
- parsed `.meas` results;
- theoretical RC values;
- simulation values;
- percent error;
- warning/error summary;
- engineering conclusion;
- follow-up improvements.

Example report excerpt:

```text
## Theory vs Simulation

| Measurement | Theory | Simulation | Error |
| --- | ---: | ---: | ---: |
| `vout_at_1ms` | `0.632121 V` | `0.631937 V` | `0.02903%` |
| `vout_at_5ms` | `0.993262 V` | `0.993259 V` | `0.0003167%` |
| `tau_cross` | `0.001 s` | `0.0010005 s` | `0.04982%` |
```

## Testing

Current test commands:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/smoke_test.py
python3 scripts/rl_smoke_test.py
python3 -m py_compile mcp/server.py mcp/reporting.py scripts/smoke_test.py scripts/rl_smoke_test.py tests/test_server.py tests/test_reporting.py tests/test_rl.py
```

Covered today:

- RC schematic generation for default and non-default parameters.
- RL schematic generation and report integration.
- Mega-ohm unit normalization.
- Structured simulation status helper behavior.
- Non-macOS GUI-open unsupported-platform response.
- Numeric smoke-test tolerance for the default RC response.
- Markdown report generation for RC and RL workflows.
- End-to-end LTspice batch simulation on macOS.

## Common Problems

### LTspice is not found

Install LTspice for macOS and confirm:

```bash
ls -ld /Applications/LTspice.app
```

If it is installed elsewhere, pass `ltspice_path`.

### The shell says `LTspice not found`

That can be fine. The project does not require `LTspice` in `PATH` if `/Applications/LTspice.app` exists.

### GUI opening fails on Windows or Linux

`open_schematic` currently supports GUI opening only on macOS. Batch simulation may still work if you pass a valid LTspice executable path.

### A non-RC circuit request fails

That is expected. The stable natural-language visual schematic generator currently supports RC low-pass circuits only. Use explicit netlist lines for custom `.cir` files until more verified templates exist.

### Measurement names changed for non-default RC values

For default `R=1k`, `C=1uF`, names remain `vout_at_1ms` and `vout_at_5ms`. For other `R*C` values, the tool uses `vout_at_1tau` and `vout_at_5tau` so the labels match the actual measurement meaning.

## Current Limitations

- Stable visual schematic generation is limited to RC low-pass and RL series step response.
- Natural-language parsing is constrained and regex-based.
- GUI opening is macOS-specific.
- Log parsing is useful but still simple; severity classification can be improved.
- Markdown report generation currently supports RC low-pass and RL series step response.
- RLC, Buck converter, and parameter sweep workflows are planned but not implemented.
- The project is not a PCB or KiCad automation tool.

## Roadmap

- Phase 0: stabilize the current RC workflow.
- Phase 1: improve tests, error handling, and log parsing.
- Phase 2: add automatic Markdown simulation reports. Completed for RC low-pass.
- Phase 3: add RL step response. Completed for a series RL template.
- Phase 4: add RLC second-order response.
- Phase 5: add Buck converter simulation workflow.
- Phase 6: add parameter sweep support.
- Phase 7: create portfolio-ready artifacts.

See `PROJECT_ROADMAP.md` for the full staged plan.

## Why This Project Matters

This project demonstrates a practical engineering automation loop:

1. Translate a constrained design intent into a circuit artifact.
2. Generate a real LTspice schematic instead of only text.
3. Run the simulator instead of assuming correctness.
4. Parse measured outputs.
5. Compare results against circuit theory.
6. Preserve the workflow as tests and documentation.

That makes it suitable for electrical engineering, hardware test, circuit simulation, and embedded-test internship portfolios.
