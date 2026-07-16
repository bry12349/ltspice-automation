# v0.5.1 Reliability Design

## Goal

Prevent LTspice execution and validation from reporting false success, make natural-language step-response requests electrically meaningful by default, and reject invalid component values with actionable errors.

## Confirmed Root Causes

1. LTspice 26.0.2 on macOS silently produces no artifacts when the batch input path contains a space, while still returning process code 0.
2. `tool_run_simulation` considers any existing `.log/.raw/.op.raw` file an output of the current run. A stale valid log can therefore turn a failed run into `simulation_passed` and validation `PASS`.
3. `_source_from_description` defaults to `DC <Vin>` when the request omits the word "step". The generated `.tran` analysis starts from the DC operating point, but validation compares it with a zero-to-Vin step response.
4. Numeric component values are not checked for positivity. Zero RC values generate `.tran 0 0`; negative RLC values enter complex-number calculations and expose an internal Python type error.
5. Log severity detection uses substring matching, so benign text such as "No errors found" is classified as an error.
6. Single-letter parameter aliases are not token-bounded, so the `C` in `5V RLC` can consume the input voltage as capacitance.
7. Input voltage inference only recognizes unnamed amplitudes when they are followed by `step`/`阶跃`, so plain `5V RLC` falls back to 1V.

## Considered Approaches

### Recommended: transparent staging and strict freshness

When the input path or working directory contains whitespace, copy the input to a temporary directory whose path contains no whitespace, run LTspice there, then copy only newly generated artifacts back beside the original input. Before every run, remove the known derived outputs in the actual execution directory so stale data cannot be mistaken for current output. Return explicit `ok` and `reason` fields from `run_simulation` while preserving existing response fields.

This keeps the public API usable in ordinary folders such as `ltspice 2` and directly addresses both the path failure and stale-output false positive.

### Alternative: reject whitespace paths

This is smaller but forces users to rename folders or manually stage files. It is unsuitable for a local automation plugin intended to work in normal Finder-created directories.

### Alternative: add quoting around the path

The subprocess already passes arguments without a shell, so quoting is not the cause. Adding literal quotes would send incorrect path characters to LTspice and would not solve the observed behavior.

## Detailed Behavior

### Simulation execution

- `tool_run_simulation` validates that `timeout_seconds` is positive.
- Known old derived files (`.log`, `.raw`, `.op.raw`, `.net`, `.db`) are removed from the execution location before invoking LTspice.
- Whitespace paths use `tempfile.TemporaryDirectory(prefix="ltspice-automation-")`; the input is copied there with the same filename.
- Generated derived files are copied back beside the original input after the subprocess exits.
- `ok` is true only when the process returns 0 and a new `.log` exists.
- `reason` distinguishes `simulation_passed`, `ltspice_returncode_nonzero`, and `log_missing`.
- `_simulation_status` consumes these explicit fields and never infers success from a stale log.

### Natural-language sources

- Explicit `PULSE(...)` input remains unchanged.
- A parsed or explicit `DC <Vin>` source is converted to the existing long zero-to-Vin pulse used by step-response templates.
- An explicitly unit-labeled voltage such as `5V` is used as Vin even when the request omits the word "step".
- AC and sine sources remain rejected.

### Component validation

- When R, L, or C parses as a numeric SPICE value, it must be greater than zero.
- Invalid numeric values raise `RuntimeError` naming the component and requiring a positive value before a schematic is written.
- Unparseable LTspice expressions remain allowed and are left for LTspice to evaluate.
- The underdamped RLC check continues after positivity validation.
- Single-letter R/L/C aliases match only standalone parameter tokens, not letters embedded in words such as `RLC`.

### Log severity

- Warnings are lines whose trimmed text begins with `warning`.
- Errors are lines whose trimmed text begins with `error` or `fatal error`, plus known LTspice failure prefixes such as `failed to` and `can't`.
- General prose containing words such as "error", "expected", or "not found" is not promoted to a fatal error.

## Compatibility

- Existing MCP tool names, arguments, and successful result fields remain intact.
- `run_simulation` adds `ok`, `reason`, and `staged_for_whitespace` fields.
- Valid RC/RL/RLC step workflows and explicit report paths remain unchanged.
- The patch version becomes `0.5.1`.

## Verification

- Unit tests must demonstrate red-green behavior for whitespace staging, stale-output rejection, DC-to-step conversion, positive component validation, timeout validation, and benign log prose.
- Real LTspice smoke tests must run RC, RL, and RLC in the repository path and an additional RLC workflow in a directory containing spaces.
- Python compilation, plugin validation, Skill validation, and whitespace checks must pass before release.
