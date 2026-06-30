# LTspice Automation

Local Codex plugin for turning natural-language circuit requests into visible
LTspice schematics.

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

## Smoke test

From the plugin root:

```bash
python3 scripts/smoke_test.py
```

The test creates an RC low-pass schematic, runs LTspice, and verifies that
`V(out)` at `1 ms` is near `0.632 V`.

## Notes

This plugin is file-first but not headless-only. It writes `.asc` files because
that is the stable interface LTspice itself understands, then opens those files
in LTspice for the visible schematic experience.

Start a new Codex thread after installing or reinstalling the plugin so the MCP tools and skill are loaded.
