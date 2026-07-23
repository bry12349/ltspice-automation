import csv
import html
import json
import math
import re
import struct
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


Table = Dict[str, Any]


def _normalize_column(name: str) -> str:
    cleaned = name.strip()
    if cleaned.lower() in {"time", "time_s"}:
        return "time_s"
    if re.match(r"(?i)^v\(.+\)$", cleaned):
        return "V" + cleaned[1:]
    if re.match(r"(?i)^i\(.+\)$", cleaned):
        return "I" + cleaned[1:]
    return cleaned


def validate_table(table: Table) -> Table:
    columns = list(table.get("columns") or [])
    rows = list(table.get("rows") or [])
    if len(columns) < 2 or columns[0] != "time_s":
        raise RuntimeError("waveform must start with time_s and contain at least one signal")
    if len(set(columns)) != len(columns):
        raise RuntimeError("waveform columns must be unique")
    if len(rows) < 2:
        raise RuntimeError("waveform must contain at least two rows")

    previous_time: Optional[float] = None
    normalized_rows: List[List[float]] = []
    for row in rows:
        if len(row) != len(columns):
            raise RuntimeError("waveform rows must match the column count")
        values = [float(value) for value in row]
        if not all(math.isfinite(value) for value in values):
            raise RuntimeError("waveform values must be finite")
        if previous_time is not None and values[0] <= previous_time:
            raise RuntimeError("waveform time values must be strictly increasing")
        previous_time = values[0]
        normalized_rows.append(values)
    return {"columns": columns, "rows": normalized_rows}


def _parse_spice_ascii(text: str) -> Table:
    lines = text.splitlines()
    try:
        variables_index = next(index for index, line in enumerate(lines) if line.strip() == "Variables:")
        values_index = next(index for index, line in enumerate(lines) if line.strip() == "Values:")
    except StopIteration as exc:
        raise RuntimeError("ASCII RAW file is missing Variables or Values sections") from exc

    columns = []
    for line in lines[variables_index + 1 : values_index]:
        match = re.match(r"^\s*\d+\s+(\S+)", line)
        if match:
            columns.append(_normalize_column(match.group(1)))
    if not columns:
        raise RuntimeError("ASCII RAW file contains no variables")

    rows: List[List[float]] = []
    index = values_index + 1
    while index < len(lines):
        line = lines[index]
        point = re.match(r"^\s*(\d+)\s+(.+?)\s*$", line)
        if not point:
            index += 1
            continue
        values = []
        first_tokens = point.group(2).split()
        for token in first_tokens:
            try:
                values.append(float(token.rstrip(",")))
            except ValueError:
                break
        index += 1
        while len(values) < len(columns) and index < len(lines):
            continuation = lines[index].strip()
            if re.match(r"^\d+\s+", continuation):
                break
            for token in continuation.replace(",", " ").split():
                try:
                    values.append(float(token))
                except ValueError:
                    pass
            index += 1
        if len(values) != len(columns):
            raise RuntimeError(
                f"ASCII RAW point {point.group(1)} has {len(values)} values; expected {len(columns)}"
            )
        rows.append(values)
    return validate_table({"columns": columns, "rows": rows})


def _parse_tabular(text: str) -> Table:
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(("*", "#"))]
    if len(lines) < 3:
        raise RuntimeError("tabular waveform must include a header and at least two rows")
    comma_delimited = "," in lines[0]
    split = (lambda line: [part.strip() for part in line.split(",")]) if comma_delimited else (lambda line: line.split())
    columns = [_normalize_column(name) for name in split(lines[0])]
    rows = []
    for line in lines[1:]:
        tokens = split(line)
        try:
            rows.append([float(token) for token in tokens])
        except ValueError as exc:
            raise RuntimeError(f"invalid numeric waveform row: {line}") from exc
    return validate_table({"columns": columns, "rows": rows})


def _parse_ltspice_binary(data: bytes) -> Table:
    utf16_marker = "Binary:".encode("utf-16le")
    marker_index = data.find(utf16_marker)
    if marker_index < 0:
        raise RuntimeError("LTspice binary RAW header is missing Binary section")
    newline_index = data.find(b"\n\x00", marker_index)
    if newline_index < 0:
        raise RuntimeError("LTspice binary RAW header is truncated")
    payload_offset = newline_index + 2
    header = data[:payload_offset].decode("utf-16le")
    variables_match = re.search(r"(?m)^No\. Variables:\s*(\d+)\s*$", header)
    points_match = re.search(r"(?m)^No\. Points:\s*(\d+)\s*$", header)
    flags_match = re.search(r"(?m)^Flags:\s*(.+?)\s*$", header)
    variables_section = header.split("Variables:\n", 1)
    if not variables_match or not points_match or len(variables_section) != 2:
        raise RuntimeError("LTspice binary RAW header is missing dimensions or variables")
    variable_count = int(variables_match.group(1))
    point_count = int(points_match.group(1))
    columns = []
    for line in variables_section[1].splitlines():
        match = re.match(r"^\s*\d+\s+(\S+)", line)
        if match:
            columns.append(_normalize_column(match.group(1)))
    if len(columns) != variable_count:
        raise RuntimeError(
            f"LTspice binary RAW declares {variable_count} variables but lists {len(columns)}"
        )

    payload = data[payload_offset:]
    all_double = flags_match is not None and "double" in flags_match.group(1).lower().split()
    bytes_per_point = 8 * variable_count if all_double else 8 + 4 * (variable_count - 1)
    expected_bytes = point_count * bytes_per_point
    if len(payload) < expected_bytes:
        raise RuntimeError(
            f"LTspice binary RAW payload has {len(payload)} bytes; expected {expected_bytes}"
        )
    rows = []
    offset = 0
    for _ in range(point_count):
        time_s = struct.unpack_from("<d", payload, offset)[0]
        offset += 8
        if all_double:
            signals = list(struct.unpack_from(f"<{variable_count - 1}d", payload, offset))
            offset += 8 * (variable_count - 1)
        else:
            signals = list(struct.unpack_from(f"<{variable_count - 1}f", payload, offset))
            offset += 4 * (variable_count - 1)
        rows.append([time_s, *signals])
    return validate_table({"columns": columns, "rows": rows})


def read_waveform(path: Path, backend: str) -> Table:
    waveform_path = Path(path).expanduser().resolve()
    if not waveform_path.exists() or not waveform_path.is_file():
        raise RuntimeError("waveform path must point to an existing file")
    data = waveform_path.read_bytes()
    if backend == "ltspice" and "Binary:".encode("utf-16le") in data:
        return _parse_ltspice_binary(data)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            f"{backend} waveform is binary; configure the simulator for ASCII waveform output"
        ) from exc
    if re.search(r"(?m)^Variables:\s*$", text) and re.search(r"(?m)^Values:\s*$", text):
        return _parse_spice_ascii(text)
    return _parse_tabular(text)


def read_csv(path: Path) -> Table:
    csv_path = Path(path).expanduser().resolve()
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            columns = [_normalize_column(name) for name in next(reader)]
        except StopIteration as exc:
            raise RuntimeError("waveform CSV is empty") from exc
        rows = [[float(value) for value in row] for row in reader if row]
    return validate_table({"columns": columns, "rows": rows})


def write_csv(table: Table, path: Path) -> Dict[str, Any]:
    normalized = validate_table(table)
    output_path = Path(path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(normalized["columns"])
        for row in normalized["rows"]:
            writer.writerow([format(value, ".15g") for value in row])
    return {
        "path": str(output_path),
        "columns": normalized["columns"],
        "row_count": len(normalized["rows"]),
    }


def _column_index(table: Table, name: str) -> int:
    target = name.casefold()
    for index, column in enumerate(table["columns"]):
        if column.casefold() == target:
            return index
    raise RuntimeError(f"waveform is missing required signal {name}")


def downsample(table: Table, signal: str, max_points: int = 2000) -> Table:
    normalized = validate_table(table)
    if max_points < 4:
        raise RuntimeError("max_points must be at least 4")
    rows = normalized["rows"]
    if len(rows) <= max_points:
        return {"columns": list(normalized["columns"]), "rows": [list(row) for row in rows]}

    signal_index = _column_index(normalized, signal)
    bucket_count = max(1, (max_points - 2) // 2)
    interior = rows[1:-1]
    selected = [rows[0]]
    for bucket in range(bucket_count):
        start = bucket * len(interior) // bucket_count
        end = (bucket + 1) * len(interior) // bucket_count
        chunk = interior[start:end]
        if not chunk:
            continue
        low = min(chunk, key=lambda row: row[signal_index])
        high = max(chunk, key=lambda row: row[signal_index])
        selected.extend(sorted({tuple(low), tuple(high)}, key=lambda row: row[0]))
    selected.append(rows[-1])
    selected = [list(row) for row in sorted({tuple(row) for row in selected}, key=lambda row: row[0])]
    if len(selected) > max_points:
        selected = selected[: max_points - 1] + [rows[-1]]
    return {"columns": list(normalized["columns"]), "rows": selected}


def write_svg(
    series: Iterable[Dict[str, Any]],
    path: Path,
    title: str,
    x_label: str,
    y_label: str,
) -> Dict[str, Any]:
    prepared = []
    for item in series:
        table = downsample(item["table"], item["signal"])
        signal_index = _column_index(table, item["signal"])
        prepared.append(
            {
                "label": str(item["label"]),
                "rows": table["rows"],
                "signal_index": signal_index,
            }
        )
    if not prepared:
        raise RuntimeError("at least one waveform series is required")

    all_x = [row[0] for item in prepared for row in item["rows"]]
    all_y = [row[item["signal_index"]] for item in prepared for row in item["rows"]]
    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = min(all_y), max(all_y)
    if x_min == x_max:
        x_max = x_min + 1.0
    if y_min == y_max:
        padding = max(1.0, abs(y_min) * 0.05)
        y_min -= padding
        y_max += padding

    width, height = 1200, 720
    left, right, top, bottom = 90, 40, 70, 80
    plot_width = width - left - right
    plot_height = height - top - bottom

    def sx(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_width

    def sy(value: float) -> float:
        return top + (y_max - value) / (y_max - y_min) * plot_height

    colors = ["#2563eb", "#dc2626", "#059669", "#7c3aed", "#ea580c", "#0891b2", "#4f46e5", "#be123c"]
    lines = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 720" role="img">',
        '<rect width="1200" height="720" fill="#ffffff"/>',
        f'<text x="600" y="36" text-anchor="middle" font-family="sans-serif" font-size="24">{html.escape(title)}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" stroke="#111827"/>',
        f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#111827"/>',
    ]
    for tick in range(6):
        fraction = tick / 5
        x_value = x_min + fraction * (x_max - x_min)
        y_value = y_min + fraction * (y_max - y_min)
        x = left + fraction * plot_width
        y = height - bottom - fraction * plot_height
        lines.extend(
            [
                f'<line x1="{x:.3f}" y1="{top}" x2="{x:.3f}" y2="{height-bottom}" stroke="#e5e7eb"/>',
                f'<text x="{x:.3f}" y="{height-bottom+24}" text-anchor="middle" font-family="monospace" font-size="13">{x_value:.4g}</text>',
                f'<line x1="{left}" y1="{y:.3f}" x2="{width-right}" y2="{y:.3f}" stroke="#e5e7eb"/>',
                f'<text x="{left-10}" y="{y+4:.3f}" text-anchor="end" font-family="monospace" font-size="13">{y_value:.4g}</text>',
            ]
        )
    lines.extend(
        [
            f'<text x="{left + plot_width/2:.3f}" y="700" text-anchor="middle" font-family="sans-serif" font-size="16">{html.escape(x_label)}</text>',
            f'<text x="22" y="{top + plot_height/2:.3f}" text-anchor="middle" transform="rotate(-90 22 {top + plot_height/2:.3f})" font-family="sans-serif" font-size="16">{html.escape(y_label)}</text>',
        ]
    )
    for index, item in enumerate(prepared):
        color = colors[index % len(colors)]
        points = " ".join(
            f"{sx(row[0]):.3f},{sy(row[item['signal_index']]):.3f}" for row in item["rows"]
        )
        legend_y = top + 20 + 24 * index
        lines.extend(
            [
                f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{points}"/>',
                f'<line x1="{width-260}" y1="{legend_y}" x2="{width-220}" y2="{legend_y}" stroke="{color}" stroke-width="3"/>',
                f'<text x="{width-210}" y="{legend_y+5}" font-family="sans-serif" font-size="14">{html.escape(item["label"])}</text>',
            ]
        )
    lines.append("</svg>")

    output_path = Path(path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(output_path), "series_count": len(prepared)}


def _crossing_time(rows: List[List[float]], signal_index: int, target: float) -> float:
    for previous, current in zip(rows, rows[1:]):
        y0, y1 = previous[signal_index], current[signal_index]
        if (y0 <= target <= y1) or (y1 <= target <= y0):
            if y1 == y0:
                return current[0]
            fraction = (target - y0) / (y1 - y0)
            return previous[0] + fraction * (current[0] - previous[0])
    raise RuntimeError(f"waveform never crosses target {target:.6g}")


def rc_metrics(
    table: Table,
    vin: float,
    resistance: float,
    capacitance: float,
) -> Dict[str, float]:
    normalized = validate_table(table)
    signal_index = _column_index(normalized, "V(out)")
    theory_tau = resistance * capacitance
    measured_tau = _crossing_time(normalized["rows"], signal_index, vin * 0.632120558)
    rise_start = _crossing_time(normalized["rows"], signal_index, vin * 0.1)
    rise_end = _crossing_time(normalized["rows"], signal_index, vin * 0.9)
    final_voltage = normalized["rows"][-1][signal_index]
    return {
        "final_voltage_v": final_voltage,
        "final_voltage_error_percent": abs(final_voltage - vin) / abs(vin) * 100.0,
        "rise_time_10_90_s": rise_end - rise_start,
        "measured_tau_s": measured_tau,
        "theory_tau_s": theory_tau,
        "tau_error_percent": abs(measured_tau - theory_tau) / theory_tau * 100.0,
    }


def _window_rows(rows: List[List[float]], start_time: float) -> List[List[float]]:
    if start_time <= rows[0][0]:
        return rows
    for previous, current in zip(rows, rows[1:]):
        if start_time == current[0]:
            return rows[rows.index(current) :]
        if previous[0] < start_time < current[0]:
            fraction = (start_time - previous[0]) / (current[0] - previous[0])
            interpolated = [
                previous[index] + fraction * (current[index] - previous[index])
                for index in range(len(previous))
            ]
            later = [row for row in rows if row[0] > start_time]
            return [interpolated, *later]
    return []


def _time_average(rows: List[List[float]], signal_index: int) -> float:
    duration = rows[-1][0] - rows[0][0]
    if duration <= 0:
        raise RuntimeError("steady-state window duration must be positive")
    area = sum(
        (current[0] - previous[0])
        * (previous[signal_index] + current[signal_index])
        / 2.0
        for previous, current in zip(rows, rows[1:])
    )
    return area / duration


def buck_metrics(
    table: Table,
    vin: float,
    duty_cycle: float,
    steady_from: float,
) -> Dict[str, float]:
    normalized = validate_table(table)
    voltage_index = _column_index(normalized, "V(out)")
    current_index = _column_index(normalized, "I(L1)")
    steady_rows = _window_rows(normalized["rows"], steady_from)
    if len(steady_rows) < 2:
        raise RuntimeError("steady-state window must contain at least two waveform rows")
    voltages = [row[voltage_index] for row in steady_rows]
    currents = [row[current_index] for row in steady_rows]
    voltage_average = _time_average(steady_rows, voltage_index)
    voltage_min = min(voltages)
    voltage_max = max(voltages)
    ripple = voltage_max - voltage_min
    ideal = vin * duty_cycle
    return {
        "steady_from_s": steady_from,
        "vout_average_v": voltage_average,
        "vout_min_v": voltage_min,
        "vout_max_v": voltage_max,
        "vout_ripple_pp_v": ripple,
        "vout_ripple_percent": ripple / abs(voltage_average) * 100.0 if voltage_average else float("inf"),
        "inductor_current_average_a": _time_average(steady_rows, current_index),
        "inductor_current_min_a": min(currents),
        "inductor_current_peak_a": max(currents),
        "ideal_vout_v": ideal,
        "conversion_error_percent": abs(voltage_average - ideal) / abs(ideal) * 100.0,
    }


def export_from_args(args: Dict[str, Any]) -> Dict[str, Any]:
    input_path = Path(args.get("input_path") or "").expanduser().resolve()
    backend = str(args.get("backend") or "").lower()
    if backend not in {"ltspice", "ngspice"}:
        raise RuntimeError("backend must be ltspice or ngspice")
    table = read_waveform(input_path, backend)
    output_path = Path(args.get("output_path") or input_path.with_suffix(".csv")).expanduser().resolve()
    plot_path = Path(args.get("plot_path") or input_path.with_suffix(".svg")).expanduser().resolve()
    signal = str(args.get("signal") or table["columns"][1])
    csv_result = write_csv(table, output_path)
    plot_result = write_svg(
        [{"label": str(args.get("label") or signal), "table": table, "signal": signal}],
        plot_path,
        str(args.get("title") or "Waveform"),
        "Time (s)",
        str(args.get("y_label") or signal),
    )
    result: Dict[str, Any] = {
        "input_path": str(input_path),
        "backend": backend,
        "csv": csv_result,
        "plot": plot_result,
    }
    circuit_type = args.get("circuit_type")
    parameters = dict(args.get("parameters") or {})
    if circuit_type:
        try:
            from mcp import portable
        except ImportError:
            import portable
        if circuit_type == "rc_lowpass":
            result["metrics"] = rc_metrics(
                table,
                portable.spice_number(parameters.get("vin", "1")),
                portable.spice_number(parameters.get("resistance", "1k")),
                portable.spice_number(parameters.get("capacitance", "1u")),
            )
        elif circuit_type == "buck_converter":
            steady_value = parameters.get("steady_from", parameters.get("steady_from_s"))
            if steady_value is None:
                steady_from = table["rows"][0][0] + (
                    table["rows"][-1][0] - table["rows"][0][0]
                ) * 0.8
            else:
                steady_from = portable.spice_number(steady_value)
            result["metrics"] = buck_metrics(
                table,
                portable.spice_number(parameters.get("vin", parameters.get("vin_v", "12"))),
                portable.spice_number(parameters.get("duty_cycle", 5.0 / 12.0)),
                steady_from,
            )
        else:
            raise RuntimeError("circuit_type must be rc_lowpass or buck_converter")
        metrics_path = Path(
            args.get("metrics_path")
            or output_path.with_name(f"{output_path.stem}_metrics.json")
        ).expanduser().resolve()
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(
            json.dumps(result["metrics"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result["metrics_json"] = str(metrics_path)
    return result
