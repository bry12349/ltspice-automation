# Project Roadmap

This roadmap keeps the project scoped as an engineering automation tool, not an unbounded circuit generator. Each phase should preserve the stable RC low-pass workflow and add only the smallest verified capability needed for the next step.

## Phase 0: Stabilize Current RC Workflow

### Goal

Make the existing RC low-pass step-response workflow reliable enough to use as the baseline demo.

### Tasks

- Audit current repository behavior.
- Run existing smoke tests and document environment assumptions.
- Fix P0/P1 issues that affect correctness or reliability.
- Preserve existing public MCP tool names.
- Add minimal regression tests for the fixes.

### Acceptance Criteria

- `scripts/smoke_test.py` passes on a machine with LTspice installed.
- Unit tests cover parameterized RC measurements and value normalization.
- Default `1V`, `1k`, `1uF` workflow remains compatible.
- `AUDIT.md`, `TEST_REPORT.md`, and `CHANGELOG.md` exist.

### Risks

- Over-fixing can turn the project into a refactor before the stable demo is protected.
- Changing measurement names can break users if compatibility is ignored.

### Resume Value

Shows debugging discipline, simulation verification, and an ability to stabilize a real tool before adding features.

## Phase 1: Improve Tests, Error Handling, and Log Parsing

### Goal

Make failures easier to diagnose and reduce false confidence in simulation output.

### Tasks

- Expand unit tests for:
  - value parsing;
  - schematic generation;
  - log parsing;
  - overwrite protection;
  - unsupported circuit handling.
- Improve LTspice missing-path errors.
- Refine log severity parsing.
- Add tests for warning/error examples from real or fixture logs.
- Keep `simulation_status` stable and documented.

### Acceptance Criteria

- Unit tests run without LTspice.
- Smoke test still runs the real simulator.
- Parser distinguishes fatal errors from broad diagnostic text more clearly.
- Missing LTspice configuration gives actionable messages.

### Risks

- Log formats can vary by LTspice version.
- Too much parser complexity can make the project harder to maintain.

### Resume Value

Demonstrates test strategy, error handling, and production-style reliability around engineering software.

## Phase 2: Automatic Markdown Simulation Reports

### Goal

Generate a shareable engineering report after RC simulation.

Status: completed for the RC low-pass workflow. Future circuit templates should reuse or extend the report-generation pattern.

### Tasks

- Add a report generator module.
- Include:
  - circuit name;
  - circuit parameters;
  - simulation settings;
  - `.meas` results;
  - theoretical values;
  - simulation values;
  - error table;
  - warning/error summary;
  - engineering conclusion;
  - future improvement notes.
- Save reports under `reports/`.
- Add tests that verify report generation and key fields.
- Update README with a report example.

### Acceptance Criteria

- Running the RC workflow can produce `reports/rc_lowpass_report.md`.
- Report includes theory-vs-simulation comparison.
- Tests verify report creation and required headings.
- Existing RC smoke test still passes.

### Risks

- Report generation can become tightly coupled to current parser output.
- Hard-coded prose can make reports less useful for future circuit types.

### Resume Value

Creates a portfolio-ready artifact and shows the ability to turn simulation output into engineering communication.

## Phase 3: Add RL Step Response

### Goal

Add the next first-order circuit family after RC: RL step response.

Status: completed for a constrained series RL step-response template.

### Tasks

- Write `docs/RL_TEMPLATE_DESIGN.md` before implementation.
- Define parameters:
  - `R`;
  - `L`;
  - `Vin`;
  - `tstop`.
- Generate a visible `.asc` schematic.
- Add `.tran` and `.meas` directives.
- Parse `.log` measurements.
- Compute theory:
  - `tau = L/R`;
  - `I_final = Vin/R`;
  - `i(t) = I_final * (1 - exp(-t/tau))`.
- Generate a Markdown report.
- Add unit and smoke/regression tests.

### Acceptance Criteria

- RL template design is reviewed before coding.
- Generated RL schematic opens in LTspice.
- Batch simulation passes.
- Measured current at 1 tau and 5 tau matches theory within tolerance.
- RC workflow remains unchanged and passing.

### Risks

- Current measurement syntax for inductor or source current must be chosen carefully.
- Natural-language parsing should not accidentally classify unsupported circuits as RL.

### Resume Value

Shows transfer of first-order transient theory from capacitor voltage to inductor current and proves the architecture can extend beyond one circuit.

## Phase 4: Add RLC Second-Order Response

Status: completed in v0.4.0 for one constrained underdamped series RLC topology.

Before starting Phase 4, v0.3.0 completed an intermediate reliability phase:

- RC/RL simulation results now include tolerance-based validation summaries.
- RC/RL reports now include PASS/FAIL and reproduction sections.
- Parser tests cover LTspice warning/error lines and avoid treating simulator metadata as measurements.
- Smoke tests require validation to pass before accepting the generated result.

### Goal

Add a second-order circuit template to demonstrate more advanced transient behavior.

### Tasks

- Design a constrained RLC circuit topology.
- Decide series or parallel RLC first; do not support both initially.
- Define parameters:
  - `R`;
  - `L`;
  - `C`;
  - `Vin`;
  - `tstop`.
- Compute:
  - natural frequency;
  - damping ratio;
  - expected underdamped/overdamped behavior.
- Add `.meas` directives for peak time, overshoot, settling estimate, or selected sample points.
- Add tests and report output.

### Acceptance Criteria

- One RLC topology is documented and tested. Completed with `docs/RLC_TEMPLATE_DESIGN.md`.
- Simulation produces expected second-order behavior. Completed with `scripts/rlc_smoke_test.py`.
- Report explains damping category and measured response. Completed with `reports/rlc_series_report.md`.
- RC and RL workflows remain passing. Verified with existing smoke tests.

### Risks

- RLC theory has more cases than RC/RL.
- Poor default parameters can create confusing waveforms or unstable-looking results.

### Resume Value

Demonstrates second-order system analysis, damping concepts, and simulation interpretation.

### v0.4.0 Notes

The implemented template is intentionally narrow:

- series RLC only;
- capacitor voltage output only;
- underdamped default values only;
- no parallel RLC;
- no overdamped or critically damped validation yet.

## Phase 5: Add Buck Converter

### Goal

Add a constrained switching power converter example after simpler passive circuits are stable.

### Tasks

- Define assumptions:
  - ideal switch or simplified MOSFET;
  - diode or synchronous rectifier choice;
  - duty cycle;
  - switching frequency;
  - inductor;
  - output capacitor;
  - load resistance.
- Generate a visible `.asc`.
- Add transient simulation settings that capture switching behavior.
- Measure output voltage, ripple, and approximate settling.
- Compare expected `Vout ~= D * Vin` against simulation.
- Document limitations clearly.

### Acceptance Criteria

- Buck simulation runs with bounded default parameters.
- Output voltage and ripple are extracted.
- README and report state assumptions and limitations.
- Existing RC/RL/RLC tests remain passing.

### Risks

- Switching simulations are more sensitive to timestep, model assumptions, and convergence.
- It is easy to overclaim converter accuracy without proper component models.

### Resume Value

Shows power electronics exposure, switching simulation awareness, and the ability to handle more complex LTspice workflows.

## Phase 6: Parameter Sweeps

### Goal

Add controlled `.step` support for exploring how component values affect response.

### Tasks

- Start with RC parameter sweeps.
- Support one swept parameter at a time.
- Generate `.step param` directives.
- Parse sweep results from logs or exported data.
- Produce a table in the Markdown report.
- Add examples for changing `R`, `C`, or `Vin`.

### Acceptance Criteria

- One RC sweep runs and produces a report table.
- The report shows how tau and measured output change across parameter values.
- Sweep behavior is tested with small fixture data or a smoke run.

### Risks

- LTspice sweep output parsing can be more complex than single-run `.meas`.
- Reports can become cluttered if sweep size is not constrained.

### Resume Value

Demonstrates design-space exploration and practical test automation, both relevant to hardware validation roles.

## Phase 7: Portfolio Materials

### Goal

Package the project so an interviewer can understand and reproduce it quickly.

### Tasks

- Add curated examples:
  - generated `.asc`;
  - `.log` excerpt;
  - Markdown report;
  - screenshot or rendered image if useful.
- Add a concise demo script.
- Polish README badges or project metadata if needed.
- Add interview-focused diagrams and one-page summary.
- Confirm fresh-clone setup instructions.

### Acceptance Criteria

- A new user can run the RC demo from README.
- Portfolio artifacts show input, generated circuit, simulator output, and theory comparison.
- Limitations and future work are honest and clear.

### Risks

- Portfolio polish can drift into marketing instead of engineering evidence.
- Screenshots and generated artifacts can go stale if tests change.

### Resume Value

Turns the codebase into a complete, explainable engineering project rather than a private script.

## Guiding Rules

- Do not add a new circuit type without design documentation and tests.
- Do not break the RC low-pass workflow.
- Do not introduce heavy dependencies unless they remove real complexity.
- Prefer deterministic templates over broad natural-language guessing.
- Treat LTspice simulation output as the source of truth.
- Keep electrical theory visible in docs and reports.
