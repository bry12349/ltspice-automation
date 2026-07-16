#!/usr/bin/env python3
import json
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp import reporting
    from mcp import validation
except ImportError:
    import reporting
    import validation


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _jsonrpc_result(message_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _jsonrpc_error(message_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def _content_text(data: Any) -> Dict[str, Any]:
    if isinstance(data, str):
        text = data
    else:
        text = json.dumps(data, indent=2, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}]}


def _expand_path(value: Optional[str]) -> Optional[Path]:
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _default_ltspice_app() -> Optional[Path]:
    candidates = [
        Path("/Applications/LTspice.app"),
        Path.home() / "Applications/LTspice.app",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _ltspice_executable(ltspice_path: Optional[str] = None) -> Optional[Path]:
    explicit = _expand_path(ltspice_path)
    if explicit:
        if explicit.is_dir() and explicit.suffix == ".app":
            candidate = explicit / "Contents/MacOS/LTspice"
            return candidate if candidate.exists() else None
        return explicit if explicit.exists() else None

    from_path = shutil.which("LTspice")
    if from_path:
        return Path(from_path)

    app = _default_ltspice_app()
    if app:
        candidate = app / "Contents/MacOS/LTspice"
        if candidate.exists():
            return candidate
    return None


def _ltspice_version(app_path: Optional[Path]) -> Optional[str]:
    if not app_path:
        return None
    if app_path.name == "LTspice":
        app_path = app_path.parents[2]
    plist_path = app_path / "Contents/Info.plist"
    if not plist_path.exists():
        return None
    try:
        with plist_path.open("rb") as handle:
            info = plistlib.load(handle)
        return info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")
    except Exception:
        return None


def tool_detect_ltspice(args: Dict[str, Any]) -> Dict[str, Any]:
    exe = _ltspice_executable(args.get("ltspice_path"))
    app = None
    if exe and len(exe.parents) >= 3 and exe.parents[1].name == "Contents":
        app = exe.parents[2]
    return {
        "found": exe is not None,
        "executable": str(exe) if exe else None,
        "app": str(app) if app else None,
        "version": _ltspice_version(app or exe),
        "notes": "Batch mode normally uses the LTspice executable with -b against a .cir/.net/.asc input.",
    }


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", name.strip()).strip("-")
    return cleaned or "ltspice-simulation"


def tool_create_netlist(args: Dict[str, Any]) -> Dict[str, Any]:
    title = str(args.get("title") or "LTspice simulation")
    output_dir = _expand_path(args.get("output_dir")) or Path.cwd()
    filename = _sanitize_filename(str(args.get("filename") or title)) + ".cir"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    if path.exists() and not args.get("overwrite", False):
        raise RuntimeError(f"Refusing to overwrite existing file: {path}")

    raw_lines = args.get("lines")
    if raw_lines:
        lines = [str(line).rstrip() for line in raw_lines]
    else:
        circuit = args.get("circuit") or {}
        kind = str(circuit.get("kind") or "rc_lowpass")
        if kind != "rc_lowpass":
            raise RuntimeError("Only circuit.kind='rc_lowpass' is built in. Pass explicit 'lines' for custom netlists.")
        vin = circuit.get("vin", "AC 1 SIN(0 1 1k)")
        resistance = circuit.get("resistance", "1k")
        capacitance = circuit.get("capacitance", "100n")
        analysis = circuit.get("analysis", ".ac dec 100 10 1Meg")
        lines = [
            f"* {title}",
            f"V1 in 0 {vin}",
            f"R1 in out {resistance}",
            f"C1 out 0 {capacitance}",
            str(analysis),
            ".save V(in) V(out)",
            ".end",
        ]

    if not lines or not lines[-1].strip().lower().startswith(".end"):
        lines.append(".end")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(path), "lines": lines}


def tool_create_rc_schematic(args: Dict[str, Any]) -> Dict[str, Any]:
    title = str(args.get("title") or "RC step response schematic")
    output_dir = _expand_path(args.get("output_dir")) or Path.cwd()
    filename = _sanitize_filename(str(args.get("filename") or title)) + ".asc"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    if path.exists() and not args.get("overwrite", False):
        raise RuntimeError(f"Refusing to overwrite existing file: {path}")

    resistance = str(args.get("resistance") or "1k")
    capacitance = str(args.get("capacitance") or "1u")
    source = str(args.get("source") or "PULSE(0 1 0 1u 1u 10m 20m)")
    analysis = str(args.get("analysis") or _default_rc_analysis(resistance, capacitance))
    measures = args.get("measures") or _default_rc_measures(resistance, capacitance, source)

    # LTspice .asc is a line-oriented schematic format. Coordinates are in LTspice
    # drawing units; this compact layout is intentionally simple and readable.
    lines = [
        "Version 4",
        "SHEET 1 880 680",
        "WIRE 176 112 96 112",
        "WIRE 320 112 240 112",
        "WIRE 320 160 320 112",
        "WIRE 96 224 96 112",
        "WIRE 320 256 320 224",
        "WIRE 320 304 320 256",
        "WIRE 96 304 96 288",
        "WIRE 320 304 96 304",
        "FLAG 96 304 0",
        "FLAG 320 112 out",
        "FLAG 96 112 in",
        "SYMBOL voltage 96 192 R0",
        "SYMATTR InstName V1",
        f"SYMATTR Value {source}",
        "SYMBOL res 160 128 R270",
        "SYMATTR InstName R1",
        f"SYMATTR Value {resistance}",
        "SYMBOL cap 304 160 R0",
        "SYMATTR InstName C1",
        f"SYMATTR Value {capacitance}",
        f"TEXT 80 352 Left 2 !{analysis}",
    ]
    for index, measure in enumerate(measures):
        lines.append(f"TEXT 80 {384 + 32 * index} Left 2 !{measure}")
    lines.append(f"TEXT 80 72 Left 2 ;{title}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(path), "lines": lines}


def tool_create_rl_schematic(args: Dict[str, Any]) -> Dict[str, Any]:
    title = str(args.get("title") or "RL step response schematic")
    output_dir = _expand_path(args.get("output_dir")) or Path.cwd()
    filename = _sanitize_filename(str(args.get("filename") or title)) + ".asc"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    if path.exists() and not args.get("overwrite", False):
        raise RuntimeError(f"Refusing to overwrite existing file: {path}")

    resistance = str(args.get("resistance") or "10")
    inductance = str(args.get("inductance") or "10m")
    source = str(args.get("source") or "PULSE(0 5 0 1u 1u 10m 20m)")
    analysis = str(args.get("analysis") or _default_rl_analysis(resistance, inductance))
    measures = args.get("measures") or _default_rl_measures(resistance, inductance, source)
    lines = _rl_step_asc(title, resistance, inductance, source, analysis, measures)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "path": str(path),
        "lines": lines,
        "circuit_type": "rl_step_response",
        "component_values": {"R1": resistance, "L1": inductance, "V1": source},
        "analysis": analysis,
    }


def tool_create_rlc_schematic(args: Dict[str, Any]) -> Dict[str, Any]:
    title = str(args.get("title") or "RLC series step response schematic")
    output_dir = _expand_path(args.get("output_dir")) or Path.cwd()
    filename = _sanitize_filename(str(args.get("filename") or title)) + ".asc"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    if path.exists() and not args.get("overwrite", False):
        raise RuntimeError(f"Refusing to overwrite existing file: {path}")

    resistance = str(args.get("resistance") or "10")
    inductance = str(args.get("inductance") or "10m")
    capacitance = str(args.get("capacitance") or "10u")
    source = str(args.get("source") or "PULSE(0 5 0 1u 1u 100m 200m)")
    _require_underdamped_rlc(resistance, inductance, capacitance, source)
    analysis = str(args.get("analysis") or _default_rlc_analysis(resistance, inductance, capacitance))
    measures = args.get("measures") or _default_rlc_measures(resistance, inductance, capacitance, source)
    lines = _rlc_series_asc(title, resistance, inductance, capacitance, source, analysis, measures)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {
        "path": str(path),
        "lines": lines,
        "circuit_type": "rlc_series_step",
        "component_values": {"R1": resistance, "L1": inductance, "C1": capacitance, "V1": source},
        "analysis": analysis,
    }


def _parse_value(description: str, names: List[str], default: str) -> str:
    joined = "|".join(re.escape(name) for name in names)
    patterns = [
        rf"(?:{joined})\s*(?:=|为|是|:)?\s*([0-9.]+\s*(?:meg|MEG|[kKmMuUnNpPfF]?)(?:ohm|Ω|欧|F|法|V|伏)?)",
        rf"([0-9.]+\s*(?:meg|MEG|[kKmMuUnNpPfF]?)(?:ohm|Ω|欧|F|法|V|伏)?)\s*(?:的)?(?:{joined})",
    ]
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return _normalize_spice_value(match.group(1))
    return default


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
    suffix = match.group(2)
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
    multiplier = multipliers.get(suffix.lower())
    if multiplier is None:
        return None
    return number * multiplier


def _format_spice_decimal(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _format_spice_time(seconds: float) -> str:
    units = [
        ("n", 1e-9),
        ("u", 1e-6),
        ("m", 1e-3),
        ("", 1.0),
    ]
    for suffix, scale in units:
        scaled = seconds / scale
        if 1 <= abs(scaled) < 1000:
            return f"{_format_spice_decimal(scaled)}{suffix}"
    return _format_spice_decimal(seconds)


def _source_final_voltage(source: str) -> Optional[float]:
    text = source.strip()
    pulse = re.match(r"(?i)^PULSE\s*\(\s*([^\s,)]+)\s+([^\s,)]+)", text)
    if pulse:
        return _spice_number(_normalize_spice_value(pulse.group(2)))
    dc = re.match(r"(?i)^DC\s+([^\s,)]+)", text)
    if dc:
        return _spice_number(_normalize_spice_value(dc.group(1)))
    plain = _spice_number(_normalize_spice_value(text))
    return plain


def _default_rc_measures(resistance: str, capacitance: str, source: str) -> List[str]:
    r_value = _spice_number(_normalize_spice_value(resistance))
    c_value = _spice_number(_normalize_spice_value(capacitance))
    final_voltage = _source_final_voltage(source)
    if r_value is None or c_value is None or final_voltage is None:
        return [
            ".meas tran vout_at_1ms FIND V(out) AT=1m",
            ".meas tran vout_at_5ms FIND V(out) AT=5m",
            ".meas tran tau_cross WHEN V(out)=0.632120558 RISE=1",
        ]

    tau = r_value * c_value
    one_tau = _format_spice_time(tau)
    five_tau = _format_spice_time(5 * tau)
    tau_target = _format_spice_decimal(0.632120558 * final_voltage)
    if one_tau == "1m" and five_tau == "5m":
        first_name = "vout_at_1ms"
        second_name = "vout_at_5ms"
    else:
        first_name = "vout_at_1tau"
        second_name = "vout_at_5tau"
    return [
        f".meas tran {first_name} FIND V(out) AT={one_tau}",
        f".meas tran {second_name} FIND V(out) AT={five_tau}",
        f".meas tran tau_cross WHEN V(out)={tau_target} RISE=1",
    ]


def _default_rc_analysis(resistance: str, capacitance: str) -> str:
    r_value = _spice_number(_normalize_spice_value(resistance))
    c_value = _spice_number(_normalize_spice_value(capacitance))
    if r_value is None or c_value is None:
        return ".tran 0 6m 0 10u"
    return f".tran 0 {_format_spice_time(6 * r_value * c_value)} 0 10u"


def _default_rl_measures(resistance: str, inductance: str, source: str) -> List[str]:
    r_value = _spice_number(_normalize_spice_value(resistance))
    l_value = _spice_number(_normalize_spice_value(inductance))
    final_voltage = _source_final_voltage(source)
    if r_value in (None, 0) or l_value is None or final_voltage is None:
        return [
            ".meas tran i_at_1tau FIND I(L1) AT=1m",
            ".meas tran i_at_5tau FIND I(L1) AT=5m",
            ".meas tran tau_cross WHEN I(L1)=0.31606 RISE=1",
            ".meas tran final_current FIND I(L1) AT=5m",
        ]
    tau = l_value / r_value
    one_tau = _format_spice_time(tau)
    five_tau = _format_spice_time(5 * tau)
    target_current = _format_spice_decimal(0.632120558 * final_voltage / r_value)
    return [
        f".meas tran i_at_1tau FIND I(L1) AT={one_tau}",
        f".meas tran i_at_5tau FIND I(L1) AT={five_tau}",
        f".meas tran tau_cross WHEN I(L1)={target_current} RISE=1",
        f".meas tran final_current FIND I(L1) AT={five_tau}",
    ]


def _default_rl_analysis(resistance: str, inductance: str) -> str:
    r_value = _spice_number(_normalize_spice_value(resistance))
    l_value = _spice_number(_normalize_spice_value(inductance))
    if r_value in (None, 0) or l_value is None:
        return ".tran 0 6m 0 10u"
    return f".tran 0 {_format_spice_time(6 * l_value / r_value)} 0 10u"


def _rlc_parameters(resistance: str, inductance: str, capacitance: str, source: str) -> Optional[Dict[str, float]]:
    r_value = _spice_number(_normalize_spice_value(resistance))
    l_value = _spice_number(_normalize_spice_value(inductance))
    c_value = _spice_number(_normalize_spice_value(capacitance))
    final_voltage = _source_final_voltage(source)
    if r_value in (None, 0) or l_value in (None, 0) or c_value in (None, 0) or final_voltage is None:
        return None
    omega_n = 1 / (l_value * c_value) ** 0.5
    zeta = r_value / 2 * (c_value / l_value) ** 0.5
    settling_time = 4 / (zeta * omega_n) if zeta > 0 else 0.016
    result = {
        "omega_n": omega_n,
        "zeta": zeta,
        "settling_time": settling_time,
        "tstop": 2 * settling_time,
    }
    if zeta < 1:
        omega_d = omega_n * (1 - zeta**2) ** 0.5
        result["omega_d"] = omega_d
        result["peak_time"] = 3.141592653589793 / omega_d
    return result


def _require_underdamped_rlc(resistance: str, inductance: str, capacitance: str, source: str) -> None:
    params = _rlc_parameters(resistance, inductance, capacitance, source)
    if params and params["zeta"] >= 1:
        raise RuntimeError(
            "The RLC series template requires zeta < 1; "
            f"calculated zeta={params['zeta']:.6g}."
        )


def _default_rlc_analysis(resistance: str, inductance: str, capacitance: str) -> str:
    params = _rlc_parameters(resistance, inductance, capacitance, "DC 5")
    if not params:
        return ".tran 0 16m 0 10u"
    return f".tran 0 {_format_spice_time(params['tstop'])} 0 10u"


def _default_rlc_measures(resistance: str, inductance: str, capacitance: str, source: str) -> List[str]:
    params = _rlc_parameters(resistance, inductance, capacitance, source)
    if not params or "peak_time" not in params:
        return [
            ".meas tran vout_at_peak FIND V(out) AT=1m",
            ".meas tran peak_voltage MAX V(out) FROM=0 TO=16m",
            ".meas tran vout_at_settle FIND V(out) AT=8m",
        ]
    peak_time = _format_spice_time(params["peak_time"])
    settle_time = _format_spice_time(params["settling_time"])
    tstop = _format_spice_time(params["tstop"])
    return [
        f".meas tran vout_at_peak FIND V(out) AT={peak_time}",
        f".meas tran peak_voltage MAX V(out) FROM=0 TO={tstop}",
        f".meas tran vout_at_settle FIND V(out) AT={settle_time}",
    ]


def _long_step_source(source: str) -> str:
    final_voltage = _source_final_voltage(source)
    if final_voltage is None:
        return source
    return f"PULSE(0 {_format_spice_decimal(final_voltage)} 0 1u 1u 100m 200m)"


def _safe_asc_comment(text: str) -> str:
    ascii_text = text.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^A-Za-z0-9 _.,:;()\\[\\]/+=*#-]+", "", ascii_text).strip()
    return ascii_text or "Generated LTspice schematic"


def _classify_description(description: str) -> str:
    text = description.lower()
    if re.search(r"\brlc\b", text) or "二阶" in text or "second-order" in text or "second order" in text:
        return "rlc_series_step"
    if re.search(r"\brl\b", text) or "电感" in text or "inductor" in text:
        return "rl_step_response"
    if any(token in text for token in ["高通", "high pass", "high-pass", "highpass"]):
        return "rc_highpass"
    if any(token in text for token in ["分压", "voltage divider", "divider"]):
        return "voltage_divider"
    return "rc_lowpass"


def _source_from_description(description: str, explicit: Optional[str] = None) -> str:
    if explicit:
        return str(explicit)
    text = description.lower()
    amplitude = _parse_value(description, ["幅度", "输入", "电源", "source", "vin", "v1"], "1")
    if amplitude == "1":
        step_amplitude = re.search(r"([0-9.]+\s*(?:meg|MEG|[kKmMuUnNpPfF]?)(?:V|v|伏)?)\s*(?:step|阶跃|pulse|脉冲)", description)
        if step_amplitude:
            amplitude = _normalize_spice_value(step_amplitude.group(1))
    if any(token in text for token in ["阶跃", "step", "pulse", "脉冲"]):
        return f"PULSE(0 {amplitude} 0 1u 1u 10m 20m)"
    if any(token in text for token in ["正弦", "sine", "sin"]):
        return f"SINE(0 {amplitude} 1k)"
    if any(token in text for token in ["交流", "ac", "频响", "频率响应"]):
        return f"AC {amplitude}"
    return f"DC {amplitude}"


def _schematic_common_header() -> List[str]:
    return ["Version 4", "SHEET 1 960 720"]


def _rc_lowpass_asc(title: str, resistance: str, capacitance: str, source: str, analysis: str, measures: List[str]) -> List[str]:
    lines = _schematic_common_header() + [
        "WIRE 176 112 96 112",
        "WIRE 320 112 240 112",
        "WIRE 320 160 320 112",
        "WIRE 96 224 96 112",
        "WIRE 320 256 320 224",
        "WIRE 320 304 320 256",
        "WIRE 96 304 96 288",
        "WIRE 320 304 96 304",
        "FLAG 96 304 0",
        "FLAG 320 112 out",
        "FLAG 96 112 in",
        "SYMBOL voltage 96 192 R0",
        "SYMATTR InstName V1",
        f"SYMATTR Value {source}",
        "SYMBOL res 160 128 R270",
        "SYMATTR InstName R1",
        f"SYMATTR Value {resistance}",
        "SYMBOL cap 304 160 R0",
        "SYMATTR InstName C1",
        f"SYMATTR Value {capacitance}",
        f"TEXT 80 352 Left 2 !{analysis}",
    ]
    return _append_directives(lines, title, measures)


def _rl_step_asc(title: str, resistance: str, inductance: str, source: str, analysis: str, measures: List[str]) -> List[str]:
    lines = _schematic_common_header() + [
        "WIRE 176 112 96 112",
        "WIRE 320 112 240 112",
        "WIRE 464 112 384 112",
        "WIRE 464 224 464 112",
        "WIRE 96 224 96 112",
        "WIRE 464 304 464 224",
        "WIRE 96 304 96 288",
        "WIRE 464 304 96 304",
        "FLAG 96 304 0",
        "FLAG 96 112 in",
        "FLAG 320 112 n1",
        "SYMBOL voltage 96 192 R0",
        "SYMATTR InstName V1",
        f"SYMATTR Value {source}",
        "SYMBOL res 160 128 R270",
        "SYMATTR InstName R1",
        f"SYMATTR Value {resistance}",
        "SYMBOL ind 304 128 R270",
        "SYMATTR InstName L1",
        f"SYMATTR Value {inductance}",
        f"TEXT 80 352 Left 2 !{analysis}",
    ]
    return _append_directives(lines, title, measures)


def _rlc_series_asc(title: str, resistance: str, inductance: str, capacitance: str, source: str, analysis: str, measures: List[str]) -> List[str]:
    lines = _schematic_common_header() + [
        "WIRE 176 112 96 112",
        "WIRE 320 112 240 112",
        "WIRE 464 112 384 112",
        "WIRE 464 160 464 112",
        "WIRE 96 224 96 112",
        "WIRE 464 256 464 224",
        "WIRE 464 304 464 256",
        "WIRE 96 304 96 288",
        "WIRE 464 304 96 304",
        "FLAG 96 304 0",
        "FLAG 96 112 in",
        "FLAG 464 112 out",
        "SYMBOL voltage 96 192 R0",
        "SYMATTR InstName V1",
        f"SYMATTR Value {source}",
        "SYMBOL res 160 128 R270",
        "SYMATTR InstName R1",
        f"SYMATTR Value {resistance}",
        "SYMBOL ind 304 128 R270",
        "SYMATTR InstName L1",
        f"SYMATTR Value {inductance}",
        "SYMBOL cap 448 160 R0",
        "SYMATTR InstName C1",
        f"SYMATTR Value {capacitance}",
        f"TEXT 80 352 Left 2 !{analysis}",
    ]
    return _append_directives(lines, title, measures)


def _rc_highpass_asc(title: str, resistance: str, capacitance: str, source: str, analysis: str, measures: List[str]) -> List[str]:
    lines = _schematic_common_header() + [
        "WIRE 176 112 96 112",
        "WIRE 320 112 240 112",
        "WIRE 320 160 320 112",
        "WIRE 96 224 96 112",
        "WIRE 320 256 320 224",
        "WIRE 320 304 320 256",
        "WIRE 96 304 96 288",
        "WIRE 320 304 96 304",
        "FLAG 96 304 0",
        "FLAG 320 112 out",
        "FLAG 96 112 in",
        "SYMBOL voltage 96 192 R0",
        "SYMATTR InstName V1",
        f"SYMATTR Value {source}",
        "SYMBOL cap 160 128 R270",
        "SYMATTR InstName C1",
        f"SYMATTR Value {capacitance}",
        "SYMBOL res 304 160 R0",
        "SYMATTR InstName R1",
        f"SYMATTR Value {resistance}",
        f"TEXT 80 352 Left 2 !{analysis}",
    ]
    return _append_directives(lines, title, measures)


def _voltage_divider_asc(title: str, r_top: str, r_bottom: str, source: str, analysis: str, measures: List[str]) -> List[str]:
    lines = _schematic_common_header() + [
        "WIRE 176 112 96 112",
        "WIRE 320 112 240 112",
        "WIRE 320 160 320 112",
        "WIRE 96 224 96 112",
        "WIRE 320 256 320 224",
        "WIRE 320 304 320 256",
        "WIRE 96 304 96 288",
        "WIRE 320 304 96 304",
        "FLAG 96 304 0",
        "FLAG 320 112 out",
        "FLAG 96 112 in",
        "SYMBOL voltage 96 192 R0",
        "SYMATTR InstName V1",
        f"SYMATTR Value {source}",
        "SYMBOL res 160 128 R270",
        "SYMATTR InstName R1",
        f"SYMATTR Value {r_top}",
        "SYMBOL res 304 160 R0",
        "SYMATTR InstName R2",
        f"SYMATTR Value {r_bottom}",
        f"TEXT 80 352 Left 2 !{analysis}",
    ]
    return _append_directives(lines, title, measures)


def _append_directives(lines: List[str], title: str, measures: List[str]) -> List[str]:
    for index, measure in enumerate(measures):
        lines.append(f"TEXT 80 {384 + 32 * index} Left 2 !{measure}")
    lines.append(f"TEXT 80 40 Left 2 ;{_safe_asc_comment(title)}")
    return lines


def _write_schematic(output_dir: Path, filename: str, lines: List[str], overwrite: bool) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (_sanitize_filename(filename) + ".asc")
    if path.exists() and not overwrite:
        raise RuntimeError(f"Refusing to overwrite existing file: {path}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _simulation_status(simulation: Optional[Dict[str, Any]], log: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if simulation is None:
        return {"ok": None, "reason": "simulation_not_requested"}
    if simulation.get("returncode") != 0:
        return {"ok": False, "reason": "ltspice_returncode_nonzero"}
    if log is None:
        return {"ok": False, "reason": "log_missing"}
    if log.get("errors"):
        return {"ok": False, "reason": "log_errors"}
    return {"ok": True, "reason": "simulation_passed"}


def _default_report_path(schematic_path: Path) -> Path:
    return schematic_path.with_name(f"{schematic_path.stem}_report.md")


def tool_create_schematic_from_description(args: Dict[str, Any]) -> Dict[str, Any]:
    description = str(args.get("description") or "").strip()
    if not description:
        raise RuntimeError("description is required.")
    output_dir = _expand_path(args.get("output_dir")) or Path.cwd()
    circuit_type = str(args.get("circuit_type") or _classify_description(description))
    title = str(args.get("title") or description[:72])
    filename = str(args.get("filename") or circuit_type)
    overwrite = bool(args.get("overwrite", False))
    source = _source_from_description(description, args.get("source"))
    if not source.upper().startswith(("PULSE", "SINE", "SIN", "AC", "DC")):
        source = f"DC {source}"
    if source.upper().startswith(("SINE", "SIN", "AC")):
        raise RuntimeError(
            "Natural-language generation supports only DC or step transient requests; "
            "use create_netlist for AC or sine analysis."
        )

    if circuit_type in ["rc_lowpass", "rc_highpass"]:
        if circuit_type != "rc_lowpass":
            raise RuntimeError("The natural-language visual schematic generator currently supports rc_lowpass, rl_step_response, and rlc_series_step. Use create_netlist for other circuits until their .asc templates are verified.")
        resistance = str(args.get("resistance") or _parse_value(description, ["电阻", "r", "resistor", "resistance"], "1k"))
        capacitance = str(args.get("capacitance") or _parse_value(description, ["电容", "c", "capacitor", "capacitance"], "1u"))
        analysis = str(args.get("analysis") or _default_rc_analysis(resistance, capacitance))
        measures = args.get("measures") or _default_rc_measures(resistance, capacitance, source)
        lines = _rc_lowpass_asc(title, resistance, capacitance, source, analysis, measures)
        component_values = {"R1": resistance, "C1": capacitance, "V1": source}
    elif circuit_type == "rl_step_response":
        resistance = str(args.get("resistance") or _parse_value(description, ["电阻", "r", "resistor", "resistance"], "10"))
        inductance = str(args.get("inductance") or _parse_value(description, ["电感", "l", "inductor", "inductance"], "10m"))
        analysis = str(args.get("analysis") or _default_rl_analysis(resistance, inductance))
        measures = args.get("measures") or _default_rl_measures(resistance, inductance, source)
        lines = _rl_step_asc(title, resistance, inductance, source, analysis, measures)
        component_values = {"R1": resistance, "L1": inductance, "V1": source}
    elif circuit_type == "rlc_series_step":
        if not args.get("source"):
            source = _long_step_source(source)
        resistance = str(args.get("resistance") or _parse_value(description, ["电阻", "r", "resistor", "resistance"], "10"))
        inductance = str(args.get("inductance") or _parse_value(description, ["电感", "l", "inductor", "inductance"], "10m"))
        capacitance = str(args.get("capacitance") or _parse_value(description, ["电容", "c", "capacitor", "capacitance"], "10u"))
        _require_underdamped_rlc(resistance, inductance, capacitance, source)
        analysis = str(args.get("analysis") or _default_rlc_analysis(resistance, inductance, capacitance))
        measures = args.get("measures") or _default_rlc_measures(resistance, inductance, capacitance, source)
        lines = _rlc_series_asc(title, resistance, inductance, capacitance, source, analysis, measures)
        component_values = {"R1": resistance, "L1": inductance, "C1": capacitance, "V1": source}
    elif circuit_type == "voltage_divider":
        raise RuntimeError("The natural-language visual schematic generator currently supports rc_lowpass, rl_step_response, and rlc_series_step. Use create_netlist for other circuits until their .asc templates are verified.")
    else:
        raise RuntimeError("Unsupported circuit_type. Use rc_lowpass, rl_step_response, or rlc_series_step.")

    path = _write_schematic(output_dir, filename, lines, overwrite)
    result: Dict[str, Any] = {
        "path": str(path),
        "circuit_type": circuit_type,
        "component_values": component_values,
        "analysis": analysis,
        "opened": False,
        "simulation": None,
        "log": None,
        "simulation_status": {"ok": None, "reason": "simulation_not_requested"},
        "validation": None,
        "report": None,
    }
    if args.get("simulate", True):
        result["simulation"] = tool_run_simulation(
            {
                "input_path": str(path),
                "timeout_seconds": args.get("timeout_seconds", 60),
                "ltspice_path": args.get("ltspice_path"),
            }
        )
        log_path = path.with_suffix(".log")
        if log_path.exists():
            result["log"] = tool_parse_log({"log_path": str(log_path)})
        result["simulation_status"] = _simulation_status(result["simulation"], result["log"])
        if circuit_type == "rc_lowpass":
            result["validation"] = validation.validate_result(result, float(args.get("tolerance_percent") or 2.0))
            report_path = _expand_path(args.get("report_path")) or _default_report_path(path)
            result["report"] = reporting.generate_rc_lowpass_report(result, report_path)
        elif circuit_type == "rl_step_response":
            result["validation"] = validation.validate_result(result, float(args.get("tolerance_percent") or 2.0))
            report_path = _expand_path(args.get("report_path")) or _default_report_path(path)
            result["report"] = reporting.generate_rl_step_response_report(result, report_path)
        elif circuit_type == "rlc_series_step":
            result["validation"] = validation.validate_result(result, float(args.get("tolerance_percent") or 3.0))
            report_path = _expand_path(args.get("report_path")) or _default_report_path(path)
            result["report"] = reporting.generate_rlc_series_report(result, report_path)
    if args.get("open", True):
        result["opened"] = tool_open_schematic({"path": str(path), "ltspice_path": args.get("ltspice_path")})
    return result


def tool_open_schematic(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _expand_path(args.get("path"))
    if not path or not path.exists():
        raise RuntimeError("path must point to an existing LTspice schematic file.")
    if sys.platform != "darwin":
        return {
            "command": None,
            "returncode": 1,
            "stdout": "",
            "stderr": "Opening LTspice schematics in the GUI is currently supported only on macOS.",
            "path": str(path),
            "unsupported_platform": True,
        }
    app = _expand_path(args.get("ltspice_path"))
    if app and app.is_file() and app.name == "LTspice":
        app = app.parents[2]
    if not app:
        detected = tool_detect_ltspice({})
        if detected.get("app"):
            app = Path(str(detected["app"]))
    cmd = ["open"]
    if app:
        cmd.extend(["-a", str(app)])
    cmd.append(str(path))
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-1000:],
        "stderr": proc.stderr[-1000:],
        "path": str(path),
    }


def tool_run_simulation(args: Dict[str, Any]) -> Dict[str, Any]:
    exe = _ltspice_executable(args.get("ltspice_path"))
    if not exe:
        raise RuntimeError("LTspice executable not found. Install LTspice.app or pass ltspice_path.")
    input_path = _expand_path(args.get("input_path"))
    if not input_path or not input_path.exists():
        raise RuntimeError("input_path must point to an existing .cir, .net, or .asc file.")
    cwd = _expand_path(args.get("cwd")) or input_path.parent
    timeout = int(args.get("timeout_seconds") or 120)
    cmd = [str(exe), "-b", str(input_path)]
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, timeout=timeout)
    expected = {
        "log": input_path.with_suffix(".log"),
        "raw": input_path.with_suffix(".raw"),
        "op_raw": input_path.with_suffix(".op.raw"),
    }
    return {
        "command": cmd,
        "cwd": str(cwd),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-4000:],
        "stderr": proc.stderr[-4000:],
        "expected_outputs": {name: str(path) for name, path in expected.items() if path.exists()},
    }


def _parse_measurements(text: str) -> Dict[str, str]:
    measurements: Dict[str, str] = {}
    ignored_keys = {
        "circuit",
        "solver",
        "tnom",
        "temp",
        "method",
        "warning",
        "error",
        "fatal",
    }
    for line in text.splitlines():
        lowered = line.strip().lower()
        if not lowered or lowered.startswith(("warning", "error", "fatal error")):
            continue
        meas_match = re.match(r"^\s*([A-Za-z_][\w.]*)\s*:\s*(.+?)\s*$", line)
        if meas_match:
            name = meas_match.group(1)
            if name.lower() not in ignored_keys:
                measurements[name] = meas_match.group(2)
            continue
        match = re.match(r"^\s*([A-Za-z_][\w.]*)\s*[:=]\s*([^\s]+)", line)
        if match:
            name = match.group(1)
            if name.lower() not in ignored_keys:
                measurements[name] = match.group(2)
    return measurements


def tool_parse_log(args: Dict[str, Any]) -> Dict[str, Any]:
    path = _expand_path(args.get("log_path"))
    if not path or not path.exists():
        raise RuntimeError("log_path must point to an existing LTspice .log file.")
    text = path.read_text(errors="replace")
    warnings = [line.strip() for line in text.splitlines() if "warning" in line.lower()]
    error_markers = ["error", "failed", "expected", "unknown", "can't", "cannot", "not found"]
    errors = [line.strip() for line in text.splitlines() if any(marker in line.lower() for marker in error_markers)]
    return {
        "path": str(path),
        "line_count": len(text.splitlines()),
        "warnings": warnings[:50],
        "errors": errors[:50],
        "measurements": _parse_measurements(text),
        "tail": "\n".join(text.splitlines()[-80:]),
    }


TOOLS = {
    "detect_ltspice": {
        "description": "Detect the local LTspice installation and executable path.",
        "inputSchema": {
            "type": "object",
            "properties": {"ltspice_path": {"type": "string"}},
        },
        "handler": tool_detect_ltspice,
    },
    "create_netlist": {
        "description": "Create a SPICE netlist file. Supports explicit netlist lines or a built-in RC low-pass template.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "output_dir": {"type": "string"},
                "filename": {"type": "string"},
                "overwrite": {"type": "boolean"},
                "lines": {"type": "array", "items": {"type": "string"}},
                "circuit": {"type": "object"},
            },
        },
        "handler": tool_create_netlist,
    },
    "run_simulation": {
        "description": "Run LTspice in batch mode against a .cir, .net, or .asc file.",
        "inputSchema": {
            "type": "object",
            "required": ["input_path"],
            "properties": {
                "input_path": {"type": "string"},
                "ltspice_path": {"type": "string"},
                "cwd": {"type": "string"},
                "timeout_seconds": {"type": "integer"},
            },
        },
        "handler": tool_run_simulation,
    },
    "create_rc_schematic": {
        "description": "Create a visible LTspice .asc schematic for an RC step-response circuit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "output_dir": {"type": "string"},
                "filename": {"type": "string"},
                "overwrite": {"type": "boolean"},
                "resistance": {"type": "string"},
                "capacitance": {"type": "string"},
                "source": {"type": "string"},
                "analysis": {"type": "string"},
                "measures": {"type": "array", "items": {"type": "string"}},
            },
        },
        "handler": tool_create_rc_schematic,
    },
    "create_rl_schematic": {
        "description": "Create a visible LTspice .asc schematic for an RL step-response circuit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "output_dir": {"type": "string"},
                "filename": {"type": "string"},
                "overwrite": {"type": "boolean"},
                "resistance": {"type": "string"},
                "inductance": {"type": "string"},
                "source": {"type": "string"},
                "analysis": {"type": "string"},
                "measures": {"type": "array", "items": {"type": "string"}},
            },
        },
        "handler": tool_create_rl_schematic,
    },
    "create_rlc_schematic": {
        "description": "Create a visible LTspice .asc schematic for an underdamped series RLC step-response circuit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "output_dir": {"type": "string"},
                "filename": {"type": "string"},
                "overwrite": {"type": "boolean"},
                "resistance": {"type": "string"},
                "inductance": {"type": "string"},
                "capacitance": {"type": "string"},
                "source": {"type": "string"},
                "analysis": {"type": "string"},
                "measures": {"type": "array", "items": {"type": "string"}},
            },
        },
        "handler": tool_create_rlc_schematic,
    },
    "create_schematic_from_description": {
        "description": "Convert a natural-language circuit request into a visible LTspice .asc schematic, optionally simulate it, and open it in LTspice.",
        "inputSchema": {
            "type": "object",
            "required": ["description"],
            "properties": {
                "description": {"type": "string"},
                "circuit_type": {"type": "string", "enum": ["rc_lowpass", "rl_step_response", "rlc_series_step"]},
                "title": {"type": "string"},
                "output_dir": {"type": "string"},
                "filename": {"type": "string"},
                "overwrite": {"type": "boolean"},
                "open": {"type": "boolean"},
                "simulate": {"type": "boolean"},
                "timeout_seconds": {"type": "integer"},
                "resistance": {"type": "string"},
                "capacitance": {"type": "string"},
                "inductance": {"type": "string"},
                "r_top": {"type": "string"},
                "r_bottom": {"type": "string"},
                "source": {"type": "string"},
                "analysis": {"type": "string"},
                "measures": {"type": "array", "items": {"type": "string"}},
                "ltspice_path": {"type": "string"},
                "report_path": {"type": "string"},
                "tolerance_percent": {"type": "number"},
            },
        },
        "handler": tool_create_schematic_from_description,
    },
    "open_schematic": {
        "description": "Open an existing LTspice .asc schematic in the LTspice GUI so the user can see it.",
        "inputSchema": {
            "type": "object",
            "required": ["path"],
            "properties": {
                "path": {"type": "string"},
                "ltspice_path": {"type": "string"},
            },
        },
        "handler": tool_open_schematic,
    },
    "parse_log": {
        "description": "Parse an LTspice .log file for warnings, errors, measurements, and tail output.",
        "inputSchema": {
            "type": "object",
            "required": ["log_path"],
            "properties": {"log_path": {"type": "string"}},
        },
        "handler": tool_parse_log,
    },
}


def handle_request(request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method = request.get("method")
    message_id = request.get("id")
    try:
        if method == "initialize":
            return _jsonrpc_result(message_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ltspice-automation", "version": "0.4.0"},
            })
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            return _jsonrpc_result(message_id, {
                "tools": [
                    {
                        "name": name,
                        "description": spec["description"],
                        "inputSchema": spec["inputSchema"],
                    }
                    for name, spec in TOOLS.items()
                ]
            })
        if method == "tools/call":
            params = request.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name not in TOOLS:
                return _jsonrpc_error(message_id, -32602, f"Unknown tool: {name}")
            result = TOOLS[name]["handler"](arguments)
            return _jsonrpc_result(message_id, _content_text(result))
        if message_id is not None:
            return _jsonrpc_error(message_id, -32601, f"Unsupported method: {method}")
        return None
    except Exception as exc:
        return _jsonrpc_error(message_id, -32000, str(exc))


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
        except Exception as exc:
            response = _jsonrpc_error(None, -32700, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
