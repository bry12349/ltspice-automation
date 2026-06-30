# LTspice Automation

Codex plugin that turns natural-language circuit requests into visible LTspice
schematics, opens them in the LTspice GUI, validates them with batch simulation,
and parses measurement results.

This project is designed as a small but complete agentic engineering workflow:
it bridges natural-language intent, deterministic file generation, desktop app
automation, simulation verification, and result interpretation.

## Highlights

- Natural language to LTspice `.asc` schematic generation.
- Opens generated schematics in the LTspice desktop app for visual inspection.
- Runs LTspice batch simulations to verify generated circuits.
- Parses `.log` files for warnings, errors, and `.meas` results.
- Ships as a local Codex plugin with MCP tools and a reusable skill.
- Includes a smoke test that validates the full RC low-pass workflow.

The first stable workflow is intentionally narrow: generate a visible RC
low-pass `.asc` schematic, open it in LTspice, run a batch simulation, and parse
the `.log` measurements. The plugin favors correctness over broad but fragile
GUI automation.

## What it does

Example request:

> Generate a 1 V step-input RC low-pass circuit with R=1k and C=1uF, open the
> visible LTspice schematic, run it, and explain the result.

The plugin can:

1. Create an LTspice `.asc` schematic with visible voltage source, resistor,
   capacitor, wiring, node labels, `.tran`, and `.meas` directives.
2. Open the `.asc` file in the LTspice GUI so the user can inspect/edit it.
3. Run LTspice in batch mode to verify the generated schematic is electrically
   valid.
4. Parse `.log` output for warnings, errors, and measured values.

## Demo result

For a 1 V step input with `R=1k` and `C=1uF`, the generated schematic produces:

```text
vout_at_1ms = 0.631937 V
vout_at_5ms = 0.993259 V
tau_cross   = 1.000497 ms
```

That matches the expected RC time constant of `1 ms`, where the output reaches
about 63.2% of the final value.

An example schematic is included at:

```text
examples/rc-lowpass-step.asc
```

## Tools

- `detect_ltspice`: finds `/Applications/LTspice.app` or a supplied executable path.
- `create_netlist`: writes a `.cir` file from explicit SPICE lines or a built-in RC low-pass template.
- `create_rc_schematic`: writes a visible LTspice `.asc` schematic for an RC step-response circuit.
- `create_schematic_from_description`: converts a natural-language RC low-pass request into a visible `.asc`, optionally opens LTspice and simulates it.
- `open_schematic`: opens an existing `.asc` in the LTspice GUI.
- `run_simulation`: runs LTspice batch mode with `-b`.
- `parse_log`: extracts warnings, errors, measurements, and log tail text.

## Current scope

Stable:

- RC low-pass transient response schematics.
- Basic explicit SPICE netlist generation.
- Batch simulation and log parsing.

Not yet promoted to stable:

- Arbitrary LTspice schematic drawing.
- Op-amp circuits, switching regulators, transistor circuits.
- KiCad/PCB design.

Those can be added template-by-template, with regression tests that confirm the
generated `.asc` netlist has the expected nodes.

## Project structure

```text
ltspice-automation/
├── .codex-plugin/plugin.json
├── .mcp.json
├── mcp/server.py
├── skills/ltspice-automation/SKILL.md
├── scripts/smoke_test.py
├── examples/rc-lowpass-step.asc
├── README.md
└── LICENSE
```

## Installation in Codex

Install the local plugin from a personal marketplace or copy the repository into
your plugin source path, then add it from Codex:

```bash
codex plugin add ltspice-automation@personal
```

Restart Codex or open a new thread so the MCP tools and skill are loaded.

## Smoke test

From the plugin root:

```bash
python3 scripts/smoke_test.py
```

The test creates an RC low-pass schematic, runs LTspice, and verifies that
`V(out)` at `1 ms` is near `0.632 V`.

## Why this exists

Most AI coding workflows stop at generating text files. This plugin demonstrates
a tighter loop for engineering software: generate a circuit artifact, open it in
the real desktop tool, run the simulator, and inspect the measured output before
reporting success.

## Notes

This plugin is file-first but not headless-only. It writes `.asc` files because
that is the stable interface LTspice itself understands, then opens those files
in LTspice for the visible schematic experience.

Start a new Codex thread after installing or reinstalling the plugin so the MCP tools and skill are loaded.
