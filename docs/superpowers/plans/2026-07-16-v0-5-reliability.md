# v0.5 Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release v0.5.0 with guarded transient-only natural-language workflows, underdamped RLC validation, correct LTspice-path forwarding, and non-destructive default reports.

**Architecture:** Keep the existing MCP public interface and add narrowly scoped validation at the natural-language template boundary. Reuse the existing source and RLC parameter parsers; tests isolate behavior with temporary directories and mocks only where process execution is the boundary.

**Tech Stack:** Python 3 standard library, `unittest`, LTspice batch executable, Codex plugin manifest and Skill metadata.

## Global Constraints

- Preserve existing public MCP tool names and valid RC/RL/RLC step-response output.
- Support only DC/step transient workflow through natural-language generation.
- Reject known RLC damping ratios where `zeta >= 1`; preserve unparseable LTspice-expression fallback.
- Do not add dependencies or broaden circuit support.
- Default reports must be created next to generated schematics; explicit `report_path` wins.

---

### Task 1: Guard natural-language source modes and forward LTspice paths

**Files:**
- Modify: `tests/test_server.py`
- Modify: `mcp/server.py`

**Interfaces:**
- Consumes: `tool_create_schematic_from_description(args: Dict[str, Any])`.
- Produces: source-mode errors before writes and a `tool_run_simulation` call that includes `ltspice_path`.

- [ ] **Step 1: Write failing tests**

```python
def test_description_rejects_ac_source_before_writing_a_schematic(self):
    with tempfile.TemporaryDirectory() as tmp:
        with self.assertRaisesRegex(RuntimeError, "DC or step transient"):
            server.tool_create_schematic_from_description({
                "description": "Generate an AC RC low-pass frequency response",
                "output_dir": tmp, "open": False, "simulate": False,
            })
        self.assertEqual(list(Path(tmp).iterdir()), [])

def test_description_forwards_ltspice_path_to_simulation(self):
    with tempfile.TemporaryDirectory() as tmp:
        with mock.patch.object(server, "tool_run_simulation", return_value={"returncode": 1}) as run:
            server.tool_create_schematic_from_description({
                "description": "Generate a 1V step RC low-pass circuit",
                "output_dir": tmp, "open": False, "simulate": True,
                "ltspice_path": "/custom/LTspice.app",
            })
        self.assertEqual(run.call_args.args[0]["ltspice_path"], "/custom/LTspice.app")
```

- [ ] **Step 2: Run the focused tests and verify they fail because v0.4 accepts AC and omits the forwarded argument.**

Run: `python3 -m unittest tests.test_server -v`

- [ ] **Step 3: Implement the minimum guard and forwarding change**

```python
if source.upper().startswith(("AC", "SINE", "SIN")):
    raise RuntimeError("Natural-language generation supports only DC or step transient requests; use create_netlist for AC or sine analysis.")

result["simulation"] = tool_run_simulation({
    "input_path": str(path),
    "timeout_seconds": args.get("timeout_seconds", 60),
    "ltspice_path": args.get("ltspice_path"),
})
```

- [ ] **Step 4: Re-run the focused tests and the complete suite.**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'`
Expected: all tests pass.

### Task 2: Enforce the underdamped RLC boundary

**Files:**
- Modify: `tests/test_rlc.py`
- Modify: `mcp/server.py`

**Interfaces:**
- Consumes: `_rlc_parameters(resistance, inductance, capacitance, source)`.
- Produces: `_require_underdamped_rlc(...) -> None`, raising only for parseable `zeta >= 1`.

- [ ] **Step 1: Write a failing test for a critical/overdamped direct RLC request.**

```python
def test_create_rlc_schematic_rejects_non_underdamped_values(self):
    with tempfile.TemporaryDirectory() as tmp:
        with self.assertRaisesRegex(RuntimeError, "zeta < 1"):
            server.tool_create_rlc_schematic({
                "output_dir": tmp, "resistance": "100", "inductance": "10m",
                "capacitance": "10u", "source": "PULSE(0 5 0 1u 1u 100m 200m)",
            })
```

- [ ] **Step 2: Run the focused RLC tests and verify the new test fails.**

Run: `python3 -m unittest tests.test_rlc -v`

- [ ] **Step 3: Add the minimum pre-write damping guard.**

```python
def _require_underdamped_rlc(resistance, inductance, capacitance, source):
    params = _rlc_parameters(resistance, inductance, capacitance, source)
    if params and params.get("zeta") is not None and params["zeta"] >= 1:
        raise RuntimeError(f"The RLC series template requires zeta < 1; calculated zeta={params['zeta']:.6g}.")
```

Call it in both direct and natural-language RLC branches before `_write_schematic`.

- [ ] **Step 4: Re-run focused and complete unit tests.**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'`
Expected: all tests pass.

### Task 3: Make default report paths non-destructive

**Files:**
- Modify: `tests/test_reporting.py`
- Modify: `tests/test_rl.py`
- Modify: `tests/test_rlc.py`
- Modify: `mcp/server.py`

**Interfaces:**
- Consumes: generated `.asc` path and optional `report_path`.
- Produces: a sibling `<stem>_report.md` when `report_path` is omitted.

- [ ] **Step 1: Write failing tests for RC, RL, and RLC default report locations.**

```python
self.assertEqual(result["report"]["path"], str(Path(result["path"]).with_name("rc-report_report.md")))
```

Use mocked `tool_run_simulation` and `tool_parse_log` as existing report tests do.

- [ ] **Step 2: Run report tests and verify they fail because reports use `PLUGIN_ROOT / "reports"`.**

Run: `python3 -m unittest tests.test_reporting tests.test_rl tests.test_rlc -v`

- [ ] **Step 3: Add `_default_report_path(path)` and use it in all three report branches.**

```python
def _default_report_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_report.md")
```

- [ ] **Step 4: Re-run report tests and the complete suite.**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'`
Expected: all tests pass.

### Task 4: Document, verify, release, and refresh the installed plugin

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Modify: `README.md`
- Modify: `PROJECT_ROADMAP.md`
- Modify: `AUDIT.md`
- Modify: `CHANGELOG.md`
- Modify: `TEST_REPORT.md`
- Modify: `skills/ltspice-automation/SKILL.md`

- [ ] **Step 1: Update release metadata and documentation.**

Set version to `0.5.0`; state the validated source and damping boundaries, sibling report default, and current remaining roadmap.

- [ ] **Step 2: Run full release verification.**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile mcp/server.py mcp/reporting.py mcp/validation.py scripts/smoke_test.py scripts/rl_smoke_test.py scripts/rlc_smoke_test.py tests/test_server.py tests/test_reporting.py tests/test_rl.py tests/test_rlc.py tests/test_validation.py
python3 scripts/smoke_test.py
python3 scripts/rl_smoke_test.py
python3 scripts/rlc_smoke_test.py
python3 /Users/a0000/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 /Users/a0000/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/ltspice-automation
git diff --check
```

- [ ] **Step 3: Commit, push, tag, and refresh the local installation.**

Commit the release, push `codex/v0.5-reliability`, create and push annotated tag `v0.5.0`, then reinstall the plugin using the configured personal marketplace workflow.
