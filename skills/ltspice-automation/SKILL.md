---
name: ltspice-automation
description: Turn natural-language RC low-pass requests into visible LTspice .asc schematics, open them in LTspice, run simulations, and parse logs. Use for LTspice schematic generation, inspection, simulation, or troubleshooting.
---

# LTspice Automation

Use this skill when a task involves LTspice, visible `.asc` schematics, SPICE netlists, circuit simulation, transient analysis, or parsing LTspice output.

## Workflow

1. Detect LTspice first with `detect_ltspice`.
2. When the user asks in natural language for a visible circuit, use `create_schematic_from_description`.
3. Default to opening the generated `.asc` in LTspice unless the user asks for a file-only workflow.
4. Run batch simulation and parse the `.log` before claiming the circuit is valid.
5. Explain assumptions and measured values in ordinary engineering terms.
6. Use explicit netlists for unsupported circuit types until a verified `.asc` template exists.

## Boundaries

- Do not overwrite existing circuit files unless the user asks or `overwrite=true` is safe and explicit.
- Treat generated circuit designs as engineering drafts. Ask for voltage/current/power requirements when missing and call out assumptions.
- The stable natural-language visual schematic generator currently supports RC low-pass circuits. Do not pretend arbitrary schematic synthesis is supported.
- For PCB or KiCad work, use a KiCad-specific workflow; this skill only covers LTspice simulation automation.
