---
name: ltspice-automation
description: Generate visible LTspice RC low-pass, RL step-response, or underdamped series RLC step-response schematics, run LTspice simulations, parse .log/.meas results, validate circuit theory against simulation, and produce Markdown reports with PASS/FAIL summaries. Use for LTspice schematic generation, transient simulation, measurement extraction, validation, or troubleshooting this plugin's RC/RL/RLC workflows.
---

# LTspice Automation

Use this skill for LTspice workflows involving visible `.asc` schematics, SPICE netlists, transient analysis, `.meas` extraction, or simulation report generation.

## Stable Workflows

- RC low-pass step response.
- RL series step response.
- Underdamped series RLC step response.
- Explicit `.cir` netlist creation from caller-provided SPICE lines.
- LTspice batch simulation and `.log` parsing.
- Theory validation with tolerance-based PASS/FAIL checks.
- Markdown reports for stable RC/RL/RLC step-response simulations.

## Standard Workflow

1. Call `detect_ltspice` before promising simulation.
2. For visible RC/RL/RLC circuits, call `create_schematic_from_description`.
3. Set `open=false` when the user asks for a file-only or headless workflow.
4. Leave `simulate=true` unless the user asks only for schematic generation.
5. Check `simulation_status.ok`, `.log` warnings/errors, and parsed measurements before explaining results.
6. Check `validation.status` before calling the result acceptable.
7. Use the generated Markdown report when summarizing final values.
8. Treat `run_simulation.ok=false` as a failed run even if older artifacts exist in the destination directory.

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

Default report: beside the generated schematic as `<schematic-stem>_report.md`; callers can override it with `report_path`.

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

Default report: beside the generated schematic as `<schematic-stem>_report.md`; callers can override it with `report_path`.

## RLC Series Step-Response Requests

Use RLC when the request mentions an RLC circuit, second-order response, ringing, overshoot, damping ratio, or `RLC step`.

Expected parameters:

- `R` or resistance;
- `L` or inductance;
- `C` or capacitance;
- `Vin` or step amplitude.

Theory:

```text
omega_n = 1 / sqrt(L * C)
zeta = R / 2 * sqrt(C / L)
omega_d = omega_n * sqrt(1 - zeta^2)
```

Default report: beside the generated schematic as `<schematic-stem>_report.md`; callers can override it with `report_path`.

## Tool Selection

- `detect_ltspice`: find LTspice executable and version.
- `create_schematic_from_description`: preferred entry point for natural-language RC/RL/RLC schematic generation, simulation, parsing, and reporting.
- `create_rc_schematic`: file-only RC `.asc` generation from explicit parameters.
- `create_rl_schematic`: file-only RL `.asc` generation from explicit parameters.
- `create_rlc_schematic`: file-only underdamped series RLC `.asc` generation from explicit parameters.
- `run_simulation`: run LTspice batch mode on an existing `.asc`, `.cir`, or `.net`.
- `parse_log`: parse an existing LTspice `.log`.
- `create_netlist`: create `.cir` files from explicit SPICE lines or the simple built-in RC netlist template.
- `open_schematic`: open `.asc` files in the LTspice GUI on macOS.

## Boundaries

- Do not claim arbitrary circuit synthesis.
- Do not claim Buck, op-amp, transistor, or PCB/KiCad support yet.
- Treat RLC support as the constrained underdamped series template only; do not claim arbitrary second-order topology synthesis.
- Natural-language templates support only DC/step transient requests; route AC, frequency-response, and sine requests to explicit netlists until a verified analysis workflow exists.
- Natural-language DC/default sources are normalized to zero-to-Vin pulses for the supported step-response templates.
- Parseable R/L/C values must be positive; unparseable LTspice expressions are left for LTspice to evaluate.
- Reject parseable RLC values where `zeta >= 1`; critical and overdamped RLC behavior is not supported yet.
- LTspice batch runs transparently stage whitespace-containing paths and copy newly generated artifacts back to the requested directory.
- Treat unsupported circuits as explicit-netlist tasks until a verified `.asc` template and tests exist.
- Do not overwrite existing circuit files unless the user asks or `overwrite=true` is explicit and safe.
- GUI opening is macOS-only; batch simulation can use an explicit executable path when available.
- Treat generated circuits as engineering drafts until LTspice simulation and `.meas` results are checked.

## Good Result Summary

When reporting results, include:

- generated `.asc` path;
- LTspice simulation status;
- parsed `.meas` values;
- theory comparison for first-order tau or second-order damping/peak response;
- validation status and max error;
- report path;
- any warnings/errors or limitations.
