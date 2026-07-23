# v0.4.0 Iteration Plan

## Project Assessment

The v0.3.0 skill already has stable RC and RL workflows, LTspice batch execution, `.log` parsing, validation summaries, and Markdown reports. The main remaining gap for a stronger electrical-engineering portfolio project is a second-order circuit workflow that demonstrates damping, overshoot, and natural-frequency analysis.

## Selected Direction

v0.4.0 adds one constrained underdamped series RLC step-response workflow.

This is a better next step than Buck converter because it extends the existing passive-circuit architecture without adding switching-device modeling, convergence assumptions, or PWM complexity. It also maps cleanly to interview topics: natural frequency, damping ratio, damped natural frequency, peak time, overshoot, and settling behavior.

## Scope

- Generate a visible LTspice `.asc` schematic for a series RLC circuit.
- Use capacitor voltage `V(out)` as the measured output.
- Support parameters:
  - `R`;
  - `L`;
  - `C`;
  - `Vin`.
- Add `.tran` and `.meas` directives for:
  - `vout_at_peak`;
  - `peak_voltage`;
  - `vout_at_settle`.
- Parse `.log` measurements.
- Validate simulation against second-order theory.
- Generate `reports/rlc_series_report.md`.
- Add unit tests and a real LTspice smoke test.

## Out of Scope

- Buck converter.
- Arbitrary RLC topology synthesis.
- Parallel RLC support.
- Overdamped and critically damped validation.
- Waveform image export.
- Parameter sweeps.

## Acceptance Criteria

- Existing RC and RL unit tests still pass.
- Existing RC and RL smoke tests still pass.
- New RLC unit tests pass.
- New `scripts/rlc_smoke_test.py` passes on the verified macOS LTspice environment.
- RLC report includes theory-vs-simulation and validation PASS/FAIL sections.
- README, skill metadata, changelog, and test report reflect v0.4.0.
