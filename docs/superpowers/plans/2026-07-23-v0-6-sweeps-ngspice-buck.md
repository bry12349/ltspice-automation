# LTspice Automation v0.6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bounded RC/Buck parameter sweeps, waveform CSV/SVG/metrics, a portable ngspice backend with Linux CI, and one constrained asynchronous Buck converter workflow.

**Architecture:** New portable workflows generate one `.cir` file per simulation and normalize LTspice/ngspice results into the same waveform table. Sweep orchestration runs isolated points and aggregates their CSV data and metrics; existing RC/RL/RLC LTspice APIs remain unchanged.

**Tech Stack:** Python 3 standard library, MCP JSON-RPC over stdio, LTspice 26 batch mode, ngspice batch mode, `unittest`, GitHub Actions.

## Global Constraints

- Preserve every v0.5.1 public tool and accepted successful RC/RL/RLC behavior.
- Support exactly RC `resistance`/`capacitance` and Buck `duty_cycle` sweeps.
- Accept 2 through 20 explicit sweep values and exactly one swept parameter.
- Keep waveform CSV and SVG generation dependency-free.
- Generate a visible LTspice Buck `.asc` and a portable `.cir` from one validated parameter object.
- Do not add arbitrary circuit generation, arbitrary `.step`, synchronous Buck, boost, flyback, closed-loop control, STM32 firmware, or op-amp workflows.
- A failed or stale simulator output must never produce validation PASS.
- Publish only after local LTspice/ngspice verification and Linux CI are green.

---

## File Structure

- Create `mcp/backends.py`: simulator discovery, selection, execution, and normalized run status.
- Create `mcp/waveforms.py`: waveform parsing, validation, CSV, SVG, downsampling, and metrics.
- Create `mcp/buck.py`: validated Buck parameters, `.cir`, `.asc`, expected-value calculations, and report rendering.
- Create `mcp/sweeps.py`: whitelist validation, per-point orchestration, aggregate CSV/SVG/report generation.
- Modify `mcp/server.py`: MCP handlers and schemas for the four new public tools.
- Modify `mcp/reporting.py`: shared artifact/reproduction formatting where needed.
- Create `tests/fixtures/ngspice_rc_wrdata.txt`: stable ngspice table parser fixture.
- Create `tests/fixtures/ltspice_rc_ascii.txt`: minimal LTspice ASCII RAW parser fixture.
- Create `tests/test_backends.py`: backend unit tests.
- Create `tests/test_waveforms.py`: waveform, metric, CSV, and SVG unit tests.
- Create `tests/test_buck.py`: Buck generation, validation, and report unit tests.
- Create `tests/test_sweeps.py`: sweep validation, orchestration, and partial-failure unit tests.
- Modify `tests/test_server.py`: tool registration, compatibility, and handler integration tests.
- Create `scripts/ngspice_smoke_test.py`: portable RC and Buck ngspice smoke test.
- Create `scripts/buck_smoke_test.py`: real LTspice Buck smoke test.
- Create `scripts/sweep_smoke_test.py`: RC R sweep and Buck duty sweep smoke test.
- Create `.github/workflows/ci.yml`: Linux unit, compile, validation, and ngspice smoke gates.
- Modify `.codex-plugin/plugin.json`, `skills/ltspice-automation/SKILL.md`, `skills/ltspice-automation/agents/openai.yaml`, `README.md`, `INSTALL.md`, `PROJECT_ROADMAP.md`, `CHANGELOG.md`, `TEST_REPORT.md`, and `.mcp.json`: v0.6 documentation and metadata.

---

### Task 1: Simulator Backend Discovery and Execution

**Files:**
- Create: `mcp/backends.py`
- Create: `tests/test_backends.py`

**Interfaces:**
- Produces: `detect_simulators(ltspice_path=None, ngspice_path=None) -> dict`
- Produces: `select_backend(name, detections) -> str`
- Produces: `run_portable(input_path, backend="auto", timeout_seconds=60, ltspice_path=None, ngspice_path=None) -> dict`
- Result keys: `ok`, `reason`, `backend`, `executable`, `command`, `cwd`, `returncode`, `stdout`, `stderr`, `raw_path`, `log_path`

- [ ] **Step 1: Write failing discovery and selection tests**

```python
class BackendSelectionTests(unittest.TestCase):
    def test_auto_prefers_ltspice_then_ngspice(self):
        both = {"ltspice": {"found": True}, "ngspice": {"found": True}}
        linux = {"ltspice": {"found": False}, "ngspice": {"found": True}}
        self.assertEqual(backends.select_backend("auto", both), "ltspice")
        self.assertEqual(backends.select_backend("auto", linux), "ngspice")

    def test_explicit_missing_backend_fails(self):
        detected = {"ltspice": {"found": False}, "ngspice": {"found": True}}
        with self.assertRaisesRegex(RuntimeError, "LTspice backend is not available"):
            backends.select_backend("ltspice", detected)
```

- [ ] **Step 2: Run tests and confirm the expected import failure**

Run: `python3 -m unittest tests.test_backends -v`

Expected: `ImportError: cannot import name 'backends' from 'mcp'`.

- [ ] **Step 3: Implement discovery and backend selection**

```python
def detect_simulators(ltspice_path=None, ngspice_path=None):
    lt = _find_ltspice(ltspice_path)
    ng = _find_executable(ngspice_path, "ngspice")
    return {
        "ltspice": {"found": lt is not None, "executable": str(lt) if lt else None},
        "ngspice": {"found": ng is not None, "executable": str(ng) if ng else None},
    }

def select_backend(name, detections):
    if name not in {"auto", "ltspice", "ngspice"}:
        raise RuntimeError("backend must be auto, ltspice, or ngspice")
    if name == "auto":
        for candidate in ("ltspice", "ngspice"):
            if detections[candidate]["found"]:
                return candidate
        raise RuntimeError("Neither LTspice nor ngspice is available")
    if not detections[name]["found"]:
        label = "LTspice" if name == "ltspice" else "ngspice"
        raise RuntimeError(f"{label} backend is not available")
    return name
```

- [ ] **Step 4: Add failing process and freshness tests**

```python
def test_ngspice_command_requires_fresh_raw_and_log(self):
    with tempfile.TemporaryDirectory() as tmp:
        circuit = Path(tmp) / "case.cir"
        circuit.write_text("* case\n.end\n", encoding="utf-8")
        circuit.with_suffix(".raw").write_text("stale", encoding="utf-8")
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(backends, "detect_simulators", return_value={
            "ltspice": {"found": False, "executable": None},
            "ngspice": {"found": True, "executable": "/usr/bin/ngspice"},
        }), mock.patch.object(backends.subprocess, "run", return_value=completed):
            result = backends.run_portable(circuit, backend="ngspice")
    self.assertFalse(result["ok"])
    self.assertEqual(result["reason"], "waveform_missing")
```

- [ ] **Step 5: Implement normalized LTspice and ngspice execution**

Use commands:

```python
if chosen == "ltspice":
    command = [executable, "-b", str(input_path)]
else:
    command = [executable, "-b", "-o", str(log_path), "-r", str(raw_path), str(input_path)]
```

Before execution, remove only derived siblings for the exact input stem:
`.raw`, `.log`, `.op.raw`, `.net`, and `.db`. Validate `timeout_seconds > 0`,
capture output, and require a newly created nonempty `.raw` file. Preserve the
existing whitespace-safe LTspice staging behavior by extracting or reusing its
logic without changing `server.tool_run_simulation`.

- [ ] **Step 6: Run backend tests and the existing suite**

Run:

```bash
python3 -m unittest tests.test_backends -v
python3 -m unittest discover -s tests -p 'test_*.py'
```

Expected: all tests pass; existing count plus backend tests.

- [ ] **Step 7: Commit**

```bash
git add mcp/backends.py tests/test_backends.py
git commit -m "feat: add portable simulator backends"
```

### Task 2: Waveform Parsing, CSV, SVG, and Metrics

**Files:**
- Create: `mcp/waveforms.py`
- Create: `tests/test_waveforms.py`
- Create: `tests/fixtures/ngspice_rc_wrdata.txt`
- Create: `tests/fixtures/ltspice_rc_ascii.txt`

**Interfaces:**
- Produces: `read_waveform(path, backend) -> {"columns": list[str], "rows": list[list[float]]}`
- Produces: `write_csv(table, path) -> dict`
- Produces: `write_svg(series, path, title, x_label, y_label) -> dict`
- Produces: `rc_metrics(table, vin, resistance, capacitance) -> dict`
- Produces: `buck_metrics(table, vin, duty_cycle, steady_from) -> dict`

- [ ] **Step 1: Add representative parser fixtures**

`tests/fixtures/ngspice_rc_wrdata.txt`:

```text
time v(out) i(v1)
0.000000e+00 0.000000e+00 0.000000e+00
1.000000e-03 6.321206e-01 -3.678794e-04
5.000000e-03 9.932621e-01 -6.737947e-06
```

`tests/fixtures/ltspice_rc_ascii.txt`:

```text
Title: rc
Date: Thu Jul 23 00:00:00 2026
Plotname: Transient Analysis
Flags: real forward
No. Variables: 2
No. Points: 3
Variables:
	0	time	time
	1	V(out)	voltage
Values:
0	0.000000e+00
	0.000000e+00
1	1.000000e-03
	6.321206e-01
2	5.000000e-03
	9.932621e-01
```

- [ ] **Step 2: Write failing parser and validation tests**

```python
def test_parsers_normalize_time_and_signal_names(self):
    ng = waveforms.read_waveform(FIXTURES / "ngspice_rc_wrdata.txt", "ngspice")
    lt = waveforms.read_waveform(FIXTURES / "ltspice_rc_ascii.txt", "ltspice")
    self.assertEqual(ng["columns"][:2], ["time_s", "V(out)"])
    self.assertEqual(lt["columns"], ["time_s", "V(out)"])
    self.assertAlmostEqual(lt["rows"][1][1], 0.6321206)

def test_non_monotonic_time_is_rejected(self):
    table = {"columns": ["time_s", "V(out)"], "rows": [[0, 0], [1, 1], [.5, .8]]}
    with self.assertRaisesRegex(RuntimeError, "strictly increasing"):
        waveforms.validate_table(table)
```

- [ ] **Step 3: Implement strict normalized table parsers**

Implement finite-float validation with `math.isfinite`, require at least two
rows, unique columns, equal row widths, `time_s` first, and strictly increasing
time. The LTspice parser reads `Variables:` and flattened `Values:` blocks; the
ngspice parser accepts whitespace or comma-separated headers and rows.

- [ ] **Step 4: Write failing CSV and SVG tests**

```python
def test_csv_and_svg_are_deterministic(self):
    table = {"columns": ["time_s", "V(out)"], "rows": [[0, 0], [.001, .63], [.005, .99]]}
    with tempfile.TemporaryDirectory() as tmp:
        csv_result = waveforms.write_csv(table, Path(tmp) / "wave.csv")
        svg_result = waveforms.write_svg(
            [{"label": "R=1k", "table": table, "signal": "V(out)"}],
            Path(tmp) / "wave.svg", "RC sweep", "Time (s)", "Voltage (V)",
        )
        self.assertEqual(Path(csv_result["path"]).read_text().splitlines()[0], "time_s,V(out)")
        self.assertIn("<svg", Path(svg_result["path"]).read_text())
        self.assertIn("R=1k", Path(svg_result["path"]).read_text())
```

- [ ] **Step 5: Implement CSV, deterministic extrema-preserving downsampling, and SVG**

Use `csv.writer(..., lineterminator="\n")`. Cap plotted points at 2,000 per
series by retaining first/last and each bucket's min/max signal points. Escape
all labels with `html.escape`. Draw axes, ticks, legend, and polyline paths in a
fixed 1200×720 viewBox.

- [ ] **Step 6: Write failing RC and Buck metric tests**

```python
def test_rc_metrics_find_tau_and_rise_time():
    table = exponential_rc_fixture()
    result = waveforms.rc_metrics(table, vin=1.0, resistance=1000.0, capacitance=1e-6)
    self.assertAlmostEqual(result["theory_tau_s"], .001)
    self.assertLess(result["tau_error_percent"], 1.0)
    self.assertGreater(result["rise_time_10_90_s"], .002)

def test_buck_metrics_use_only_steady_state_window():
    table = buck_fixture_with_startup_and_ripple()
    result = waveforms.buck_metrics(table, vin=12.0, duty_cycle=5 / 12, steady_from=.004)
    self.assertAlmostEqual(result["vout_average_v"], 5.0, places=1)
    self.assertGreater(result["vout_ripple_pp_v"], 0)
    self.assertIn("inductor_current_peak_a", result)
```

- [ ] **Step 7: Implement interpolated crossings and steady-state metrics**

Use linear interpolation for 10%, 63.212%, and 90% crossings. Buck metrics
select rows with `time_s >= steady_from`; require `V(out)` and `I(L1)`; calculate
average/min/max/ripple and ideal conversion error.

- [ ] **Step 8: Run waveform tests and commit**

```bash
python3 -m unittest tests.test_waveforms -v
python3 -m unittest discover -s tests -p 'test_*.py'
git add mcp/waveforms.py tests/test_waveforms.py tests/fixtures
git commit -m "feat: export and analyze waveform data"
```

Expected: all tests pass.

### Task 3: Portable RC Workflow for ngspice and Sweep Reuse

**Files:**
- Create: `mcp/portable.py`
- Create: `tests/test_portable.py`

**Interfaces:**
- Produces: `rc_netlist(resistance, capacitance, vin, stop_time=None, max_step=None) -> str`
- Produces: `run_rc_case(output_dir, parameters, backend, simulator_paths=None) -> dict`
- Consumes: `backends.run_portable`, `waveforms.read_waveform`, `waveforms.write_csv`, `waveforms.rc_metrics`

- [ ] **Step 1: Write failing portable netlist tests**

```python
def test_rc_netlist_is_accepted_by_both_backends():
    text = portable.rc_netlist("1k", "1u", "1")
    self.assertIn("V1 in 0 PULSE(0 1", text)
    self.assertIn("R1 in out 1k", text)
    self.assertIn("C1 out 0 1u", text)
    self.assertIn(".tran", text)
    self.assertIn(".save V(out)", text)
    self.assertTrue(text.rstrip().endswith(".end"))
```

- [ ] **Step 2: Implement portable RC generation using shared SPICE parsing**

Move only generally useful value parsing to `mcp/portable.py` or import the
existing helpers without changing their observable results. Derive stop time as
`6 * R * C` and max step as `tau / 100`.

- [ ] **Step 3: Write a failing mocked end-to-end RC case test**

```python
def test_run_rc_case_returns_csv_and_metrics():
    with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
        backends, "run_portable", return_value={
            "ok": True, "backend": "ngspice", "raw_path": str(FIXTURE), "log_path": None,
        }
    ):
        result = portable.run_rc_case(Path(tmp), {
            "resistance": "1k", "capacitance": "1u", "vin": "1",
        }, "ngspice")
    self.assertTrue(result["ok"])
    self.assertTrue(Path(result["waveform_csv"]).exists())
    self.assertLess(result["metrics"]["tau_error_percent"], 1.0)
```

- [ ] **Step 4: Implement case artifacts and failure propagation**

Write `input.cir`, call the normalized backend, parse only fresh waveform
output, write `waveform.csv` and `metrics.json`, and return `ok=False` without
metrics when simulation or parsing fails.

- [ ] **Step 5: Run all tests and commit**

```bash
python3 -m unittest tests.test_portable -v
python3 -m unittest discover -s tests -p 'test_*.py'
git add mcp/portable.py tests/test_portable.py
git commit -m "feat: add portable rc simulation workflow"
```

### Task 4: Constrained Buck Converter

**Files:**
- Create: `mcp/buck.py`
- Create: `tests/test_buck.py`
- Create: `scripts/buck_smoke_test.py`

**Interfaces:**
- Produces: `validate_parameters(values) -> dict[str, float|str]`
- Produces: `render_netlist(parameters) -> str`
- Produces: `render_schematic(parameters, title) -> list[str]`
- Produces: `create_buck(output_dir, filename, parameters, overwrite=False, simulate=False, backend="auto") -> dict`

- [ ] **Step 1: Write failing default and bounds tests**

```python
def test_defaults_target_twelve_to_five_volts():
    values = buck.validate_parameters({})
    self.assertEqual(values["vin_v"], 12.0)
    self.assertAlmostEqual(values["duty_cycle"], 5 / 12)
    self.assertGreater(values["switching_frequency_hz"], 0)

def test_invalid_duty_is_rejected_before_files_exist():
    with tempfile.TemporaryDirectory() as tmp:
        with self.assertRaisesRegex(RuntimeError, "0 < duty_cycle < 1"):
            buck.create_buck(Path(tmp), "bad", {"duty_cycle": 1.0})
        self.assertEqual(list(Path(tmp).iterdir()), [])
```

- [ ] **Step 2: Implement validated Buck parameter normalization**

Defaults:

```python
DEFAULTS = {
    "vin_v": 12.0,
    "duty_cycle": 5.0 / 12.0,
    "switching_frequency_hz": 100_000.0,
    "inductance_h": 100e-6,
    "capacitance_f": 220e-6,
    "load_resistance_ohm": 5.0,
    "switch_ron_ohm": 0.01,
    "switch_roff_ohm": 1e6,
    "stop_time_s": 0.01,
    "max_step_s": 100e-9,
}
```

Require all positive and `0 < duty_cycle < 1`; require at least 100 time steps
per switching period and at least 200 switching cycles in the default stop
time. Caller overrides that violate sampling bounds fail before writing.

- [ ] **Step 3: Write failing netlist and schematic tests**

```python
def test_buck_generates_portable_netlist_and_visible_schematic():
    values = buck.validate_parameters({})
    netlist = buck.render_netlist(values)
    schematic = "\n".join(buck.render_schematic(values, "Buck converter"))
    self.assertIn("S1 vin sw gate 0 SWMOD", netlist)
    self.assertIn("D1 0 sw DMOD", netlist)
    self.assertIn("L1 sw out", netlist)
    self.assertIn("C1 out 0", netlist)
    self.assertIn("SYMBOL sw", schematic)
    self.assertIn("SYMATTR InstName L1", schematic)
```

- [ ] **Step 4: Implement the bounded asynchronous topology**

Generate:

```text
V1 vin 0 12
VPWM gate 0 PULSE(0 5 0 10n 10n {ton} {period})
S1 vin sw gate 0 SWMOD
D1 0 sw DMOD
L1 sw out 100u
C1 out 0 220u
RLOAD out 0 5
.model SWMOD SW(Ron=.01 Roff=1Meg Vt=2.5 Vh=.1)
.model DMOD D(Is=1n Rs=.01 N=1)
.tran 0 10m 0 100n startup
.save V(out) V(gate) I(L1)
.end
```

Use the correct freewheel diode orientation and include title/limitation
comments. The `.asc` uses visible voltage, switch, diode, inductor, capacitor,
and resistor symbols with named `vin`, `sw`, `out`, and `gate` nets.

- [ ] **Step 5: Write failing mocked analysis/report test**

```python
def test_create_buck_returns_waveform_metrics_plot_and_report():
    with tempfile.TemporaryDirectory() as tmp, fake_successful_buck_run():
        result = buck.create_buck(Path(tmp), "buck", {}, simulate=True, backend="ngspice")
        self.assertEqual(result["circuit_type"], "buck_converter")
        self.assertTrue(result["validation"]["status"] in {"PASS", "FAIL"})
        for key in ("waveform_csv", "plot", "report"):
            self.assertTrue(Path(result[key]["path"]).exists())
```

- [ ] **Step 6: Implement simulation, metrics, validation, SVG, and Markdown report**

The report must include topology, parameters, backend, waveform paths, steady
window, average output, ripple, inductor current, ideal `D*Vin`, conversion
error, PASS/FAIL, warnings/errors, reproduction command, and explicit simplified
model limitations.

Default validation:

```python
checks = {
    "conversion_error_percent_max": 10.0,
    "ripple_percent_max": 5.0,
    "inductor_current_min_a": 0.0,
}
```

- [ ] **Step 7: Add a real LTspice smoke entry point**

`scripts/buck_smoke_test.py` creates `work/buck-smoke/buck-smoke.asc` and
`.cir`, runs LTspice, and exits nonzero unless simulation, waveform parsing,
validation, CSV, SVG, and report all succeed.

- [ ] **Step 8: Run unit tests and commit**

```bash
python3 -m unittest tests.test_buck -v
python3 -m unittest discover -s tests -p 'test_*.py'
git add mcp/buck.py tests/test_buck.py scripts/buck_smoke_test.py
git commit -m "feat: add constrained buck converter"
```

### Task 5: RC and Buck Parameter Sweeps

**Files:**
- Create: `mcp/sweeps.py`
- Create: `tests/test_sweeps.py`
- Create: `scripts/sweep_smoke_test.py`

**Interfaces:**
- Produces: `validate_request(args) -> dict`
- Produces: `run_sweep(args) -> dict`
- Consumes: `portable.run_rc_case`, `buck.create_buck`, `waveforms.write_svg`

- [ ] **Step 1: Write failing whitelist and limit tests**

```python
def test_supported_sweep_matrix_and_limits():
    self.assertEqual(sweeps.validate_request({
        "circuit_type": "rc_lowpass", "parameter": "resistance", "values": ["1k", "2k"],
    })["values"], ["1k", "2k"])
    for parameter in ("inductance", "vin"):
        with self.assertRaisesRegex(RuntimeError, "supported sweep"):
            sweeps.validate_request({
                "circuit_type": "rc_lowpass", "parameter": parameter, "values": ["1", "2"],
            })
    with self.assertRaisesRegex(RuntimeError, "2 through 20"):
        sweeps.validate_request({
            "circuit_type": "buck_converter", "parameter": "duty_cycle", "values": [.4],
        })
```

- [ ] **Step 2: Implement validation and collision-free point IDs**

Use exact matrix:

```python
SUPPORTED = {
    "rc_lowpass": {"resistance", "capacitance"},
    "buck_converter": {"duty_cycle"},
}
```

Reject duplicates after numeric normalization. Point IDs use a zero-padded
index plus sanitized caller value, for example `point-01-1k`.

- [ ] **Step 3: Write failing success and partial-failure tests**

```python
def test_sweep_continues_after_one_failed_point():
    outcomes = [
        {"ok": True, "metrics": {"theory_tau_s": .001}, "waveform_csv": "a.csv"},
        {"ok": False, "reason": "simulation_failed"},
        {"ok": True, "metrics": {"theory_tau_s": .003}, "waveform_csv": "c.csv"},
    ]
    with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
        sweeps, "_run_point", side_effect=outcomes
    ):
        result = sweeps.run_sweep(valid_args(tmp, ["1k", "2k", "3k"]))
    self.assertEqual(result["status"], "FAIL")
    self.assertEqual(len(result["points"]), 3)
    self.assertTrue(Path(result["summary_csv"]).exists())
    self.assertEqual(result["points"][1]["reason"], "simulation_failed")
```

- [ ] **Step 4: Implement isolated orchestration and aggregate artifacts**

Run every point even after failures. Write `sweep_summary.csv` with:

```text
index,parameter,value,status,reason,backend,waveform_csv,<circuit metric columns>
```

Build the overlay SVG from successful point CSVs only. The Markdown report
lists request parameters, every point status, summary metrics, plot, and exact
failure reasons. Overall `PASS` requires every point to pass simulation,
waveform validation, and circuit validation.

- [ ] **Step 5: Add real sweep smoke tests**

`scripts/sweep_smoke_test.py` runs:

- LTspice RC resistance values `["500", "1k", "2k"]`;
- ngspice Buck duty values `[0.35, 5/12, 0.5]` when ngspice is available.

It requires summary CSV, overlay SVG, report, and all point statuses.

- [ ] **Step 6: Run tests and commit**

```bash
python3 -m unittest tests.test_sweeps -v
python3 -m unittest discover -s tests -p 'test_*.py'
git add mcp/sweeps.py tests/test_sweeps.py scripts/sweep_smoke_test.py
git commit -m "feat: add bounded parameter sweeps"
```

### Task 6: MCP Tool Integration and Compatibility

**Files:**
- Modify: `mcp/server.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Produces tools: `detect_simulators`, `create_buck_schematic`, `export_waveform`, `run_parameter_sweep`
- Consumes modules from Tasks 1–5.

- [ ] **Step 1: Write failing tool registration tests**

```python
def test_v060_tools_are_registered_without_removing_old_tools(self):
    expected_old = {
        "detect_ltspice", "create_netlist", "run_simulation",
        "create_rc_schematic", "create_rl_schematic", "create_rlc_schematic",
        "create_schematic_from_description", "open_schematic", "parse_log",
    }
    expected_new = {
        "detect_simulators", "create_buck_schematic",
        "export_waveform", "run_parameter_sweep",
    }
    self.assertTrue(expected_old | expected_new <= set(server.TOOLS))
```

- [ ] **Step 2: Add handlers and exact JSON schemas**

Handler mapping:

```python
def tool_detect_simulators(args):
    return backends.detect_simulators(args.get("ltspice_path"), args.get("ngspice_path"))

def tool_create_buck_schematic(args):
    return buck.create_buck_from_args(args)

def tool_export_waveform(args):
    return waveforms.export_from_args(args)

def tool_run_parameter_sweep(args):
    return sweeps.run_sweep(args)
```

Require `input_path` for export and `circuit_type`, `parameter`, `values` for
sweep. Use enums for backend/circuit/parameter where schemas permit. Do not add
Buck to natural-language classification in v0.6; the explicit Buck tool keeps
the boundary unambiguous.

- [ ] **Step 3: Write handler success/error tests**

Patch each module function and verify JSON-RPC `tools/call` forwards arguments,
serializes result content, and returns `-32000` with the original actionable
message on validation failure.

- [ ] **Step 4: Set server initialization version to `0.6.0`**

Change only the `serverInfo.version`; metadata files are updated in Task 8.

- [ ] **Step 5: Run full regression and commit**

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile mcp/*.py tests/*.py scripts/*.py
git add mcp/server.py tests/test_server.py
git commit -m "feat: expose v0.6 simulation tools"
```

Expected: all tests and compilation pass.

### Task 7: ngspice Linux CI and Real Simulator Verification

**Files:**
- Create: `scripts/ngspice_smoke_test.py`
- Create: `.github/workflows/ci.yml`
- Modify: `.gitignore`

**Interfaces:**
- CI uses only committed source plus Ubuntu `ngspice`.

- [ ] **Step 1: Add ngspice smoke script**

The script detects ngspice, runs one `1k/1u/1V` RC case and one default Buck
case under `work/ngspice-smoke`, and prints a JSON summary. It returns exit code
1 unless both have fresh waveform CSV, metrics, plot/report where applicable,
and PASS validation.

- [ ] **Step 2: Install ngspice locally for cross-backend verification**

If Homebrew is available and ngspice is absent:

```bash
brew install ngspice
ngspice --version
```

Expected: a version banner and exit code 0. If package installation is not
available, continue implementation but do not publish until CI supplies a
passing real ngspice run.

- [ ] **Step 3: Run local real-simulator smoke tests**

```bash
python3 scripts/smoke_test.py
python3 scripts/rl_smoke_test.py
python3 scripts/rlc_smoke_test.py
python3 scripts/buck_smoke_test.py
python3 scripts/ngspice_smoke_test.py
python3 scripts/sweep_smoke_test.py
```

Expected: six success messages, PASS validation, and no simulator errors.

- [ ] **Step 4: Add Linux GitHub Actions workflow**

```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: sudo apt-get update && sudo apt-get install -y ngspice
      - run: python3 -m unittest discover -s tests -p 'test_*.py'
      - run: python3 -m py_compile mcp/*.py scripts/*.py tests/*.py
      - run: python3 scripts/ngspice_smoke_test.py
      - run: git diff --check
      - if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: ngspice-failure-artifacts
          path: work/ngspice-smoke
```

- [ ] **Step 5: Ignore generated simulator work without hiding examples**

Add `/work/` and Python cache patterns if not already present. Do not ignore
`examples/`, `reports/`, or test fixtures.

- [ ] **Step 6: Run YAML sanity checks, tests, and commit**

```bash
python3 -c 'import pathlib; text=pathlib.Path(".github/workflows/ci.yml").read_text(); assert "ngspice" in text and "unittest" in text'
python3 -m unittest discover -s tests -p 'test_*.py'
git diff --check
git add .github/workflows/ci.yml scripts/ngspice_smoke_test.py .gitignore
git commit -m "ci: verify portable ngspice workflows"
```

### Task 8: Documentation, Metadata, Release Gates, Push, and Publication

**Files:**
- Modify: `.codex-plugin/plugin.json`
- Modify: `.mcp.json`
- Modify: `skills/ltspice-automation/SKILL.md`
- Modify: `skills/ltspice-automation/agents/openai.yaml`
- Modify: `README.md`
- Modify: `INSTALL.md`
- Modify: `PROJECT_ROADMAP.md`
- Modify: `CHANGELOG.md`
- Modify: `TEST_REPORT.md`
- Create: `examples/rc-resistance-sweep/README.md`
- Create: `examples/buck-converter/README.md`

**Interfaces:**
- Plugin version: `0.6.0`
- Git tag/release: `v0.6.0`

- [ ] **Step 1: Update plugin and server metadata consistently**

Set `.codex-plugin/plugin.json` version to `0.6.0`, expand descriptions to name
RC/Buck sweeps, CSV/SVG, and ngspice, and add new default prompts. Keep
repository, author, license, and plugin ID unchanged. Update `.mcp.json` only if
required by the final module layout.

- [ ] **Step 2: Update the installed skill boundary**

Document:

- simulator detection before simulation;
- explicit vs auto backend behavior;
- supported sweep matrix and 2–20 limit;
- waveform artifact and metric expectations;
- constrained asynchronous Buck assumptions;
- PASS/FAIL checks and failure handling;
- unchanged arbitrary-circuit non-goal.

- [ ] **Step 3: Update README, install guide, roadmap, changelog, and examples**

Include exact commands for unit tests, LTspice smoke tests, ngspice smoke tests,
and sweeps. Explain Linux `apt-get install ngspice` and macOS installation.
Mark roadmap Buck and controlled sweeps complete in v0.6.0. Examples link to
generated CSV/SVG/report paths but do not commit large `.raw` files.

- [ ] **Step 4: Run the complete local release gate**

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile mcp/*.py scripts/*.py tests/*.py
python3 scripts/smoke_test.py
python3 scripts/rl_smoke_test.py
python3 scripts/rlc_smoke_test.py
python3 scripts/buck_smoke_test.py
python3 scripts/ngspice_smoke_test.py
python3 scripts/sweep_smoke_test.py
python3 /Users/a0000/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py .
python3 /Users/a0000/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/ltspice-automation
git diff --check
```

Expected: every command exits 0; all circuit validations PASS.

- [ ] **Step 5: Record exact release evidence**

Update `TEST_REPORT.md` with date, OS/Python/LTspice/ngspice versions, unit-test
count, all commands, smoke metrics, artifact paths, plugin/skill validation,
and remaining limitations. Do not claim Linux CI until the remote check passes.

- [ ] **Step 6: Commit the v0.6 release candidate**

```bash
git add .codex-plugin/plugin.json .mcp.json skills README.md INSTALL.md PROJECT_ROADMAP.md CHANGELOG.md TEST_REPORT.md examples
git commit -m "release: prepare v0.6.0"
git status --short --branch
```

Expected: clean worktree and local branch ahead of `origin/main`.

- [ ] **Step 7: Re-run the release gate on the exact commit**

Repeat every command from Step 4 and record `git rev-parse HEAD`. Any failure
must be fixed in a new commit and the entire gate repeated.

- [ ] **Step 8: Push the release commit and wait for Linux CI**

```bash
git push origin main
gh run list --workflow ci.yml --branch main --limit 1
gh run watch --exit-status <run-id>
```

Expected: push succeeds and the exact pushed SHA has a successful `ci` run. If
CI fails, inspect logs, fix with TDD, re-run local gates, push, and wait again.

- [ ] **Step 9: Tag and publish only after CI passes**

```bash
git tag -a v0.6.0 -m "LTspice Automation v0.6.0"
git push origin v0.6.0
gh release create v0.6.0 --title "LTspice Automation v0.6.0" --notes-file CHANGELOG.md
```

Expected: tag push succeeds and GitHub returns the published release URL.

- [ ] **Step 10: Verify publication**

```bash
git ls-remote --tags origin refs/tags/v0.6.0
gh release view v0.6.0 --json url,tagName,isDraft,isPrerelease
git status --short --branch
```

Expected: remote tag exists; release is neither draft nor prerelease; worktree
is clean and `main` matches `origin/main`.
