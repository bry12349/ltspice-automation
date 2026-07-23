# RC Resistance Sweep

This example varies resistance while keeping `C=1uF` and `Vin=1V`.

```json
{
  "circuit_type": "rc_lowpass",
  "parameter": "resistance",
  "values": ["500", "1k", "2k"],
  "parameters": {
    "capacitance": "1u",
    "vin": "1"
  },
  "backend": "ltspice",
  "output_dir": "work/rc-resistance-sweep",
  "overwrite": true
}
```

Expected artifacts:

```text
work/rc-resistance-sweep/
├── point-01-500/
├── point-02-1k/
├── point-03-2k/
├── sweep_summary.csv
├── sweep_plot.svg
└── sweep_report.md
```

As resistance increases, theory tau `R*C` and the measured 63.212% crossing
increase proportionally.
