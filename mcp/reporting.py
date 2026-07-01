import math
import re
from pathlib import Path
from typing import Any, Dict, Optional


def _normalize_spice_value(value: str) -> str:
    cleaned = value.strip().replace(" ", "")
    cleaned = re.sub(r"(?i)([0-9.]+)M(?:Ω|ohm|欧姆|欧)$", r"\1Meg", cleaned)
    replacements = {
        "Ω": "",
        "欧姆": "",
        "欧": "",
        "ohm": "",
        "Ohm": "",
        "法拉": "",
        "法": "",
        "V": "",
        "v": "",
        "伏特": "",
        "伏": "",
        "Henry": "",
        "henry": "",
        "H": "",
        "h": "",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    cleaned = cleaned.replace("K", "k")
    cleaned = re.sub(r"(?i)([0-9.]+)meg$", r"\1Meg", cleaned)
    cleaned = re.sub(r"(?i)uf$", "u", cleaned)
    cleaned = re.sub(r"(?i)nf$", "n", cleaned)
    cleaned = re.sub(r"(?i)pf$", "p", cleaned)
    return cleaned


def _spice_number(value: str) -> Optional[float]:
    match = re.match(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([A-Za-z]*)\s*$", value)
    if not match:
        return None
    number = float(match.group(1))
    suffix = match.group(2).lower()
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
    multiplier = multipliers.get(suffix)
    if multiplier is None:
        return None
    return number * multiplier


def _source_final_voltage(source: str) -> Optional[float]:
    text = source.strip()
    pulse = re.match(r"(?i)^PULSE\s*\(\s*([^\s,)]+)\s+([^\s,)]+)", text)
    if pulse:
        return _spice_number(_normalize_spice_value(pulse.group(2)))
    dc = re.match(r"(?i)^DC\s+([^\s,)]+)", text)
    if dc:
        return _spice_number(_normalize_spice_value(dc.group(1)))
    return _spice_number(_normalize_spice_value(text))


def _measurement_value(text: str) -> Optional[float]:
    match = re.search(r"=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", text)
    if not match:
        return None
    return float(match.group(1))


def _measurement_time(text: str) -> Optional[float]:
    match = re.search(r"(?:at|AT)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))", text)
    if not match:
        return None
    return float(match.group(1))


def _fmt(value: Optional[float], unit: str = "") -> str:
    if value is None:
        return "n/a"
    suffix = f" {unit}" if unit else ""
    return f"{value:.6g}{suffix}"


def _percent_error(theory: Optional[float], simulation: Optional[float]) -> str:
    if theory is None or simulation is None:
        return "n/a"
    denominator = abs(theory)
    if denominator == 0:
        return "n/a"
    return f"{abs(simulation - theory) / denominator * 100:.4g}%"


def _theory_rows(result: Dict[str, Any], tau: Optional[float], vin: Optional[float]) -> str:
    measurements = ((result.get("log") or {}).get("measurements") or {})
    rows = ["| Measurement | Theory | Simulation | Error |", "| --- | ---: | ---: | ---: |"]
    for name, raw in measurements.items():
        if not name.startswith("vout_at_") and name != "tau_cross":
            continue
        sim_value = _measurement_time(raw) if name == "tau_cross" else _measurement_value(raw)
        if name == "tau_cross":
            theory = tau
            unit = "s"
        else:
            time_value = _measurement_time(raw)
            theory = None
            if tau and vin is not None and time_value is not None:
                theory = vin * (1 - math.exp(-time_value / tau))
            unit = "V"
        rows.append(
            f"| `{name}` | `{_fmt(theory, unit)}` | `{_fmt(sim_value, unit)}` | `{_percent_error(theory, sim_value)}` |"
        )
    if len(rows) == 2:
        rows.append("| n/a | n/a | n/a | n/a |")
    return "\n".join(rows)


def _warning_error_summary(log: Optional[Dict[str, Any]]) -> str:
    if not log:
        return "- Log was not available."
    warnings = log.get("warnings") or []
    errors = log.get("errors") or []
    lines = [f"- Warnings: {len(warnings)}", f"- Errors: {len(errors)}"]
    for warning in warnings[:5]:
        lines.append(f"- Warning detail: `{warning}`")
    for error in errors[:5]:
        lines.append(f"- Error detail: `{error}`")
    return "\n".join(lines)


def render_rc_lowpass_report(result: Dict[str, Any]) -> str:
    component_values = result.get("component_values") or {}
    resistance = str(component_values.get("R1", "n/a"))
    capacitance = str(component_values.get("C1", "n/a"))
    source = str(component_values.get("V1", "n/a"))
    r_value = _spice_number(_normalize_spice_value(resistance))
    c_value = _spice_number(_normalize_spice_value(capacitance))
    vin = _source_final_voltage(source)
    tau = r_value * c_value if r_value is not None and c_value is not None else None
    log = result.get("log")
    status = result.get("simulation_status") or {}

    conclusion = "Simulation completed without parser-detected errors."
    if status.get("ok") is False:
        conclusion = f"Simulation needs review: {status.get('reason', 'unknown_reason')}."
    elif status.get("ok") is None:
        conclusion = "Simulation was not run, so measurements are not validated."

    return "\n".join(
        [
            "# RC Low-Pass Simulation Report",
            "",
            "## Circuit Parameters",
            "",
            f"- Circuit name: RC low-pass step response",
            f"- Schematic: `{result.get('path', 'n/a')}`",
            f"- R1: `{resistance}`",
            f"- C1: `{capacitance}`",
            f"- V1: `{source}`",
            f"- tau = R * C = {_fmt(tau, 's')}",
            f"- Final voltage: `{_fmt(vin, 'V')}`",
            "",
            "## Simulation Settings",
            "",
            f"- Analysis: `{result.get('analysis', 'n/a')}`",
            f"- Status: `{status.get('reason', 'unknown')}`",
            "",
            "## Measurement Results",
            "",
            "\n".join(f"- `{name}`: `{value}`" for name, value in ((log or {}).get("measurements") or {}).items())
            or "- No measurements were parsed.",
            "",
            "## Theory vs Simulation",
            "",
            _theory_rows(result, tau, vin),
            "",
            "## Warning/Error Summary",
            "",
            _warning_error_summary(log),
            "",
            "## Engineering Conclusion",
            "",
            conclusion,
            "",
            "## Follow-Up Improvements",
            "",
            "- Add waveform image export when `.raw` parsing or plotting is available.",
            "- Extend report generation to future RL and RLC templates after their theory calculators are added.",
            "- Keep simulator output and theory checks together so generated circuits remain verifiable.",
            "",
        ]
    )


def generate_rc_lowpass_report(result: Dict[str, Any], report_path: Path) -> Dict[str, str]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_rc_lowpass_report(result), encoding="utf-8")
    return {"path": str(report_path)}


def _rl_theory_rows(result: Dict[str, Any], tau: Optional[float], final_current: Optional[float]) -> str:
    measurements = ((result.get("log") or {}).get("measurements") or {})
    rows = ["| Measurement | Theory | Simulation | Error |", "| --- | ---: | ---: | ---: |"]
    for name, raw in measurements.items():
        if name not in {"i_at_1tau", "i_at_5tau", "tau_cross", "final_current"}:
            continue
        sim_value = _measurement_time(raw) if name == "tau_cross" else _measurement_value(raw)
        unit = "s" if name == "tau_cross" else "A"
        theory = None
        if name == "tau_cross":
            theory = tau
        elif name == "i_at_1tau" and final_current is not None:
            theory = final_current * (1 - math.exp(-1))
        elif name == "i_at_5tau" and final_current is not None:
            theory = final_current * (1 - math.exp(-5))
        elif name == "final_current":
            theory = final_current
        rows.append(
            f"| `{name}` | `{_fmt(theory, unit)}` | `{_fmt(sim_value, unit)}` | `{_percent_error(theory, sim_value)}` |"
        )
    if len(rows) == 2:
        rows.append("| n/a | n/a | n/a | n/a |")
    return "\n".join(rows)


def render_rl_step_response_report(result: Dict[str, Any]) -> str:
    component_values = result.get("component_values") or {}
    resistance = str(component_values.get("R1", "n/a"))
    inductance = str(component_values.get("L1", "n/a"))
    source = str(component_values.get("V1", "n/a"))
    r_value = _spice_number(_normalize_spice_value(resistance))
    l_value = _spice_number(_normalize_spice_value(inductance))
    vin = _source_final_voltage(source)
    tau = l_value / r_value if l_value is not None and r_value not in (None, 0) else None
    final_current = vin / r_value if vin is not None and r_value not in (None, 0) else None
    log = result.get("log")
    status = result.get("simulation_status") or {}

    conclusion = "Simulation completed without parser-detected errors."
    if status.get("ok") is False:
        conclusion = f"Simulation needs review: {status.get('reason', 'unknown_reason')}."
    elif status.get("ok") is None:
        conclusion = "Simulation was not run, so measurements are not validated."

    return "\n".join(
        [
            "# RL Step Response Simulation Report",
            "",
            "## Circuit Parameters",
            "",
            "- Circuit name: RL step response",
            f"- Schematic: `{result.get('path', 'n/a')}`",
            f"- R1: `{resistance}`",
            f"- L1: `{inductance}`",
            f"- V1: `{source}`",
            f"- tau = L / R = {_fmt(tau, 's')}",
            f"- Final current: `{_fmt(final_current, 'A')}`",
            "",
            "## Simulation Settings",
            "",
            f"- Analysis: `{result.get('analysis', 'n/a')}`",
            f"- Status: `{status.get('reason', 'unknown')}`",
            "",
            "## Measurement Results",
            "",
            "\n".join(f"- `{name}`: `{value}`" for name, value in ((log or {}).get("measurements") or {}).items())
            or "- No measurements were parsed.",
            "",
            "## Theory vs Simulation",
            "",
            _rl_theory_rows(result, tau, final_current),
            "",
            "## Warning/Error Summary",
            "",
            _warning_error_summary(log),
            "",
            "## Engineering Conclusion",
            "",
            conclusion,
            "",
            "## Follow-Up Improvements",
            "",
            "- Verify inductor-current sign whenever the schematic orientation changes.",
            "- Extend first-order reporting helpers so RC and RL share more formatting code.",
            "- Add RLC second-order response after RL behavior is stable.",
            "",
        ]
    )


def generate_rl_step_response_report(result: Dict[str, Any], report_path: Path) -> Dict[str, str]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_rl_step_response_report(result), encoding="utf-8")
    return {"path": str(report_path)}
