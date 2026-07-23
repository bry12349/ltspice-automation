---
name: ltspice-automation
description: Use when a request involves LTspice or ngspice transient simulation, visible RC/RL/RLC/Buck schematics, waveform CSV or curve export, bounded RC/Buck parameter sweeps, engineering metrics, or simulation validation.
---

# LTspice Automation

Use this skill for the plugin's verified circuit templates and portable
transient-analysis workflows.

## Stable Workflows

- RC low-pass step response.
- RL series step response.
- Underdamped series RLC step response.
- Constrained asynchronous Buck converter.
- RC resistance or capacitance sweep.
- Buck duty-cycle sweep.
- LTspice/ngspice waveform CSV, SVG, and metric export.
- Explicit caller-provided SPICE netlists.

## Standard Workflow

1. Call `detect_simulators` before promising a backend.
2. Use `create_schematic_from_description` for natural-language RC/RL/RLC
   step responses.
3. Use `create_buck_schematic` explicitly for the supported Buck topology.
4. Use `run_parameter_sweep` only for the supported matrix below.
5. Check simulation status, validation status, warnings/errors, and every
   requested artifact before calling a result acceptable.
6. Treat stale, missing, non-finite, or non-monotonic waveform data as failure.

## Backend Selection

- `backend=ltspice`: require LTspice.
- `backend=ngspice`: require ngspice.
- `backend=auto`: prefer LTspice when available, otherwise use ngspice.

GUI opening remains macOS-only. Portable `.cir` simulations and CI can use
ngspice on Linux.

## Parameter Sweeps

`run_parameter_sweep` accepts exactly one parameter and 2–20 explicit values:

| Circuit | Parameters |
| --- | --- |
| `rc_lowpass` | `resistance`, `capacitance` |
| `buck_converter` | `duty_cycle` |

Sweeps run one isolated simulation per value. Require every point to PASS
before reporting aggregate PASS. Expected artifacts are per-point netlists and
waveforms plus `sweep_summary.csv`, `sweep_plot.svg`, and `sweep_report.md`.

## Waveform Export

Use `export_waveform` for supported LTspice binary/ASCII RAW or ngspice ASCII
RAW data. The normalized table starts with `time_s`, contains finite numeric
values, and has strictly increasing time.

RC metrics include final voltage, 10–90% rise time, measured tau, theory tau,
and tau error. Buck metrics include average/min/max output, ripple, inductor
current, ideal `D * Vin`, and conversion error.

## Buck Boundary

The Buck template is asynchronous and contains:

- DC input;
- pulse-driven voltage-controlled switch;
- freewheel diode;
- inductor;
- output capacitor;
- resistive load.

The idealized model omits gate-drive loss, parasitics, saturation, temperature,
closed-loop dynamics, and PCB effects. Treat its report as a bounded engineering
draft, not device-grade converter accuracy.

## Tool Selection

- `detect_ltspice`: legacy LTspice-only discovery.
- `detect_simulators`: LTspice and ngspice discovery.
- `create_rc_schematic`, `create_rl_schematic`, `create_rlc_schematic`:
  file-only visible templates.
- `create_schematic_from_description`: RC/RL/RLC generation, simulation,
  validation, and reports.
- `create_buck_schematic`: bounded Buck `.asc`/`.cir`, simulation, CSV, SVG,
  metrics, validation, and report.
- `run_parameter_sweep`: supported RC/Buck sweeps.
- `export_waveform`: CSV/SVG and optional RC/Buck metrics.
- `run_simulation`, `parse_log`, `create_netlist`, `open_schematic`: existing
  LTspice utilities.

## Boundaries

- Do not claim arbitrary circuit synthesis or arbitrary sweep targets.
- Do not add Buck to broad natural-language topology inference.
- Do not claim synchronous Buck, boost, flyback, closed-loop compensation,
  firmware generation, op-amp templates, PCB, or KiCad support.
- RLC remains one underdamped series topology; reject `zeta >= 1`.
- Natural-language RC/RL/RLC remains DC/step transient only.
- Do not overwrite circuit files unless `overwrite=true` is explicit.
- Never treat older artifacts as evidence for the current run.

## Good Result Summary

Include the generated input paths, selected backend, simulation and validation
status, key measurements/metrics, CSV/SVG/report paths, warnings/errors, and
model limitations.
