# LTspice Automation v0.6 Design

Date: 2026-07-23

## Objective

Version 0.6 adds four bounded capabilities:

1. parameter sweeps for RC resistance/capacitance and Buck duty cycle;
2. waveform CSV export, automatic plots, and circuit-specific metrics;
3. an ngspice backend for Linux CI and portable simulations;
4. one constrained asynchronous Buck converter template.

The release must preserve all v0.5.1 RC, RL, and underdamped RLC behavior. It
must not introduce arbitrary circuit synthesis, arbitrary sweep targets, or a
general-purpose SPICE abstraction.

## Chosen Approach

The implementation will use orchestrated point-by-point sweeps rather than
native simulator `.step` output.

For each requested parameter value, the sweep runner creates a deterministic
portable netlist, runs one simulation, exports one waveform CSV, derives
metrics, and records the result. It then produces a summary CSV, an overlay
SVG plot, and a Markdown report.

This is preferred over parsing native multi-step RAW/log files because LTspice
and ngspice represent stepped results differently. Independent runs keep the
analysis pipeline backend-neutral, make partial failures attributable to a
single point, and give every result a directly reproducible input.

## Architecture

The existing `mcp/server.py` remains the MCP entry point. New focused modules
will keep simulator and analysis concerns separate:

- `mcp/backends.py`
  - simulator discovery;
  - explicit `ltspice`, `ngspice`, and `auto` backend selection;
  - process execution and normalized status results;
  - LTspice binary/ASCII RAW and ngspice ASCII RAW handling.
- `mcp/waveforms.py`
  - normalized waveform table representation;
  - CSV reading and writing;
  - time-series validation;
  - RC and Buck metric calculation;
  - dependency-free SVG line plots.
- `mcp/sweeps.py`
  - sweep validation and limits;
  - deterministic per-point directories and filenames;
  - per-point simulation orchestration;
  - summary CSV, overlay plot, and report assembly.
- `mcp/buck.py`
  - bounded Buck parameter validation;
  - portable SPICE netlist generation;
  - visible LTspice schematic generation;
  - expected ideal conversion calculations.

Existing validation and reporting modules will be extended only where the new
result types need shared PASS/FAIL and report formatting.

## Public MCP Surface

All existing v0.5.1 tools and accepted arguments remain compatible.

New tools:

- `detect_simulators`
  - returns LTspice and ngspice availability and versions.
- `create_buck_schematic`
  - generates a visible `.asc` plus a portable `.cir` companion;
  - optionally simulates, exports CSV, plots, validates, and reports.
- `export_waveform`
  - converts a supported simulator output or normalized waveform into CSV;
  - optionally creates an SVG and metrics JSON.
- `run_parameter_sweep`
  - supports only:
    - `rc_lowpass` with `resistance` or `capacitance`;
    - `buck_converter` with `duty_cycle`;
  - supports `backend=auto|ltspice|ngspice`;
  - returns all per-point statuses and aggregate artifact paths.

The existing `run_simulation` remains LTspice-compatible. A normalized internal
runner is used by new workflows so existing callers do not receive a breaking
schema change.

## Simulator Backends

### Backend Selection

- `ltspice`: require LTspice and fail with an actionable message if absent.
- `ngspice`: require ngspice and fail with an actionable message if absent.
- `auto`: prefer LTspice on macOS when available, otherwise use ngspice.

The selected backend, executable, command, version, runtime, return code, and
fresh-output checks are included in every result.

### Portable Inputs

New portable simulations use `.cir` netlists accepted by both simulators. The
existing visible `.asc` templates remain the user-facing LTspice artifacts.
The Buck workflow generates both forms from the same validated parameter
object to prevent value drift.

### Waveform Acquisition

- ngspice is invoked with `SPICE_ASCIIRAWFILE=1`.
- LTspice uses its reliable binary batch output; the parser handles the tested
  transient RAW layout directly because LTspice 26 on macOS hangs with
  `-ascii`.
- both outputs are normalized to:
  - one strictly increasing `time_s` column;
  - finite numeric signal columns;
  - stable signal names and units.

Empty, stale, non-finite, or non-monotonic data fails the workflow rather than
producing a misleading plot.

## Parameter Sweep Contract

A sweep contains:

- a supported circuit type;
- exactly one supported parameter;
- 2 through 20 explicit values;
- fixed circuit parameters;
- backend choice;
- output directory and overwrite policy.

Values retain caller order in the summary but each point receives a sanitized,
collision-free identifier. Duplicate values, invalid SPICE numbers, nonpositive
R/C, and duty cycles outside `0 < D < 1` are rejected before files are written.

Each point has an isolated directory containing:

- the generated netlist;
- simulator log/raw output;
- normalized waveform CSV;
- metrics JSON;
- optional single-run SVG.

Aggregate artifacts:

- `sweep_summary.csv`;
- `sweep_plot.svg`;
- `sweep_report.md`.

If one point fails, remaining points still run. The aggregate status is `FAIL`,
the failed point and reason are explicit, and no overall PASS is claimed.

## Waveform Data, Plots, and Metrics

CSV output uses UTF-8, a header row, decimal numeric values, and no locale
dependent formatting.

SVG plotting uses only the Python standard library. Plots include title, axes,
units, legend, and one curve per successful sweep point. Downsampling is
deterministic and preserves endpoints and extrema so large transient files do
not create unbounded artifacts.

RC metrics:

- final voltage;
- 10–90% rise time;
- measured 63.212% time constant;
- theory time constant;
- time-constant error.

Buck metrics over a declared steady-state window:

- average output voltage;
- minimum and maximum output voltage;
- peak-to-peak and percentage ripple;
- average, minimum, and peak inductor current;
- ideal `D * Vin` target;
- conversion error relative to that idealized target.

Metric windows and formulas are included in the report and returned data.

## Buck Converter Boundary

The supported topology is one asynchronous Buck converter:

- DC input source;
- pulse-driven voltage-controlled idealized switch;
- freewheel diode;
- output inductor;
- output capacitor;
- resistive load.

Validated parameters:

- input voltage;
- duty cycle;
- switching frequency;
- inductance;
- capacitance;
- load resistance;
- switch on/off resistance;
- diode model values;
- stop time and maximum timestep.

Defaults target a 12 V input and approximately 5 V output at a bounded switching
frequency. The stop time covers enough cycles for steady-state measurement, and
the maximum timestep resolves the switching period.

The report explicitly states that idealized switch and diode models omit gate
drive loss, parasitics, magnetic saturation, device temperature, control-loop
dynamics, and PCB effects. Validation checks bounded engineering expectations,
not device-grade converter accuracy.

## Validation

RC checks compare waveform-derived tau and final value with first-order theory.

Buck checks require:

- successful simulation and valid waveform;
- finite steady-state metrics;
- positive inductor current within the supported continuous-conduction default;
- output average within a documented tolerance of `D * Vin`;
- ripple below a documented default ceiling;
- no parser-detected fatal simulator diagnostics.

Thresholds are parameterized where useful and recorded in results. A backend
result cannot PASS using stale artifacts.

## Testing and CI

Development follows red-green-refactor.

Unit tests without an installed simulator cover:

- backend selection and command construction;
- RAW/tabular waveform fixtures;
- CSV serialization;
- SVG generation;
- downsampling and data validation;
- RC and Buck metrics;
- sweep validation, limits, partial failures, and artifact naming;
- Buck netlist and visible schematic content;
- compatibility of all existing tools.

Real local smoke tests cover:

- existing RC, RL, and RLC LTspice workflows;
- one LTspice Buck run with waveform export;
- one RC resistance sweep;
- one Buck duty-cycle sweep;
- ngspice RC and Buck runs when ngspice is available.

GitHub Actions on Linux installs ngspice and runs:

- all unit tests;
- Python compilation;
- plugin and skill validation where portable;
- ngspice RC smoke;
- ngspice Buck smoke;
- git whitespace checks.

The CI workflow stores failure logs as artifacts when a simulation fails.

## Documentation and Release

README, INSTALL, roadmap, changelog, test report, plugin manifest, MCP metadata,
and skill boundaries will be updated for v0.6.0. Examples include one RC sweep
and one Buck run with CSV, SVG, metrics, and report artifacts.

Release readiness requires:

- all unit tests passing;
- Python compilation passing;
- all existing LTspice smoke tests passing;
- new LTspice and ngspice smoke tests passing;
- plugin/skill validation passing;
- clean whitespace check;
- Linux CI passing on the pushed release commit.

Only after those gates pass will the release commit be pushed, tagged `v0.6.0`,
and published as a GitHub release. A failure at any gate stops publication and
is reported with its evidence.

## Explicit Non-Goals

- arbitrary circuit generation;
- arbitrary `.step` directives or multiple simultaneous swept parameters;
- synchronous Buck, boost, flyback, closed-loop compensator, or device-library
  synthesis;
- STM32 firmware generation;
- op-amp sensor-conditioning examples;
- GUI waveform control;
- arbitrary binary RAW-format compatibility beyond the tested outputs required
  by these workflows.
