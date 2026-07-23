# Constrained Buck Converter

This example uses the v0.6 default asynchronous Buck:

```json
{
  "output_dir": "work/buck-example",
  "filename": "buck-example",
  "backend": "ngspice",
  "simulate": true,
  "overwrite": true,
  "vin": 12,
  "duty_cycle": 0.4166666667,
  "switching_frequency": "100k",
  "inductance": "100u",
  "capacitance": "220u",
  "load_resistance": "5"
}
```

Expected artifacts:

```text
work/buck-example/
├── buck-example.asc
├── buck-example.cir
├── buck-example_waveform.csv
├── buck-example_waveform.svg
├── buck-example_metrics.json
└── buck-example_report.md
```

The verified default produces about 4.69 V average output with less than 0.4%
ripple in both LTspice and ngspice. It is an idealized open-loop engineering
model, not a device-loss or control-loop design.
