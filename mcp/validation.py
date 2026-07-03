import math
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def normalize_spice_value(value: str) -> str:
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


def spice_number(value: str) -> Optional[float]:
    match = re.match(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([A-Za-z]*)\s*$", value)
    if not match:
        return None
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
    return float(match.group(1)) * multiplier


def source_final_voltage(source: str) -> Optional[float]:
    text = source.strip()
    pulse = re.match(r"(?i)^PULSE\s*\(\s*([^\s,)]+)\s+([^\s,)]+)", text)
    if pulse:
        return spice_number(normalize_spice_value(pulse.group(2)))
    dc = re.match(r"(?i)^DC\s+([^\s,)]+)", text)
    if dc:
        return spice_number(normalize_spice_value(dc.group(1)))
    return spice_number(normalize_spice_value(text))


def measurement_value(text: str) -> Optional[float]:
    match = re.search(r"=\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))", text)
    if not match:
        return None
    return float(match.group(1))


def measurement_time(text: str) -> Optional[float]:
    match = re.search(r"(?:at|AT)\s+([+-]?(?:\d+(?:\.\d*)?|\.\d+))", text)
    if not match:
        return None
    return float(match.group(1))


def _check(name: str, theory: Optional[float], simulation: Optional[float], unit: str, tolerance_percent: float) -> Dict[str, Any]:
    if simulation is None:
        return {
            "measurement": name,
            "status": "MISSING",
            "theory": theory,
            "simulation": None,
            "absolute_error": None,
            "percent_error": None,
            "unit": unit,
        }
    if theory is None:
        return {
            "measurement": name,
            "status": "UNSUPPORTED",
            "theory": None,
            "simulation": simulation,
            "absolute_error": None,
            "percent_error": None,
            "unit": unit,
        }
    absolute_error = abs(simulation - theory)
    percent_error = None if theory == 0 else absolute_error / abs(theory) * 100
    status = "PASS" if percent_error is not None and percent_error <= tolerance_percent else "FAIL"
    return {
        "measurement": name,
        "status": status,
        "theory": theory,
        "simulation": simulation,
        "absolute_error": absolute_error,
        "percent_error": percent_error,
        "unit": unit,
    }


def _rc_checks(result: Dict[str, Any], tolerance_percent: float) -> List[Dict[str, Any]]:
    values = result.get("component_values") or {}
    r_value = spice_number(normalize_spice_value(str(values.get("R1", ""))))
    c_value = spice_number(normalize_spice_value(str(values.get("C1", ""))))
    vin = source_final_voltage(str(values.get("V1", "")))
    tau = r_value * c_value if r_value is not None and c_value is not None else None
    measurements = ((result.get("log") or {}).get("measurements") or {})
    names = ["vout_at_1ms", "vout_at_1tau", "vout_at_5ms", "vout_at_5tau", "tau_cross"]
    checks: List[Dict[str, Any]] = []
    for name in names:
        raw = measurements.get(name)
        if raw is None and name in {"vout_at_1ms", "vout_at_1tau", "vout_at_5ms", "vout_at_5tau"}:
            continue
        if name == "tau_cross":
            theory = tau
            simulation = measurement_time(raw) if raw else None
            checks.append(_check(name, theory, simulation, "s", tolerance_percent))
        else:
            time_value = measurement_time(raw) if raw else None
            theory = None
            if tau and vin is not None and time_value is not None:
                theory = vin * (1 - math.exp(-time_value / tau))
            checks.append(_check(name, theory, measurement_value(raw) if raw else None, "V", tolerance_percent))
    return checks


def _rl_checks(result: Dict[str, Any], tolerance_percent: float) -> List[Dict[str, Any]]:
    values = result.get("component_values") or {}
    r_value = spice_number(normalize_spice_value(str(values.get("R1", ""))))
    l_value = spice_number(normalize_spice_value(str(values.get("L1", ""))))
    vin = source_final_voltage(str(values.get("V1", "")))
    tau = l_value / r_value if l_value is not None and r_value not in (None, 0) else None
    final_current = vin / r_value if vin is not None and r_value not in (None, 0) else None
    measurements = ((result.get("log") or {}).get("measurements") or {})
    targets = {
        "i_at_1tau": (final_current * (1 - math.exp(-1)) if final_current is not None else None, "A", measurement_value),
        "i_at_5tau": (final_current * (1 - math.exp(-5)) if final_current is not None else None, "A", measurement_value),
        "tau_cross": (tau, "s", measurement_time),
        "final_current": (final_current, "A", measurement_value),
    }
    checks = []
    for name, (theory, unit, extractor) in targets.items():
        raw = measurements.get(name)
        checks.append(_check(name, theory, extractor(raw) if raw else None, unit, tolerance_percent))
    return checks


def validate_result(result: Dict[str, Any], tolerance_percent: float = 2.0) -> Dict[str, Any]:
    circuit_type = result.get("circuit_type")
    if circuit_type == "rc_lowpass":
        checks = _rc_checks(result, tolerance_percent)
    elif circuit_type == "rl_step_response":
        checks = _rl_checks(result, tolerance_percent)
    else:
        checks = []

    failing = [check for check in checks if check["status"] != "PASS"]
    error_values = [check["percent_error"] for check in checks if check.get("percent_error") is not None]
    passed = bool(checks) and not failing
    return {
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "tolerance_percent": tolerance_percent,
        "max_error_percent": max(error_values) if error_values else None,
        "checks": checks,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
