import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List

try:
    from mcp import backends
    from mcp import portable
    from mcp import waveforms
except ImportError:
    import backends
    import portable
    import waveforms


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


ALIASES = {
    "vin_v": ("vin_v", "vin", "input_voltage"),
    "duty_cycle": ("duty_cycle", "duty"),
    "switching_frequency_hz": ("switching_frequency_hz", "switching_frequency", "frequency"),
    "inductance_h": ("inductance_h", "inductance"),
    "capacitance_f": ("capacitance_f", "capacitance"),
    "load_resistance_ohm": ("load_resistance_ohm", "load_resistance", "load"),
    "switch_ron_ohm": ("switch_ron_ohm", "switch_ron"),
    "switch_roff_ohm": ("switch_roff_ohm", "switch_roff"),
    "stop_time_s": ("stop_time_s", "stop_time"),
    "max_step_s": ("max_step_s", "max_step"),
}


def _value(args: Dict[str, Any], canonical: str) -> float:
    raw: Any = DEFAULTS[canonical]
    for alias in ALIASES[canonical]:
        if alias in args and args[alias] is not None:
            raw = args[alias]
            break
    return portable.spice_number(raw)


def validate_parameters(values: Dict[str, Any]) -> Dict[str, float]:
    normalized = {name: _value(values, name) for name in DEFAULTS}
    for name, value in normalized.items():
        if name == "duty_cycle":
            continue
        if not math.isfinite(value) or value <= 0:
            raise RuntimeError(f"{name} must be positive")
    if not 0 < normalized["duty_cycle"] < 1:
        raise RuntimeError("0 < duty_cycle < 1 is required")

    period = 1.0 / normalized["switching_frequency_hz"]
    if normalized["max_step_s"] > period / 100.0 * (1.0 + 1e-12):
        raise RuntimeError("max_step must provide at least 100 points per switching period")
    if normalized["stop_time_s"] < 200.0 * period:
        raise RuntimeError("stop_time must cover at least 200 switching periods")
    normalized["switching_period_s"] = period
    normalized["on_time_s"] = normalized["duty_cycle"] * period
    normalized["steady_from_s"] = normalized["stop_time_s"] * 0.8
    normalized["ideal_vout_v"] = normalized["vin_v"] * normalized["duty_cycle"]
    return normalized


def render_netlist(parameters: Dict[str, float]) -> str:
    p = parameters
    return "\n".join(
        [
            "* Constrained asynchronous Buck converter",
            "* Idealized switch and diode; not a device-loss or control-loop model",
            f"V1 vin 0 {portable.format_spice(p['vin_v'])}",
            (
                "VPWM gate 0 PULSE(0 5 0 10n 10n "
                f"{portable.format_spice(p['on_time_s'])} "
                f"{portable.format_spice(p['switching_period_s'])})"
            ),
            "S1 vin sw gate 0 SWMOD",
            "D1 0 sw DMOD",
            f"L1 sw out {portable.format_spice(p['inductance_h'])}",
            f"C1 out 0 {portable.format_spice(p['capacitance_f'])}",
            f"RLOAD out 0 {portable.format_spice(p['load_resistance_ohm'])}",
            (
                ".model SWMOD SW("
                f"Ron={portable.format_spice(p['switch_ron_ohm'])} "
                f"Roff={portable.format_spice(p['switch_roff_ohm'])} Vt=2.5 Vh=.1)"
            ),
            ".model DMOD D(Is=1n Rs=.01 N=1)",
            ".option plotwinsize=0",
            (
                f".tran {portable.format_spice(p['max_step_s'])} "
                f"{portable.format_spice(p['stop_time_s'])} 0 "
                f"{portable.format_spice(p['max_step_s'])}"
            ),
            ".save V(out) V(gate) I(L1)",
            ".end",
            "",
        ]
    )


def render_schematic(parameters: Dict[str, float], title: str) -> List[str]:
    p = parameters
    return [
        "Version 4",
        "SHEET 1 1000 720",
        "WIRE 256 144 96 144",
        "WIRE 256 224 320 224",
        "WIRE 384 224 496 224",
        "WIRE 96 304 96 224",
        "WIRE 160 304 96 304",
        "WIRE 256 304 160 304",
        "WIRE 432 304 256 304",
        "WIRE 496 304 432 304",
        "WIRE 256 304 256 288",
        "WIRE 432 304 432 288",
        "WIRE 160 336 160 304",
        "WIRE 160 256 208 256",
        "WIRE 208 256 208 208",
        "FLAG 96 304 0",
        "FLAG 96 144 vin",
        "FLAG 256 224 sw",
        "FLAG 384 224 out",
        "FLAG 208 208 gate",
        "FLAG 208 160 0",
        "SYMBOL voltage 96 128 R0",
        "SYMATTR InstName V1",
        f"SYMATTR Value {portable.format_spice(p['vin_v'])}",
        "SYMBOL voltage 160 240 R0",
        "SYMATTR InstName VPWM",
        (
            "SYMATTR Value PULSE(0 5 0 10n 10n "
            f"{portable.format_spice(p['on_time_s'])} "
            f"{portable.format_spice(p['switching_period_s'])})"
        ),
        "SYMBOL sw 256 128 R0",
        "SYMATTR InstName S1",
        "SYMATTR Value SWMOD",
        "SYMBOL diode 272 288 R180",
        "SYMATTR InstName D1",
        "SYMATTR Value DMOD",
        "SYMBOL ind 304 240 R270",
        "SYMATTR InstName L1",
        f"SYMATTR Value {portable.format_spice(p['inductance_h'])}",
        "SYMBOL cap 416 224 R0",
        "SYMATTR InstName C1",
        f"SYMATTR Value {portable.format_spice(p['capacitance_f'])}",
        "SYMBOL res 480 208 R0",
        "SYMATTR InstName RLOAD",
        f"SYMATTR Value {portable.format_spice(p['load_resistance_ohm'])}",
        (
            "TEXT 80 376 Left 2 !.model SWMOD SW("
            f"Ron={portable.format_spice(p['switch_ron_ohm'])} "
            f"Roff={portable.format_spice(p['switch_roff_ohm'])} Vt=2.5 Vh=.1)"
        ),
        "TEXT 80 408 Left 2 !.model DMOD D(Is=1n Rs=.01 N=1)",
        (
            f"TEXT 80 440 Left 2 !.tran 0 {portable.format_spice(p['stop_time_s'])} 0 "
            f"{portable.format_spice(p['max_step_s'])} startup"
        ),
        f"TEXT 80 72 Left 2 ;{title}",
        "TEXT 80 488 Left 2 ;Simplified asynchronous Buck: idealized switch and diode",
    ]


def _validation(metrics: Dict[str, float]) -> Dict[str, Any]:
    checks = [
        {
            "metric": "conversion_error_percent",
            "value": metrics["conversion_error_percent"],
            "limit": 10.0,
            "status": "PASS" if metrics["conversion_error_percent"] <= 10.0 else "FAIL",
        },
        {
            "metric": "vout_ripple_percent",
            "value": metrics["vout_ripple_percent"],
            "limit": 5.0,
            "status": "PASS" if metrics["vout_ripple_percent"] <= 5.0 else "FAIL",
        },
        {
            "metric": "inductor_current_min_a",
            "value": metrics["inductor_current_min_a"],
            "limit": 0.0,
            "status": "PASS" if metrics["inductor_current_min_a"] >= 0.0 else "FAIL",
        },
    ]
    return {
        "status": "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL",
        "checks": checks,
    }


def _render_report(result: Dict[str, Any]) -> str:
    p = result["parameters"]
    m = result["metrics"]
    validation = result["validation"]
    simulation = result["simulation"]
    check_rows = "\n".join(
        f"| `{check['metric']}` | `{check['value']:.6g}` | `{check['limit']:.6g}` | `{check['status']}` |"
        for check in validation["checks"]
    )
    command = " ".join(simulation.get("command") or [])
    return "\n".join(
        [
            "# Buck Converter Simulation Report",
            "",
            "## Topology and Parameters",
            "",
            "- Topology: constrained asynchronous Buck converter",
            f"- Input voltage: `{p['vin_v']:.6g} V`",
            f"- Duty cycle: `{p['duty_cycle']:.6g}`",
            f"- Switching frequency: `{p['switching_frequency_hz']:.6g} Hz`",
            f"- Inductance: `{p['inductance_h']:.6g} H`",
            f"- Capacitance: `{p['capacitance_f']:.6g} F`",
            f"- Load resistance: `{p['load_resistance_ohm']:.6g} ohm`",
            "",
            "## Waveform Artifacts",
            "",
            f"- CSV: `{result['waveform_csv']}`",
            f"- SVG: `{result['plot']['path']}`",
            f"- Metrics JSON: `{result['metrics_json']}`",
            f"- Steady-state window starts at: `{m['steady_from_s']:.6g} s`",
            "",
            "## Key Metrics",
            "",
            f"- Average output voltage: `{m['vout_average_v']:.6g} V`",
            f"- Output ripple: `{m['vout_ripple_pp_v']:.6g} V p-p` (`{m['vout_ripple_percent']:.6g}%`)",
            f"- Inductor current average: `{m['inductor_current_average_a']:.6g} A`",
            f"- Inductor current range: `{m['inductor_current_min_a']:.6g}` to `{m['inductor_current_peak_a']:.6g} A`",
            f"- Ideal D * Vin target: `{m['ideal_vout_v']:.6g} V`",
            f"- Conversion error: `{m['conversion_error_percent']:.6g}%`",
            "",
            "## Validation",
            "",
            f"- Overall result: `{validation['status']}`",
            "",
            "| Metric | Value | Limit | Status |",
            "| --- | ---: | ---: | --- |",
            check_rows,
            "",
            "## Reproduction",
            "",
            f"- Backend: `{simulation.get('backend', 'unknown')}`",
            f"- Command: `{command}`",
            f"- Netlist: `{result['netlist_path']}`",
            f"- Visible schematic: `{result['path']}`",
            "",
            "## Simplified Model Limitations",
            "",
            "- The switch and diode use idealized models.",
            "- Gate-drive loss, parasitics, magnetic saturation, temperature, control-loop dynamics, and PCB effects are omitted.",
            "- The D * Vin comparison is a bounded engineering check, not device-grade converter accuracy.",
            "",
        ]
    )


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned or "buck-converter"


def create_buck(
    output_dir: Path,
    filename: str,
    parameters: Dict[str, Any],
    overwrite: bool = False,
    simulate: bool = False,
    backend: str = "auto",
    timeout_seconds: int = 60,
    ltspice_path: str = None,
    ngspice_path: str = None,
) -> Dict[str, Any]:
    p = validate_parameters(parameters)
    destination = Path(output_dir).expanduser().resolve()
    stem = _safe_filename(filename)
    asc_path = destination / f"{stem}.asc"
    cir_path = destination / f"{stem}.cir"
    for path in (asc_path, cir_path):
        if path.exists() and not overwrite:
            raise RuntimeError(f"Refusing to overwrite existing file: {path}")
    destination.mkdir(parents=True, exist_ok=True)
    asc_path.write_text(
        "\n".join(render_schematic(p, "Constrained asynchronous Buck converter")) + "\n",
        encoding="utf-8",
    )
    cir_path.write_text(render_netlist(p), encoding="utf-8")

    result: Dict[str, Any] = {
        "path": str(asc_path),
        "netlist_path": str(cir_path),
        "circuit_type": "buck_converter",
        "parameters": p,
        "simulation_status": {
            "ok": None,
            "reason": "simulation_not_requested",
        },
    }
    if not simulate:
        return result

    simulation = backends.run_portable(
        cir_path,
        backend=backend,
        timeout_seconds=timeout_seconds,
        ltspice_path=ltspice_path,
        ngspice_path=ngspice_path,
    )
    result["simulation"] = simulation
    result["simulation_status"] = {
        "ok": bool(simulation.get("ok")),
        "reason": simulation.get("reason", "simulation_failed"),
    }
    if not simulation.get("ok"):
        return result

    try:
        table = waveforms.read_waveform(Path(simulation["raw_path"]), simulation["backend"])
        metrics = waveforms.buck_metrics(
            table,
            p["vin_v"],
            p["duty_cycle"],
            p["steady_from_s"],
        )
    except Exception as exc:
        result["simulation_status"] = {
            "ok": False,
            "reason": "waveform_analysis_failed",
            "error": str(exc),
        }
        return result

    waveform_csv = destination / f"{stem}_waveform.csv"
    metrics_json = destination / f"{stem}_metrics.json"
    plot_path = destination / f"{stem}_waveform.svg"
    report_path = destination / f"{stem}_report.md"
    waveforms.write_csv(table, waveform_csv)
    plot = waveforms.write_svg(
        [{"label": f"D={p['duty_cycle']:.4g}", "table": table, "signal": "V(out)"}],
        plot_path,
        "Buck Converter Output",
        "Time (s)",
        "Output voltage (V)",
    )
    validation = _validation(metrics)
    metrics_json.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result.update(
        {
            "waveform_csv": str(waveform_csv),
            "metrics_json": str(metrics_json),
            "plot": plot,
            "metrics": metrics,
            "validation": validation,
        }
    )
    report_path.write_text(_render_report(result), encoding="utf-8")
    result["report"] = {"path": str(report_path)}
    return result


def create_buck_from_args(args: Dict[str, Any]) -> Dict[str, Any]:
    known = {alias for aliases in ALIASES.values() for alias in aliases}
    parameters = {key: value for key, value in args.items() if key in known}
    return create_buck(
        Path(args.get("output_dir") or Path.cwd()),
        str(args.get("filename") or "buck-converter"),
        parameters,
        overwrite=bool(args.get("overwrite", False)),
        simulate=bool(args.get("simulate", True)),
        backend=str(args.get("backend") or "auto"),
        timeout_seconds=int(args.get("timeout_seconds", 60)),
        ltspice_path=args.get("ltspice_path"),
        ngspice_path=args.get("ngspice_path"),
    )
