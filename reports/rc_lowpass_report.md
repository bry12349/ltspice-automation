# RC Low-Pass Simulation Report

## Circuit Parameters

- Circuit name: RC low-pass step response
- Schematic: `/Users/a0000/plugins/ltspice-automation/work/smoke/smoke-rc-lowpass.asc`
- R1: `1k`
- C1: `1u`
- V1: `PULSE(0 1 0 1u 1u 10m 20m)`
- tau = R * C = 0.001 s
- Final voltage: `1 V`

## Simulation Settings

- Analysis: `.tran 0 6m 0 10u`
- Status: `simulation_passed`

## Measurement Results

- `Circuit`: `/Users/a0000/plugins/ltspice-automation/work/smoke/smoke-rc-lowpass.net`
- `solver`: `Normal`
- `tnom`: `27`
- `temp`: `27`
- `method`: `trap`
- `vout_at_1ms`: `V(out) =0.631937031823 at 0.001`
- `vout_at_5ms`: `V(out) =0.993258907545 at 0.005`
- `tau_cross`: `V(out)=0.632121  AT 0.00100049816386`

## Theory vs Simulation

| Measurement | Theory | Simulation | Error |
| --- | ---: | ---: | ---: |
| `vout_at_1ms` | `0.632121 V` | `0.631937 V` | `0.02903%` |
| `vout_at_5ms` | `0.993262 V` | `0.993259 V` | `0.0003167%` |
| `tau_cross` | `0.001 s` | `0.0010005 s` | `0.04982%` |

## Warning/Error Summary

- Warnings: 0
- Errors: 0

## Engineering Conclusion

Simulation completed without parser-detected errors.

## Follow-Up Improvements

- Add waveform image export when `.raw` parsing or plotting is available.
- Extend report generation to future RL and RLC templates after their theory calculators are added.
- Keep simulator output and theory checks together so generated circuits remain verifiable.
