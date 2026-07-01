# RL Step Response Template Design

Status: design only. Do not implement code from this document until the user explicitly confirms Phase 7.

## 1. Functional Goal

Add an RL step-response template for simulating a first-order resistor-inductor circuit in LTspice.

The workflow should mirror the current RC low-pass flow:

```text
Natural-language RL request
  -> deterministic template selection
  -> visible LTspice .asc schematic generation
  -> .tran and .meas directive insertion
  -> LTspice batch simulation
  -> .log parsing
  -> theory-vs-simulation comparison
  -> Markdown report generation
```

Initial scope should be narrow:

- one source;
- one resistor;
- one inductor;
- one ground reference;
- transient step response only;
- no arbitrary RL topology synthesis.

The stable user-facing circuit type should be named `rl_step_response`.

## 2. Theory Foundation

For a series RL circuit driven by a voltage step:

```text
tau = L / R
I_final = Vin / R
i(t) = I_final * (1 - exp(-t / tau))
```

Where:

- `tau` is the RL time constant in seconds;
- `L` is inductance in henries;
- `R` is resistance in ohms;
- `Vin` is the final input step voltage;
- `I_final` is the steady-state current.

Physical meaning:

- At `1 tau`, inductor current reaches about `63.2%` of final current.
- At `5 tau`, inductor current reaches about `99.3%` of final current.
- Higher inductance increases `tau` and slows current rise.
- Higher resistance decreases `tau` and lowers final current.

Example:

```text
R = 10 ohm
L = 10 mH
Vin = 5 V
tau = L / R = 0.01 / 10 = 0.001 s = 1 ms
I_final = Vin / R = 5 / 10 = 0.5 A
i(1 tau) = 0.5 * (1 - exp(-1)) = 0.31606 A
i(5 tau) = 0.5 * (1 - exp(-5)) = 0.49663 A
```

## 3. LTspice Circuit Structure

The first implementation should use a simple series RL topology:

```text
Vin source -> R1 -> L1 -> ground
```

Recommended node names:

- `in`: voltage source output node;
- `n1`: resistor-inductor junction;
- `0`: ground.

Visible schematic elements:

- voltage source `V1`;
- resistor `R1`;
- inductor `L1`;
- ground reference;
- wire connections;
- optional node labels;
- `.tran` directive;
- `.meas` directives.

Recommended source:

```text
PULSE(0 {Vin} 0 1u 1u 10m 20m)
```

Recommended default transient stop time:

```text
tstop = 6 * tau
```

If the user supplies `tstop`, use it directly but keep tests for the default computed value.

## 4. Parameter Design

The first template should support:

| Parameter | Meaning | Suggested default | Notes |
| --- | --- | ---: | --- |
| `R` | Series resistance | `10` | Ohms |
| `L` | Series inductance | `10m` | Henries, LTspice suffix format |
| `Vin` | Step final voltage | `5` | Volts |
| `tstop` | Simulation stop time | `6*tau` | Optional override |

Parsing behavior:

- Reuse or extract shared helpers for SPICE suffix parsing.
- Normalize common units such as `mH`, `H`, `ohm`, `Ω`, `V`.
- If parsing fails, fall back to documented defaults and include assumptions in the result/report.

Implementation boundary:

- Do not support parallel RL in the first version.
- Do not support sinusoidal or AC RL analysis in the first version.
- Do not classify arbitrary inductor circuits as RL step-response.

## 5. Measurement Design

Recommended `.meas` directives:

```text
.meas tran i_at_1tau FIND I(L1) AT={tau}
.meas tran i_at_5tau FIND I(L1) AT={5*tau}
.meas tran tau_cross WHEN I(L1)={0.632120558 * I_final} RISE=1
.meas tran final_current FIND I(L1) AT={5*tau}
```

Important LTspice detail:

- Current sign may depend on the inductor symbol orientation.
- The implementation must verify whether `I(L1)` is positive or negative for the chosen schematic orientation.
- If the default orientation produces negative current, either reverse the inductor orientation or measure `-I(L1)` if LTspice accepts that expression reliably in `.meas`.

Recommended result names:

- `i_at_1tau`;
- `i_at_5tau`;
- `tau_cross`;
- `final_current`.

Theory comparison:

| Measurement | Theory |
| --- | --- |
| `i_at_1tau` | `I_final * (1 - exp(-1))` |
| `i_at_5tau` | `I_final * (1 - exp(-5))` |
| `tau_cross` | `tau` |
| `final_current` | approximately `I_final` |

Tolerance recommendation:

- Current measurements: relative error under `1%` for default template.
- Tau crossing: relative error under `1%` for default template.

## 6. Test Plan

### File Generation Test

Add a unit test that generates an RL `.asc` without running LTspice and asserts the file contains:

- `SYMBOL voltage`;
- `SYMBOL res`;
- `SYMBOL ind`;
- `SYMATTR InstName V1`;
- `SYMATTR InstName R1`;
- `SYMATTR InstName L1`;
- `.tran`;
- all required `.meas` directives.

### `.meas` Directive Test

For default `R=10`, `L=10m`, `Vin=5`:

- `tau = 1m`;
- `5*tau = 5m`;
- `I_final = 0.5`;
- `0.632120558 * I_final = 0.316060279`.

Expected directives should include:

```text
.meas tran i_at_1tau FIND I(L1) AT=1m
.meas tran i_at_5tau FIND I(L1) AT=5m
.meas tran tau_cross WHEN I(L1)=0.31606 RISE=1
.meas tran final_current FIND I(L1) AT=5m
```

The exact numeric formatting can follow the RC helper convention, but tests should verify the electrical meaning.

### Simulation Run Test

Add a smoke or regression test that:

1. Generates default RL `.asc`.
2. Runs LTspice batch mode.
3. Parses `.log`.
4. Asserts no parser-detected errors.
5. Confirms required measurements exist.

This test should run only when LTspice is available, or it should be a separate smoke path from pure unit tests.

### Theory-vs-Simulation Error Test

Verify:

```text
i_at_1tau ~= 0.31606 A
i_at_5tau ~= 0.49663 A
tau_cross ~= 0.001 s
final_current ~= 0.5 A
```

Use numeric parsing and tolerance, not substring checks.

### Regression Safety

After RL implementation, always rerun:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 scripts/smoke_test.py
```

RC low-pass must remain passing.

## 7. README Update Plan

When RL is implemented, update `README.md` with:

- RL listed under stable or experimental features depending on test status.
- A new `RL Step Response Example` section.
- RL theory:

  ```text
  tau = L / R
  I_final = Vin / R
  i(t) = I_final * (1 - exp(-t / tau))
  ```

- Example parameters:

  ```text
  R = 10 ohm
  L = 10mH
  Vin = 5V
  tau = 1ms
  I_final = 0.5A
  ```

- Example `.meas` output and theory-vs-simulation table.
- Report path for RL, likely:

  ```text
  reports/rl_step_response_report.md
  ```

- Current limitations:
  - series RL only;
  - transient step response only;
  - no arbitrary inductor circuit synthesis.

## Implementation Notes For The Next Phase

Recommended minimal implementation order:

1. Extract shared SPICE value parsing helpers if needed.
2. Add pure RL theory helper functions.
3. Add RL `.asc` template generation.
4. Add RL `.meas` generation.
5. Add RL report rendering.
6. Add MCP tool/schema exposure.
7. Add unit tests.
8. Add LTspice smoke/regression test.
9. Update README only after tests pass.

Do not implement RL until the user confirms the implementation phase.
