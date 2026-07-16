# LTspice Automation Audit

## v0.5.1 Status Update

Date: 2026-07-16

This document began as the v0.2 static audit below. Its statements that RL/RLC, theory validation, reports, and unit tests are unsupported are historical and no longer describe the released project.

Current verified boundary:

- RC low-pass, series RL, and parseable underdamped series RLC step-response templates;
- visible `.asc` generation, LTspice batch simulation, `.log` parsing, theory validation, and Markdown reporting;
- natural-language templates limited to DC/step transient work; AC, sine, and frequency-response requests require explicit netlists;
- RLC values with `zeta >= 1` are rejected before file creation;
- LTspice paths containing whitespace are staged transparently, and only fresh output files can satisfy simulation success;
- parseable R/L/C values must be positive, while natural-language DC/default sources are normalized to step pulses;
- default generated reports are sibling files of their schematics, leaving committed example reports unchanged.

Outstanding scope remains intentionally constrained: arbitrary circuit synthesis, AC workflow generation, critical/overdamped RLC, Buck converters, parameter sweeps, and PCB/KiCad are not supported.

The remainder is retained as the 2026-07-01 historical audit record.

---

Audit date: 2026-07-01

Scope: read-only review of `README.md`, `.codex-plugin/plugin.json`, `.mcp.json`, `mcp/server.py`, `scripts/smoke_test.py`, `skills/ltspice-automation/SKILL.md`, `examples/rc-lowpass-step.asc`, and repository structure. No functional code was modified in this phase.

## 1. Current Functionality Summary

### Supported Circuits

Stable, documented circuit support:

- RC low-pass transient response schematic generation.
- Basic RC low-pass SPICE netlist generation through `create_netlist`.
- Explicit custom SPICE netlist generation when callers provide raw `lines`.

Implemented but not promoted to stable:

- `mcp/server.py` contains helper functions for RC high-pass and voltage divider `.asc` generation, but `create_schematic_from_description` intentionally rejects those circuit types before use. The public schema for natural-language schematic generation only exposes `rc_lowpass`.

Unsupported today:

- RL, RLC, op-amp circuits, transistor circuits, switching converters, Buck converter, parameter sweeps, arbitrary schematic synthesis, PCB/KiCad workflows.

### Supported LTspice Operations

The MCP server exposes these tools:

- `detect_ltspice`: detects LTspice on macOS-style paths or in `PATH`.
- `create_netlist`: writes `.cir` files from explicit SPICE lines or a built-in RC low-pass netlist template.
- `create_rc_schematic`: writes a visible `.asc` schematic for an RC step-response circuit.
- `create_schematic_from_description`: parses a narrow natural-language RC low-pass request, writes `.asc`, optionally runs LTspice batch simulation, optionally opens the schematic.
- `open_schematic`: opens an existing `.asc` with macOS `open`.
- `run_simulation`: runs LTspice with `-b` against `.cir`, `.net`, or `.asc`.
- `parse_log`: extracts warning lines, error-like lines, measurement-like key/value entries, and log tail text.

### `.asc` Generation

Yes. The project can generate visible LTspice `.asc` files with voltage source, resistor, capacitor, ground, wiring, node labels, `.tran`, and `.meas` directives.

There are two RC schematic paths:

- `create_rc_schematic`, a direct parameterized tool.
- `create_schematic_from_description`, a natural-language wrapper that currently accepts only RC low-pass as a stable visual schematic type.

The example schematic `examples/rc-lowpass-step.asc` matches the default 1 V step, `R=1k`, `C=1uF`, `.tran 0 6m 0 10u`, and measurements at 1 ms and 5 ms plus a tau crossing.

### Simulation Execution

Yes, if LTspice is installed and detectable. `run_simulation` invokes:

```bash
LTspice -b <input_path>
```

`create_schematic_from_description` defaults to `simulate=True`, so the natural-language workflow attempts simulation unless explicitly disabled.

### `.log` Parsing

Yes. `parse_log` reads an LTspice `.log` file and returns:

- first 50 warning lines;
- first 50 error-like lines;
- measurement-like key/value pairs;
- final 80 log lines.

The parser is simple string/regex based. It does not currently produce typed numeric measurement values, units, pass/fail assertions, or structured simulation diagnostics.

### `.meas` Support

Yes. Generated RC step schematics include `.meas` directives. Defaults:

- `vout_at_1ms`: `FIND V(out) AT=1m`
- `vout_at_5ms`: `FIND V(out) AT=5m`
- `tau_cross`: `WHEN V(out)=0.632120558 RISE=1`

The parser can extract measurement names and values from the `.log`, but the project does not yet compare them against theoretical RC values in code.

### Cross-Platform Support

Partial.

- Detection checks `PATH`, `/Applications/LTspice.app`, and `~/Applications/LTspice.app`.
- GUI opening uses macOS `open`, so `open_schematic` is macOS-specific.
- Version detection uses macOS `.app` `Info.plist`.
- Batch mode may work on other platforms if `LTspice` is in `PATH` or an executable path is supplied, but this is not documented or verified.

Current practical stability target: macOS with LTspice installed as `/Applications/LTspice.app` or available as `LTspice` in `PATH`.

### Current Stable Boundary

The stable boundary is narrow and valuable:

- Generate a visible RC low-pass step-response `.asc`.
- Use a 1 V step with `R=1k`, `C=1uF` defaults or simple extracted values.
- Run batch simulation on a local LTspice installation.
- Parse `.log` for `.meas` output.
- Validate the default RC workflow with `scripts/smoke_test.py`.

Outside that boundary, the project should be treated as a draft:

- Natural-language parsing is heuristic.
- Measurement directives are tuned to the default 1 V, 1 ms time constant case.
- Cross-platform behavior is incomplete.
- Error handling is mostly raw exception strings.
- Tests are smoke-level only.

## 2. Issue Classification

### P0: Core-Function Failure

No definite P0 issue was found from static repository audit. The default documented RC low-pass workflow is coherently implemented and has a smoke-test entry point.

The project does have P1 issues that can become core workflow failures for non-default parameters or missing LTspice configuration. Those should be addressed before expanding scope.

### P1: Reliability, UX, or Result-Correctness Issues

#### P1-1: Tau measurement assumes a 1 V final value

- File position: `mcp/server.py:381`, `mcp/server.py:385`, `mcp/server.py:153`
- Problem: `.meas tran tau_cross WHEN V(out)=0.632120558 RISE=1` is hard-coded to 0.632 V, not `0.632120558 * Vin`.
- Why this is a problem: For a 1 V step this represents 1 tau. For a 5 V step, the 63.2% target should be about 3.1606 V. For a 0.5 V step, 0.632 V is unreachable.
- Possible consequence: Incorrect tau results, failed `.meas` commands, misleading reports, or false confidence in simulation correctness for any Vin other than 1 V.
- Recommended fix: Compute measurement targets from parsed or explicit source amplitude, or document that the tau measurement is only valid for 1 V. Prefer a helper that derives `v_tau = 0.632120558 * final_voltage`.
- Suggested for this round: Yes, if confirmed by tests in Phase 2. This is a P1 result-correctness issue.

#### P1-2: Fixed 1 ms and 5 ms measurement points are not parameter-aware

- File position: `mcp/server.py:153`, `mcp/server.py:381`, `scripts/smoke_test.py:52`
- Problem: Default measurements always sample at 1 ms and 5 ms, regardless of `R*C`.
- Why this is a problem: For non-default RC values, 1 ms and 5 ms may no longer represent 1 tau and 5 tau.
- Possible consequence: The tool can generate electrically valid schematics but present measurements that do not mean what users expect.
- Recommended fix: Parse R and C into numeric SI values, compute `tau = R*C`, and generate measurement names/points from `tau` and `5*tau`. Keep the current names for the default case or add explicit `vout_at_1tau` and `vout_at_5tau`.
- Suggested for this round: Yes, but only after adding focused tests so the current RC workflow is preserved.

#### P1-3: SI suffix normalization can misinterpret mega-ohm values

- File position: `mcp/server.py:207`
- Problem: `_normalize_spice_value` removes `Ω` before checking `MΩ`, so `1MΩ` becomes `1M`, not `1Meg`. In SPICE conventions this can be ambiguous or wrong because `m` commonly means milli.
- Why this is a problem: Natural-language requests with mega-ohm components can produce incorrect component values.
- Possible consequence: Simulations may be off by orders of magnitude.
- Recommended fix: Normalize compound unit strings before removing unit suffixes, and add unit tests for `1MΩ`, `1meg`, `1 kΩ`, `1uF`, Chinese unit forms, and plain LTspice suffixes.
- Suggested for this round: Yes. This is a small, high-value correctness fix.

#### P1-4: Simulation failure does not guarantee parsed log diagnostics are returned

- File position: `mcp/server.py:403`, `mcp/server.py:405`
- Problem: `create_schematic_from_description` only parses the log if the expected `.log` path exists. If LTspice fails before writing a log, `log` remains `None`; if LTspice returns nonzero but a log exists, the result is returned without higher-level failure classification.
- Why this is a problem: Callers must inspect several fields manually and can easily miss an invalid simulation.
- Possible consequence: Agent responses may claim generation succeeded while simulation failed or produced no measurable result.
- Recommended fix: Return a structured `simulation_status` or `ok` field based on return code, log presence, errors, and expected measurements. Avoid changing existing fields.
- Suggested for this round: Yes, if it can be added compatibly.

#### P1-5: Log error detection is broad and can produce false positives

- File position: `mcp/server.py:482`
- Problem: Any line containing markers like `error`, `failed`, `expected`, `unknown`, `cannot`, or `not found` is treated as an error.
- Why this is a problem: LTspice logs or comments may contain non-fatal text that matches these markers.
- Possible consequence: Valid simulations can be reported as failed, or users may see noisy diagnostics.
- Recommended fix: Separate severity parsing into explicit categories, prefer LTspice-known error prefixes, and keep broad matches as `diagnostic_matches` rather than hard `errors`.
- Suggested for this round: Maybe. Fix after Phase 2 shows actual log behavior.

#### P1-6: GUI opening is macOS-specific but exposed as a general tool

- File position: `mcp/server.py:413`, `mcp/server.py:424`
- Problem: `open_schematic` always invokes macOS `open`.
- Why this is a problem: README and tool descriptions do not clearly say GUI opening is macOS-only.
- Possible consequence: Windows/Linux users can generate and simulate but fail at the GUI step with unclear errors.
- Recommended fix: Detect platform before GUI open and return a clear unsupported-platform message. Document platform support.
- Suggested for this round: Yes, at least as error-message/documentation hardening.

### P2: Code Quality, Maintainability, or Test Coverage Issues

#### P2-1: `mcp/server.py` mixes JSON-RPC, parsing, schematic templates, LTspice execution, and log parsing

- File position: `mcp/server.py:1`
- Problem: The server is a single 657-line module containing unrelated responsibilities.
- Why this is a problem: Future RL/RLC/Buck expansion will make this file harder to reason about and test.
- Possible consequence: Template changes can accidentally affect MCP protocol handling or execution behavior.
- Recommended fix: In later phases, split into small modules such as `ltspice_paths.py`, `schematics/rc.py`, `simulation.py`, `log_parser.py`, and `server.py`.
- Suggested for this round: No. Avoid refactor during P0/P1 stabilization.

#### P2-2: No unit test suite for parser and schematic generation helpers

- File position: `scripts/smoke_test.py:1`
- Problem: The only test entry point is an integration smoke test that requires LTspice.
- Why this is a problem: Many important behaviors can be tested without LTspice, including generated `.asc` lines, value parsing, duplicate `.meas` behavior, log parser behavior, and overwrite protection.
- Possible consequence: Regressions will be caught late and only on machines with LTspice installed.
- Recommended fix: Add lightweight `pytest` tests or standard-library `unittest` tests for pure functions and file generation.
- Suggested for this round: Yes, for any P1 fixes. Keep tests minimal.

#### P2-3: Natural-language parsing is heuristic and undocumented

- File position: `mcp/server.py:194`, `mcp/server.py:238`, `mcp/server.py:247`
- Problem: Parsing rules are regex-based with limited vocabulary and no documented grammar.
- Why this is a problem: Users may assume broader AI-style understanding than the code provides.
- Possible consequence: Silent defaults can mask missed parameters.
- Recommended fix: Return parsed assumptions explicitly and document supported phrases/units.
- Suggested for this round: No, except where needed for P1 fixes.

#### P2-4: Dead or blocked template helpers can confuse maintainers

- File position: `mcp/server.py:292`, `mcp/server.py:319`, `mcp/server.py:375`
- Problem: RC high-pass and voltage-divider template functions exist but the public workflow rejects those circuit types.
- Why this is a problem: It is unclear whether they are experimental, abandoned, or waiting for tests.
- Possible consequence: Future contributors may expose them without proper validation.
- Recommended fix: Mark them as experimental in comments or move them behind tests before exposing.
- Suggested for this round: No.

#### P2-5: Smoke test checks measurement text by substring

- File position: `scripts/smoke_test.py:52`
- Problem: The smoke test accepts measurements containing `"0.631"` or `"0.632"` as raw strings.
- Why this is a problem: It does not parse numeric values or enforce tolerance.
- Possible consequence: Formatting changes can break tests, and inaccurate values can pass if the substring appears incidentally.
- Recommended fix: Parse the numeric prefix and assert against a tolerance around `1 - exp(-1)`.
- Suggested for this round: Yes if touching measurement behavior.

#### P2-6: README is good for a prototype but lacks engineering setup detail

- File position: `README.md:101`
- Problem: README does not fully document LTspice path configuration, platform limitations, expected outputs, troubleshooting, or roadmap.
- Why this is a problem: Recruiters/interviewers and users cannot easily reproduce or evaluate the project.
- Possible consequence: The project looks more like a local demo than a reusable engineering tool.
- Recommended fix: Address in Phase 4 with architecture, setup, FAQ, example outputs, theory-vs-simulation table, and roadmap.
- Suggested for this round: No. This is explicitly Phase 4.

#### P2-7: Tracked `.DS_Store` conflicts with `.gitignore`

- File position: `.DS_Store`, `.gitignore:3`
- Problem: `.gitignore` excludes `.DS_Store`, but `git ls-files` shows `.DS_Store` is tracked.
- Why this is a problem: It is machine-specific metadata unrelated to the plugin.
- Possible consequence: Noise in repository history and unnecessary diffs.
- Recommended fix: Remove `.DS_Store` from version control in a cleanup phase.
- Suggested for this round: No functional impact; defer.

### P3: Future Extension Suggestions

#### P3-1: Add theory calculation and simulation comparison layer

- File position: future module, likely after `mcp/server.py:464`
- Problem: The project currently parses `.meas` but does not compute theory values or error percentages.
- Why this matters: Theory-vs-simulation comparison is the most resume-relevant engineering value.
- Possible consequence if not added: The tool remains a simulator wrapper rather than an engineering validation workflow.
- Recommended fix: Add small pure-Python calculators for RC first, then RL/RLC later.
- Suggested for this round: No. This belongs after stabilization.

#### P3-2: Add Markdown report generation

- File position: future `reports` or `mcp/reporting.py`
- Problem: Results are returned as JSON but not turned into a shareable artifact.
- Why this matters: A Markdown report makes the project easier to demo and attach to a portfolio.
- Possible consequence if not added: Users must manually summarize results.
- Recommended fix: Add a modular report generator after log parsing and theory comparison are stable.
- Suggested for this round: No. This is Phase 5.

#### P3-3: Add RL and RLC templates only after design docs and RC regression tests

- File position: future schematic modules and docs
- Problem: New circuit families need verified `.asc`, `.tran`, `.meas`, parser, theory, and tests.
- Why this matters: Expanding too early risks breaking the best working demo.
- Possible consequence if rushed: Broad but unreliable circuit support.
- Recommended fix: Design RL first in `docs/RL_TEMPLATE_DESIGN.md`; implement only after confirmation.
- Suggested for this round: No.

#### P3-4: Add parameter sweep support

- File position: future schematic/report modules
- Problem: No `.step` generation or sweep result parsing exists.
- Why this matters: Parameter sweeps are highly relevant to circuit design and hardware validation.
- Possible consequence if not added: The tool remains limited to single-point simulations.
- Recommended fix: After RC and RL reports work, add controlled `.step param` templates and table extraction.
- Suggested for this round: No.

#### P3-5: Add portfolio-oriented examples

- File position: future `examples/`, `reports/`, and README
- Problem: Only one example `.asc` is included.
- Why this matters: A resume project benefits from reproducible examples with artifacts.
- Possible consequence if not added: Harder for interviewers to understand the value quickly.
- Recommended fix: Include generated schematic, log excerpt, report, and theory table for each stable circuit.
- Suggested for this round: No.

## 3. Project Value Judgment for an Electrical Engineering Internship Resume

### Most Worth Keeping

- The narrow but real RC low-pass workflow. It connects circuit theory, schematic generation, LTspice batch simulation, `.meas` extraction, and result interpretation.
- The visible `.asc` output. This is stronger than only generating a netlist because it fits how LTspice users inspect circuits.
- The file-first automation boundary. It avoids fragile GUI clicking while still allowing GUI inspection.
- The MCP/Codex plugin packaging. It demonstrates AI-assisted engineering workflow rather than a standalone script only.
- The smoke test concept. It shows the author understands regression checks for engineering automation.

### Most Worth Strengthening

- Theory-vs-simulation comparison for RC time constant and step response.
- Typed measurement parsing with numeric tolerance checks.
- Clear LTspice environment detection and actionable error messages.
- Minimal but real tests that do not all require LTspice.
- Markdown report generation that turns simulation output into an engineering artifact.
- Documentation that explains both the electrical theory and automation architecture.

### Best Resume Framing

Strong framing:

> Built a local Codex/LTspice automation plugin that converts constrained natural-language RC circuit requests into visible LTspice schematics, runs batch simulations, parses `.meas` results, and validates outputs against first-order RC theory.

Skills demonstrated:

- Circuit simulation with LTspice.
- First-order RC transient analysis.
- SPICE directives including `.tran` and `.meas`.
- Python automation and subprocess control.
- Log parsing and result validation.
- Tool/plugin design with a narrow, testable engineering workflow.
- AI-assisted workflow design with explicit stability boundaries.

What not to overclaim yet:

- Do not claim arbitrary natural-language circuit synthesis.
- Do not claim full cross-platform support.
- Do not claim Buck/RL/RLC support until implemented and tested.
- Do not claim robust theory comparison or report generation until later phases are complete.

### Priority Recommendation

Before adding new circuit families, stabilize the default RC workflow:

1. Add focused tests around schematic generation, value parsing, and log parsing.
2. Fix measurement parameterization for Vin and tau.
3. Improve simulation status/error reporting.
4. Add theory comparison and Markdown report output.
5. Only then design and implement RL.

This sequence keeps the project credible: small scope, real simulator integration, measurable correctness, and clear engineering value.
