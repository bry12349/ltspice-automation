import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from mcp import backends
    from mcp import waveforms
except ImportError:
    import backends
    import waveforms


def spice_number(value: Any) -> float:
    text = str(value).strip()
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([A-Za-z]*)", text)
    if not match:
        raise RuntimeError(f"invalid SPICE number: {value}")
    multipliers = {
        "": 1.0,
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "k": 1e3,
        "meg": 1e6,
        "g": 1e9,
        "t": 1e12,
    }
    suffix = match.group(2).lower()
    if suffix not in multipliers:
        raise RuntimeError(f"unsupported SPICE suffix in {value}")
    number = float(match.group(1)) * multipliers[suffix]
    if not math.isfinite(number):
        raise RuntimeError(f"SPICE number must be finite: {value}")
    return number


def format_spice(value: float) -> str:
    units = (
        ("n", 1e-9),
        ("u", 1e-6),
        ("m", 1e-3),
        ("", 1.0),
        ("k", 1e3),
        ("Meg", 1e6),
    )
    for suffix, scale in units:
        scaled = value / scale
        if 1 <= abs(scaled) < 1000:
            return f"{scaled:.9g}{suffix}"
    return f"{value:.9g}"


def rc_netlist(
    resistance: Any,
    capacitance: Any,
    vin: Any,
    stop_time: Optional[float] = None,
    max_step: Optional[float] = None,
) -> str:
    r_value = spice_number(resistance)
    c_value = spice_number(capacitance)
    vin_value = spice_number(vin)
    if r_value <= 0:
        raise RuntimeError("resistance must be positive")
    if c_value <= 0:
        raise RuntimeError("capacitance must be positive")
    if vin_value <= 0:
        raise RuntimeError("vin must be positive")

    tau = r_value * c_value
    stop = stop_time if stop_time is not None else 6.0 * tau
    step = max_step if max_step is not None else tau / 100.0
    if stop <= 0 or step <= 0:
        raise RuntimeError("stop_time and max_step must be positive")
    pulse_width = stop * 2.0
    pulse_period = stop * 4.0
    return "\n".join(
        [
            "* Portable RC low-pass transient",
            f"V1 in 0 PULSE(0 {vin} 0 1n 1n {format_spice(pulse_width)} {format_spice(pulse_period)})",
            f"R1 in out {resistance}",
            f"C1 out 0 {capacitance}",
            ".option plotwinsize=0",
            f".tran 0 {format_spice(stop)} 0 {format_spice(step)}",
            ".save V(out)",
            ".end",
            "",
        ]
    )


def run_rc_case(
    output_dir: Path,
    parameters: Dict[str, Any],
    backend: str,
    simulator_paths: Optional[Dict[str, str]] = None,
    timeout_seconds: int = 60,
) -> Dict[str, Any]:
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    resistance = parameters.get("resistance", "1k")
    capacitance = parameters.get("capacitance", "1u")
    vin = parameters.get("vin", "1")
    r_value = spice_number(resistance)
    c_value = spice_number(capacitance)
    vin_value = spice_number(vin)

    netlist_path = destination / "input.cir"
    netlist_path.write_text(
        rc_netlist(resistance, capacitance, vin),
        encoding="utf-8",
    )
    paths = simulator_paths or {}
    simulation = backends.run_portable(
        netlist_path,
        backend=backend,
        timeout_seconds=timeout_seconds,
        ltspice_path=paths.get("ltspice_path"),
        ngspice_path=paths.get("ngspice_path"),
    )
    result: Dict[str, Any] = {
        "ok": bool(simulation.get("ok")),
        "reason": simulation.get("reason", "simulation_failed"),
        "circuit_type": "rc_lowpass",
        "backend": simulation.get("backend", backend),
        "parameters": {
            "resistance": str(resistance),
            "capacitance": str(capacitance),
            "vin": str(vin),
        },
        "netlist_path": str(netlist_path),
        "simulation": simulation,
    }
    if not simulation.get("ok"):
        return result

    table = waveforms.read_waveform(
        Path(simulation["raw_path"]),
        str(simulation["backend"]),
    )
    waveform_csv = destination / "waveform.csv"
    plot_path = destination / "waveform.svg"
    metrics_path = destination / "metrics.json"
    waveforms.write_csv(table, waveform_csv)
    plot = waveforms.write_svg(
        [{"label": f"R={resistance}, C={capacitance}", "table": table, "signal": "V(out)"}],
        plot_path,
        "RC Low-Pass Response",
        "Time (s)",
        "Output voltage (V)",
    )
    metrics = waveforms.rc_metrics(table, vin_value, r_value, c_value)
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result.update(
        {
            "metrics": metrics,
            "metrics_json": str(metrics_path),
            "waveform_csv": str(waveform_csv),
            "plot": plot,
        }
    )
    return result
