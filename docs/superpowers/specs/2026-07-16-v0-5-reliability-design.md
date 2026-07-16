# v0.5 Reliability Design

## Goal

Make the existing RC, RL, and underdamped series RLC workflows fail safely when a request is outside their validated transient-response scope, while preserving the v0.4 public MCP tool names and successful step-response behavior.

## Scope

v0.5 changes four behaviors.

1. `create_schematic_from_description` forwards its optional `ltspice_path` to `run_simulation`.
2. The natural-language workflow accepts only DC or PULSE sources for its transient step-response templates. It rejects AC and sine requests before creating a file, with an actionable message.
3. The RLC workflow accepts only underdamped inputs (`zeta < 1`). Direct and natural-language RLC generation reject critical or overdamped values before writing a schematic.
4. When a caller does not supply `report_path`, generated reports are saved next to the generated schematic as `<stem>_report.md`; packaged reports remain examples and are not overwritten.

The release also refreshes the README, roadmap, changelog, test report, and historical audit so documentation matches the actual v0.5 feature boundary.

## Non-Goals

- No arbitrary circuit synthesis, topology DSL, AC analysis, sine-response validation, Buck converter, parameter sweep, parallel RLC, or critically/overdamped RLC support.
- No MCP protocol change, dependency addition, or refactor of the existing single-file server architecture.
- No change to explicit caller-provided `analysis`, `measures`, or `report_path` semantics beyond the source/topology guardrails.

## Design

`_source_from_description` continues to identify a requested source, but the natural-language entry point validates the normalized source before selecting a circuit template. `PULSE(...)` is valid. DC input is converted to a long-duration step pulse so RC/RL/RLC theory and measurement directives retain a transient response; AC and sine sources produce a `RuntimeError` that names the unsupported analysis class and directs callers to explicit netlists.

RLC damping is calculated with the existing `zeta = R / 2 * sqrt(C / L)` expression. A new validation helper returns the parsed damping ratio when component values are valid, and generation raises before writing when `zeta >= 1`. Unparseable values retain existing fallback behavior, because callers may intentionally provide LTspice expressions that cannot be statically evaluated.

The natural-language simulation call passes `ltspice_path` through unchanged. Report defaults use `path.with_name(f"{path.stem}_report.md")`; explicit `report_path` still wins.

## Error Handling

- Unsupported AC/sine source: fail before a file is written, state that v0.5 supports only DC/step transient workflows, and suggest `create_netlist` for custom analysis.
- Known critical/overdamped RLC values: fail before a file is written, include the computed damping ratio, and state that the current template requires `zeta < 1`.
- Unparseable values: do not falsely reject them; LTspice remains the final evaluator.

## Tests and Release Evidence

Unit tests must demonstrate each guardrail, report location behavior, and path forwarding by observing `tool_run_simulation` arguments. Existing 20 tests remain green. Release verification must run Python compilation, all unit tests, RC/RL/RLC real LTspice smoke scripts, plugin validation, Skill validation, and `git diff --check`.

## Release and Local Installation

The release version is `0.5.0`. After the release commit is pushed, the local plugin installation is refreshed from this plugin source using the plugin-development reinstall/cache-busting workflow, so newly opened Codex tasks load the v0.5.0 Skill rather than the cached v0.4.0 copy.
