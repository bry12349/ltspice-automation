# RLC Template Design

## Functional Goal

Add a constrained underdamped series RLC step-response template. The tool generates a visible LTspice `.asc` schematic, runs transient simulation, extracts `.meas` results from the `.log`, compares them against second-order theory, and writes a Markdown report.

## Circuit Topology

The first supported RLC topology is series RLC with capacitor voltage as the output:

```text
V1 -> R1 -> L1 -> out
                 |
                 C1
                 |
                 0
```

This topology behaves as a second-order low-pass step response.

## Parameters

- `R`: series resistance.
- `L`: series inductance.
- `C`: shunt capacitance to ground.
- `Vin`: step amplitude.

Default values:

```text
Vin = 5 V
R = 10 ohm
L = 10 mH
C = 10 uF
```

These defaults produce an underdamped response suitable for demonstrating overshoot and ringing.

## Theory

```text
omega_n = 1 / sqrt(L * C)
zeta = R / 2 * sqrt(C / L)
omega_d = omega_n * sqrt(1 - zeta^2)
peak_time = pi / omega_d
overshoot = exp(-zeta * pi / sqrt(1 - zeta^2))
peak_voltage = Vin * (1 + overshoot)
settling_time ~= 4 / (zeta * omega_n)
```

For the default case:

```text
omega_n ~= 3162.28 rad/s
zeta ~= 0.1581
peak_time ~= 1.006 ms
peak_voltage ~= 8.023 V
```

## LTspice Directives

The default generated simulation uses:

```text
.tran 0 16m 0 10u
.meas tran vout_at_peak FIND V(out) AT=1.006115m
.meas tran peak_voltage MAX V(out) FROM=0 TO=16m
.meas tran vout_at_settle FIND V(out) AT=8m
```

The source pulse uses a long high time so the step remains high throughout the transient window:

```text
PULSE(0 5 0 1u 1u 100m 200m)
```

## Validation

Validation compares parsed simulation values against theory:

- `vout_at_peak`: expected capacitor voltage at theoretical peak time.
- `peak_voltage`: expected maximum overshoot voltage.
- `vout_at_settle`: expected capacitor voltage at the settling-time sample.

The default RLC tolerance is `3%`.

## Test Plan

- Unit test schematic generation and `.meas` directives.
- Unit test natural-language RLC classification and report generation.
- Unit test RLC validation.
- Smoke test real LTspice batch simulation through `scripts/rlc_smoke_test.py`.
- Re-run RC and RL smoke tests to confirm no regression.

## Current Limits

- Only underdamped series RLC is claimed.
- Parallel RLC is not supported.
- Overdamped and critically damped formulas are not implemented yet.
- Waveform plotting is not implemented yet.
