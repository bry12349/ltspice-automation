---
name: ltspice-automation
description: Generate visible LTspice RC low-pass or RL step-response schematics, run LTspice simulations, parse .log/.meas results, compare first-order theory, and produce Markdown reports. Use for LTspice schematic generation, transient simulation, measurement extraction, or troubleshooting this plugin's RC/RL workflows.
---

# LTspice Automation

Use this skill for LTspice workflows involving visible `.asc` schematics, SPICE netlists, transient analysis, `.meas` extraction, or simulation report generation.

## Stable Workflows

- RC low-pass step response.
- RL series step response.
- Explicit `.cir` netlist creation from caller-provided SPICE lines.
- LTspice batch simulation and `.log` parsing.
- Markdown reports for stable RC/RL step-response simulations.

## Standard Workflow

1. Call `detect_ltspice` before promising simulation.
2. For visible first-order circuits, call `create_schematic_from_description`.
3. Set `open=false` when the user asks for a file-only or headless workflow.
4. Leave `simulate=true` unless the user asks only for schematic generation.
5. Check `simulation_status.ok`, `.log` warnings/errors, and parsed measurements before explaining results.
6. Use the generated Markdown report when summarizing final values.

## RC Low-Pass Requests

Use RC when the request mentions a low-pass RC filter, resistor-capacitor step response, capacitor charging, or `RC low-pass`.

Expected parameters:

- `R` or resistance;
- `C` or capacitance;
- `Vin` or step amplitude.

Theory:

```text
tau = R * C
Vout(t) = Vin * (1 - exp(-t / tau))
```

Default report:

```text
reports/rc_lowpass_report.md
```

## RL Step-Response Requests

Use RL when the request mentions an RL circuit, resistor-inductor step response, inductor current rise, or `RL step`.

Expected parameters:

- `R` or resistance;
- `L` or inductance;
- `Vin` or step amplitude.

Theory:

```text
tau = L / R
I_final = Vin / R
i(t) = I_final * (1 - exp(-t / tau))
```

Default report:

```text
reports/rl_step_response_report.md
```

## Tool Selection

- `detect_ltspice`: find LTspice executable and version.
- `create_schematic_from_description`: preferred entry point for natural-language RC/RL schematic generation, simulation, parsing, and reporting.
- `create_rc_schematic`: file-only RC `.asc` generation from explicit parameters.
- `create_rl_schematic`: file-only RL `.asc` generation from explicit parameters.
- `run_simulation`: run LTspice batch mode on an existing `.asc`, `.cir`, or `.net`.
- `parse_log`: parse an existing LTspice `.log`.
- `create_netlist`: create `.cir` files from explicit SPICE lines or the simple built-in RC netlist template.
- `open_schematic`: open `.asc` files in the LTspice GUI on macOS.

## Boundaries

- Do not claim arbitrary circuit synthesis.
- Do not claim Buck, RLC, op-amp, transistor, or PCB/KiCad support yet.
- Treat unsupported circuits as explicit-netlist tasks until a verified `.asc` template and tests exist.
- Do not overwrite existing circuit files unless the user asks or `overwrite=true` is explicit and safe.
- GUI opening is macOS-only; batch simulation can use an explicit executable path when available.
- Treat generated circuits as engineering drafts until LTspice simulation and `.meas` results are checked.

## Good Result Summary

When reporting results, include:

- generated `.asc` path;
- LTspice simulation status;
- parsed `.meas` values;
- theory comparison for tau and 1 tau/5 tau response;
- report path;
- any warnings/errors or limitations.
