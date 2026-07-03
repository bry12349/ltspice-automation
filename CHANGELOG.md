# Changelog

## v0.3.0 - Reliability, Validation, and Report Reproducibility

Date: 2026-07-03

### Added

- Added `mcp/validation.py` for RC/RL theory-vs-simulation validation.
- Added tolerance-based validation summaries with:
  - overall PASS/FAIL status;
  - per-measurement status;
  - theory value;
  - simulation value;
  - absolute and percent error;
  - generated timestamp.
- Added `validation` output to `create_schematic_from_description` after simulation.
- Added `tolerance_percent` input to `create_schematic_from_description`.
- Added validation and reproduction sections to RC/RL Markdown reports.
- Added parser fixture-style tests for warnings, errors, measurements, and LTspice metadata filtering.
- Strengthened RC and RL smoke tests so they require validation PASS and report validation sections.

### Fixed

- Prevented common LTspice log metadata such as `Circuit`, `solver`, `temp`, `tnom`, and `method` from being reported as `.meas` measurements.
- Updated plugin and MCP server versions to `0.3.0`.

### Verification

Commands run during development:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile mcp/server.py mcp/reporting.py mcp/validation.py scripts/smoke_test.py scripts/rl_smoke_test.py
python3 scripts/smoke_test.py
python3 scripts/rl_smoke_test.py
```

### Compatibility Impact

- Existing RC/RL tool names remain unchanged.
- Existing report paths remain unchanged.
- `create_schematic_from_description` now returns an additional `validation` field.
- Reports now include additional validation and reproduction sections.

## Phase 7.1 - Version and Documentation Consistency

Date: 2026-07-01

### Fixed

- Synchronized the MCP `initialize` response server version with the plugin manifest version `0.2.0`.
- Clarified the README introduction and feature list so the documented stable workflows match the implemented RC low-pass and RL step-response workflows.

### Verification

- Re-ran unit tests after the metadata and documentation update.
- Re-ran Python compilation for the touched server module.

## Phase 7 - RL Workflow and Installable Skill Polish

Date: 2026-07-01

### Added

- Added stable series RL step-response schematic generation.
- Added `create_rl_schematic` MCP tool.
- Extended `create_schematic_from_description` to classify constrained RL requests.
- Added RL `.tran` and `.meas` generation:
  - `i_at_1tau`;
  - `i_at_5tau`;
  - `tau_cross`;
  - `final_current`.
- Added RL theory-vs-simulation Markdown reports at `reports/rl_step_response_report.md`.
- Added `scripts/rl_smoke_test.py` for real LTspice RL regression testing.
- Added RL unit tests covering schematic generation, report generation, and integration.
- Updated plugin manifest metadata for GitHub distribution.
- Rewrote the bundled skill instructions to document RC/RL workflows, tool selection, reports, and boundaries.

### Fixed

- Fixed the RL inductor schematic orientation after real LTspice netlist inspection showed the initial vertical inductor was disconnected.
- Added inductance-unit normalization for `mH` and `H`.

### Verification

Commands run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/smoke_test.py
python3 scripts/rl_smoke_test.py
python3 -m py_compile mcp/server.py mcp/reporting.py scripts/smoke_test.py scripts/rl_smoke_test.py tests/test_server.py tests/test_reporting.py tests/test_rl.py
```

Real RL smoke result:

```text
i_at_1tau = 0.315955860088 A
i_at_5tau = 0.496581480611 A
tau_cross = 0.00100056360574 s
```

### Compatibility Impact

- Existing RC tool behavior remains supported.
- `create_schematic_from_description` now supports `circuit_type=rl_step_response`.
- Tool list now includes `create_rl_schematic`.
- The plugin is still scoped to first-order RC/RL workflows and explicit custom netlists.

### Remaining Improvements

- Split shared SPICE parsing helpers out of `server.py` and `reporting.py`.
- Improve log error classification.
- Add RLC and parameter sweep workflows in later phases.

## Phase 5 - RC Markdown Report Generation

Date: 2026-07-01

### Added

- Added Markdown report generation for the RC low-pass simulation workflow.
- Added `mcp/reporting.py` as a focused report-generation module.
- `create_schematic_from_description` now writes `reports/rc_lowpass_report.md` after RC simulation and returns a `report` field with the report path.
- Reports include:
  - circuit name;
  - circuit parameters;
  - simulation settings;
  - parsed `.meas` results;
  - theoretical values;
  - simulation values;
  - percent error;
  - warning/error summary;
  - engineering conclusion;
  - follow-up improvements.
- Extended smoke test coverage to verify the report file exists and contains required sections.
- Added unit tests for report rendering and report integration.

### Why

The project now produces a shareable engineering artifact after simulation, which makes the workflow more useful for design review, portfolio presentation, and interview discussion.

### Files Changed

- `mcp/reporting.py`
- `mcp/server.py`
- `scripts/smoke_test.py`
- `tests/test_reporting.py`
- `README.md`
- `CHANGELOG.md`
- `TEST_REPORT.md`

### Verification

Commands run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/smoke_test.py
python3 -m py_compile mcp/server.py mcp/reporting.py scripts/smoke_test.py tests/test_server.py tests/test_reporting.py
```

Smoke test generated:

```text
reports/rc_lowpass_report.md
```

### Compatibility Impact

- Existing MCP tool names and existing result fields are preserved.
- `create_schematic_from_description` now returns an additional `report` field.
- Report generation is currently scoped to RC low-pass simulations.

### Remaining Improvements

- Add report support for future RL and RLC templates after their theory calculators are implemented.
- Add optional waveform images when `.raw` parsing or plotting is available.
- Add configurable report filenames for multi-run workflows beyond the current `report_path` override.

## Phase 3 - P0/P1 Stabilization

Date: 2026-07-01

### Fixed

- Parameterized default RC low-pass `.meas` directives for non-default `R`, `C`, and input voltage values.
  - Default `R=1k`, `C=1uF` still emits the existing `vout_at_1ms` and `vout_at_5ms` measurement names.
  - Non-default RC values emit `vout_at_1tau` and `vout_at_5tau` at computed 1 tau and 5 tau points.
  - `tau_cross` now scales the 63.2% threshold with final input voltage instead of assuming 1 V.
- Adjusted the default transient stop time to `6*tau` for generated RC schematics, so computed 5 tau measurements are inside the simulation window.
- Fixed mega-ohm normalization for values such as `1MΩ` and `2.2 MΩ`, which now normalize to LTspice-safe `1Meg` and `2.2Meg`.
- Added a compatible `simulation_status` field to natural-language schematic results.
  - Existing `simulation` and `log` fields are preserved.
  - Status reports `simulation_passed`, `simulation_not_requested`, `log_missing`, `log_errors`, or nonzero LTspice return code.
- Added a clear non-macOS response for `open_schematic` instead of blindly invoking macOS `open`.
- Strengthened `scripts/smoke_test.py` by parsing `vout_at_1ms` numerically and checking tolerance against `1 - exp(-1)`.

### Why

These changes address the Phase 1 P1 findings that affected result correctness and user-facing reliability:

- hard-coded tau measurement target for 1 V only;
- fixed measurement times that were meaningful only for `R=1k`, `C=1uF`;
- incorrect mega-ohm value handling;
- no structured simulation success/failure summary;
- platform-specific GUI opening behavior without a clear unsupported-platform response.

### Files Changed

- `mcp/server.py`
- `scripts/smoke_test.py`
- `tests/test_server.py`
- `CHANGELOG.md`
- `TEST_REPORT.md`

### Verification

Commands run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/smoke_test.py
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | python3 mcp/server.py
```

Additional manual end-to-end check:

- Generated and simulated a `5V`, `R=2k`, `C=1uF` RC low-pass circuit.
- Confirmed generated analysis: `.tran 0 12m 0 10u`.
- Confirmed measurements:
  - `vout_at_1tau`: `V(out) =3.16014341157 at 0.002`
  - `vout_at_5tau`: `V(out) =4.96630220616 at 0.01`
  - `tau_cross`: `V(out)=3.160603 AT 0.00200049875898`
- Confirmed `simulation_status.ok` is `true`.

### Compatibility Impact

- Public MCP tool names and existing input fields were not changed.
- Existing result fields are preserved.
- `create_schematic_from_description` now includes an additional `simulation_status` field.
- Default `R=1k`, `C=1uF`, `1V` RC low-pass measurement names remain compatible with the previous smoke workflow.
- For non-default RC values, default measurement names now use tau-based names to avoid misleading `1ms`/`5ms` labels.

### Remaining Improvements

- Add more parser tests for Chinese units and additional LTspice suffixes.
- Improve LTspice log severity classification to reduce false positives.
- Add theory-vs-simulation comparison.
- Add Markdown report generation in Phase 5.
- Refactor `mcp/server.py` into smaller modules in a later phase, after behavior is stable.
