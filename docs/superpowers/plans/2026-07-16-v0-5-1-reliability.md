# v0.5.1 Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate false-positive LTspice simulation results and make constrained natural-language RC/RL/RLC workflows fail safely or produce electrically meaningful step responses.

**Architecture:** Keep the existing MCP interface in `mcp/server.py`. Add a small simulation-staging layer around LTspice batch execution, validation helpers at schematic-generation boundaries, and prefix-based log severity parsing; preserve reporting and theory modules.

**Tech Stack:** Python 3 standard library, `unittest`, LTspice 26.0.2 on macOS, Codex plugin manifest and Skill metadata.

## Global Constraints

- Preserve existing MCP tool names and successful response fields.
- Add no external dependencies.
- Keep arbitrary circuit synthesis, new topologies, and AC/sine analysis out of scope.
- Allow unparseable LTspice expressions while rejecting parseable zero or negative R/L/C values.
- `run_simulation.ok` is true only when the current run returns 0 and produces a fresh log.
- Release version is `0.5.1`.

---

### Task 1: Make LTspice batch execution whitespace-safe and freshness-aware

**Files:**
- Modify: `tests/test_server.py`
- Modify: `mcp/server.py`

**Interfaces:**
- Consumes: `tool_run_simulation(args: Dict[str, Any])`.
- Produces: `_simulation_outputs(path: Path) -> Dict[str, Path]`, transparent temporary staging, copied-back artifacts, and `ok`, `reason`, `staged_for_whitespace` result fields.

- [ ] **Step 1: Write failing tests for whitespace staging and stale log removal.**

```python
def test_run_simulation_stages_whitespace_path_and_copies_outputs_back(self):
    with tempfile.TemporaryDirectory(prefix="ltspice test ") as tmp:
        schematic = Path(tmp) / "test circuit.asc"
        schematic.write_text("Version 4\n", encoding="utf-8")

        def fake_run(cmd, cwd, text, capture_output, timeout):
            staged = Path(cmd[-1])
            self.assertNotIn(" ", str(staged))
            staged.with_suffix(".log").write_text("measurement: value=1\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with mock.patch.object(server, "_ltspice_executable", return_value=Path("/tmp/LTspice")), mock.patch.object(
            server.subprocess, "run", side_effect=fake_run
        ):
            result = server.tool_run_simulation({"input_path": str(schematic)})

        self.assertTrue(result["ok"])
        self.assertTrue(result["staged_for_whitespace"])
        self.assertTrue(schematic.with_suffix(".log").exists())

def test_run_simulation_does_not_accept_a_stale_log(self):
    with tempfile.TemporaryDirectory() as tmp:
        schematic = Path(tmp) / "stale.asc"
        schematic.write_text("Version 4\n", encoding="utf-8")
        schematic.with_suffix(".log").write_text("old measurement\n", encoding="utf-8")
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(server, "_ltspice_executable", return_value=Path("/tmp/LTspice")), mock.patch.object(
            server.subprocess, "run", return_value=completed
        ):
            result = server.tool_run_simulation({"input_path": str(schematic)})
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "log_missing")
        self.assertFalse(schematic.with_suffix(".log").exists())
```

- [ ] **Step 2: Run `python3 -m unittest discover -s tests -p 'test_server.py' -v` and confirm both tests fail for missing `ok`/staging behavior.**

- [ ] **Step 3: Implement simulation-output mapping, stale cleanup, temporary staging, copy-back, and explicit status.**

```python
def _simulation_outputs(path: Path) -> Dict[str, Path]:
    return {
        "log": path.with_suffix(".log"),
        "raw": path.with_suffix(".raw"),
        "op_raw": path.with_suffix(".op.raw"),
        "net": path.with_suffix(".net"),
        "db": path.with_suffix(".db"),
    }
```

Use `tempfile.TemporaryDirectory(prefix="ltspice-automation-")`, `shutil.copy2`, and a sanitized execution filename when either the input path or requested cwd contains whitespace. Remove known outputs before each run. Set `ok = proc.returncode == 0 and original_outputs["log"].exists()` and set `reason` from that value.

- [ ] **Step 4: Update `_simulation_status` to honor `simulation["ok"] is False` before inspecting a parsed log.**

- [ ] **Step 5: Run focused and complete unit suites; commit with `fix: make LTspice batch results freshness-safe`.**

### Task 2: Normalize step sources and reject invalid component values

**Files:**
- Modify: `tests/test_server.py`
- Modify: `tests/test_rl.py`
- Modify: `tests/test_rlc.py`
- Modify: `mcp/server.py`

**Interfaces:**
- Produces: `_require_positive_component(name: str, value: str) -> None` and DC-to-PULSE normalization in `tool_create_schematic_from_description`.

- [ ] **Step 1: Write failing tests.**

```python
def test_description_without_step_keyword_uses_a_step_pulse(self):
    with tempfile.TemporaryDirectory() as tmp:
        result = server.tool_create_schematic_from_description({
            "description": "Generate a basic RC low-pass with R=1k and C=1uF",
            "output_dir": tmp, "simulate": False, "open": False,
        })
    self.assertTrue(result["component_values"]["V1"].startswith("PULSE(0 1 "))

def test_create_rc_schematic_rejects_zero_capacitance(self):
    with tempfile.TemporaryDirectory() as tmp:
        with self.assertRaisesRegex(RuntimeError, "C must be positive"):
            server.tool_create_rc_schematic({"output_dir": tmp, "capacitance": "0"})
        self.assertEqual(list(Path(tmp).glob("*.asc")), [])

def test_create_rl_schematic_rejects_negative_inductance(self):
    with tempfile.TemporaryDirectory() as tmp:
        with self.assertRaisesRegex(RuntimeError, "L must be positive"):
            server.tool_create_rl_schematic({"output_dir": tmp, "inductance": "-10m"})
        self.assertEqual(list(Path(tmp).glob("*.asc")), [])

def test_create_rlc_schematic_rejects_negative_inductance(self):
    with tempfile.TemporaryDirectory() as tmp:
        with self.assertRaisesRegex(RuntimeError, "L must be positive"):
            server.tool_create_rlc_schematic({"output_dir": tmp, "inductance": "-10m"})
        self.assertEqual(list(Path(tmp).glob("*.asc")), [])
```

- [ ] **Step 2: Run focused tests and confirm failures reflect current DC/default and invalid-number behavior.**

- [ ] **Step 3: Implement `_require_positive_component`.**

```python
def _require_positive_component(name: str, value: str) -> None:
    parsed = _spice_number(_normalize_spice_value(value))
    if parsed is not None and parsed <= 0:
        raise RuntimeError(f"{name} must be positive; received {value}.")
```

Call it for every numeric R/C, R/L, and R/L/C template before analysis or measurement calculations.

- [ ] **Step 4: Convert natural-language DC sources with `_long_step_source(source)` before template-specific analysis. Remove the RLC-only duplicate conversion.**

- [ ] **Step 5: Bound single-letter R/L/C aliases so they do not match inside `RLC`, and infer explicitly unit-labeled voltages such as `5V` without requiring a following `step` token.**

- [ ] **Step 6: Run focused and complete unit suites; commit with `fix: validate components and normalize step sources`.**

### Task 3: Tighten log severity and timeout validation

**Files:**
- Modify: `tests/test_validation.py`
- Modify: `tests/test_server.py`
- Modify: `mcp/server.py`

**Interfaces:**
- Produces: prefix-based warning/error classification and a positive `timeout_seconds` requirement.

- [ ] **Step 1: Add a failing parser test containing `No errors found during post-check` and assert `errors == []`.**

- [ ] **Step 2: Add a failing `tool_run_simulation` test with `timeout_seconds=0` and assert `RuntimeError` contains `timeout_seconds must be positive`.**

- [ ] **Step 3: Replace substring severity detection with trimmed, case-insensitive prefix checks.**

```python
warning_prefixes = ("warning",)
error_prefixes = ("error", "fatal error", "failed to", "can't", "cannot")
warnings = [line.strip() for line in lines if line.strip().lower().startswith(warning_prefixes)]
errors = [line.strip() for line in lines if line.strip().lower().startswith(error_prefixes)]
```

- [ ] **Step 4: Parse `timeout_seconds` without `or` fallback and reject values `<= 0`.**

- [ ] **Step 5: Run focused and complete unit suites; commit with `fix: tighten simulation diagnostics`.**

### Task 4: Verify, document, release, and refresh the local plugin

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Modify: `mcp/server.py`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `TEST_REPORT.md`
- Modify: `skills/ltspice-automation/SKILL.md`

- [ ] **Step 1: Update metadata and docs to v0.5.1, including whitespace staging, fresh-output status, DC-to-step normalization, and positive component requirements.**

- [ ] **Step 2: Run complete release verification.**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile mcp/server.py mcp/reporting.py mcp/validation.py scripts/*.py tests/*.py
python3 scripts/smoke_test.py
python3 scripts/rl_smoke_test.py
python3 scripts/rlc_smoke_test.py
python3 scripts/rlc_smoke_test.py --output-dir "/tmp/ltspice smoke v051"
python3 /Users/a0000/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 /Users/a0000/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/ltspice-automation
git diff --check
```

If the existing smoke script has no `--output-dir`, perform the whitespace-path test through the MCP server with equivalent RLC parameters and assert `simulation_status.ok` and `validation.status`.

- [ ] **Step 3: Commit the v0.5.1 release, merge to `main`, rerun the full unit and real smoke suites, update the cachebuster, push `main`, tag `v0.5.1`, create the GitHub Release, and reinstall `ltspice-automation@personal`.**
