import csv
import re
from pathlib import Path
from typing import Any, Dict, List

try:
    from mcp import buck
    from mcp import portable
    from mcp import waveforms
except ImportError:
    import buck
    import portable
    import waveforms


SUPPORTED = {
    "rc_lowpass": {"resistance", "capacitance"},
    "buck_converter": {"duty_cycle"},
}


def validate_request(args: Dict[str, Any]) -> Dict[str, Any]:
    circuit_type = str(args.get("circuit_type") or "")
    parameter = str(args.get("parameter") or "")
    values = args.get("values")
    if circuit_type not in SUPPORTED or parameter not in SUPPORTED.get(circuit_type, set()):
        raise RuntimeError(
            "supported sweep combinations are RC resistance/capacitance and Buck duty_cycle"
        )
    if not isinstance(values, list) or not 2 <= len(values) <= 20:
        raise RuntimeError("sweep values must contain 2 through 20 explicit values")

    normalized_values = []
    numeric_values = []
    for value in values:
        number = portable.spice_number(value)
        if parameter in {"resistance", "capacitance"} and number <= 0:
            raise RuntimeError(f"{parameter} sweep values must be positive")
        if parameter == "duty_cycle" and not 0 < number < 1:
            raise RuntimeError("0 < duty_cycle < 1 is required")
        normalized_values.append(value)
        numeric_values.append(number)
    if len(set(numeric_values)) != len(numeric_values):
        raise RuntimeError("sweep values contain duplicate numeric values")

    backend = str(args.get("backend") or "auto").lower()
    if backend not in {"auto", "ltspice", "ngspice"}:
        raise RuntimeError("backend must be auto, ltspice, or ngspice")
    timeout_seconds = int(args.get("timeout_seconds", 120))
    if timeout_seconds <= 0:
        raise RuntimeError("timeout_seconds must be positive")
    parameters = dict(args.get("parameters") or {})
    representative = dict(parameters)
    representative[parameter] = normalized_values[0]
    if circuit_type == "rc_lowpass":
        portable.rc_netlist(
            representative.get("resistance", "1k"),
            representative.get("capacitance", "1u"),
            representative.get("vin", "1"),
        )
    else:
        buck.validate_parameters(representative)
    return {
        "circuit_type": circuit_type,
        "parameter": parameter,
        "values": normalized_values,
        "parameters": parameters,
        "output_dir": str(Path(args.get("output_dir") or Path.cwd()).expanduser().resolve()),
        "backend": backend,
        "timeout_seconds": timeout_seconds,
        "overwrite": bool(args.get("overwrite", False)),
        "ltspice_path": args.get("ltspice_path"),
        "ngspice_path": args.get("ngspice_path"),
    }


def _point_id(index: int, value: Any) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip()).strip("-")
    return f"point-{index:02d}-{label or 'value'}"


def _run_point(request: Dict[str, Any], point_dir: Path, value: Any) -> Dict[str, Any]:
    parameters = dict(request["parameters"])
    parameters[request["parameter"]] = value
    simulator_paths = {
        "ltspice_path": request.get("ltspice_path"),
        "ngspice_path": request.get("ngspice_path"),
    }
    if request["circuit_type"] == "rc_lowpass":
        result = portable.run_rc_case(
            point_dir,
            parameters,
            request["backend"],
            simulator_paths=simulator_paths,
            timeout_seconds=request["timeout_seconds"],
        )
        if result.get("ok") and result.get("metrics"):
            checks = []
            for metric in ("tau_error_percent", "final_voltage_error_percent"):
                error = result["metrics"][metric]
                checks.append(
                    {
                        "metric": metric,
                        "value": error,
                        "limit": 2.0,
                        "status": "PASS" if error <= 2.0 else "FAIL",
                    }
                )
            result["validation"] = {
                "status": "PASS"
                if all(check["status"] == "PASS" for check in checks)
                else "FAIL",
                "checks": checks,
            }
        return result

    result = buck.create_buck(
        point_dir,
        "buck",
        parameters,
        overwrite=request["overwrite"],
        simulate=True,
        backend=request["backend"],
        timeout_seconds=request["timeout_seconds"],
        ltspice_path=request.get("ltspice_path"),
        ngspice_path=request.get("ngspice_path"),
    )
    status = result.get("simulation_status") or {}
    result["ok"] = bool(status.get("ok"))
    result["reason"] = status.get("reason", "simulation_failed")
    result["backend"] = (result.get("simulation") or {}).get("backend", request["backend"])
    return result


def _point_status(result: Dict[str, Any]) -> str:
    if not result.get("ok"):
        return "FAIL"
    validation = result.get("validation")
    if validation and validation.get("status") != "PASS":
        return "FAIL"
    return "PASS"


def _write_summary(points: List[Dict[str, Any]], path: Path) -> None:
    metric_names = sorted(
        {
            name
            for point in points
            for name in (point.get("metrics") or {}).keys()
        }
    )
    fields = [
        "index",
        "parameter",
        "value",
        "status",
        "reason",
        "error",
        "backend",
        "waveform_csv",
    ] + metric_names
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for point in points:
            row = {field: "" for field in fields}
            row.update(
                {
                    "index": point["index"],
                    "parameter": point["parameter"],
                    "value": point["value"],
                    "status": point["status"],
                    "reason": point.get("reason", ""),
                    "error": point.get("error", ""),
                    "backend": point.get("backend", ""),
                    "waveform_csv": point.get("waveform_csv", ""),
                }
            )
            row.update(point.get("metrics") or {})
            writer.writerow(row)


def _render_report(request: Dict[str, Any], points: List[Dict[str, Any]], status: str, plot_path: str) -> str:
    def cell(value: Any) -> str:
        return str(value or "").replace("\n", " ").replace("|", "\\|")

    rows = []
    for point in points:
        metrics = ", ".join(
            f"{name}={value:.6g}" if isinstance(value, (int, float)) else f"{name}={value}"
            for name, value in sorted((point.get("metrics") or {}).items())
        )
        rows.append(
            f"| {point['index']} | `{point['value']}` | `{point['status']}` | "
            f"`{cell(point.get('reason'))}` | {cell(point.get('error')) or 'n/a'} | "
            f"{metrics or 'n/a'} |"
        )
    return "\n".join(
        [
            "# Parameter Sweep Report",
            "",
            f"- Circuit: `{request['circuit_type']}`",
            f"- Parameter: `{request['parameter']}`",
            f"- Backend request: `{request['backend']}`",
            f"- Overall result: `{status}`",
            f"- Overlay plot: `{plot_path or 'n/a'}`",
            "",
            "| Index | Value | Status | Reason | Error | Metrics |",
            "| ---: | --- | --- | --- | --- | --- |",
            *rows,
            "",
            "A sweep passes only when every point completes simulation, waveform analysis, and circuit validation.",
            "",
        ]
    )


def run_sweep(args: Dict[str, Any]) -> Dict[str, Any]:
    request = validate_request(args)
    destination = Path(request["output_dir"])
    summary_path = destination / "sweep_summary.csv"
    plot_path = destination / "sweep_plot.svg"
    report_path = destination / "sweep_report.md"
    for path in (summary_path, plot_path, report_path):
        if path.exists() and not request["overwrite"]:
            raise RuntimeError(f"Refusing to overwrite existing file: {path}")
    point_directories = [
        destination / _point_id(index, value)
        for index, value in enumerate(request["values"], 1)
    ]
    if not request["overwrite"]:
        for point_dir in point_directories:
            if point_dir.exists():
                raise RuntimeError(f"Refusing to overwrite existing directory: {point_dir}")
    destination.mkdir(parents=True, exist_ok=True)

    points: List[Dict[str, Any]] = []
    for index, (value, point_dir) in enumerate(
        zip(request["values"], point_directories),
        1,
    ):
        point_dir.mkdir(parents=True, exist_ok=True)
        try:
            raw_result = _run_point(request, point_dir, value)
        except Exception as exc:
            raw_result = {
                "ok": False,
                "reason": "point_exception",
                "error": str(exc),
                "backend": request["backend"],
            }
        point = dict(raw_result)
        point_status = _point_status(raw_result)
        point.update(
            {
                "index": index,
                "parameter": request["parameter"],
                "value": value,
                "status": point_status,
                "point_dir": str(point_dir),
            }
        )
        validation = raw_result.get("validation")
        if (
            point_status == "FAIL"
            and raw_result.get("ok")
            and validation
            and validation.get("status") != "PASS"
        ):
            point["reason"] = "validation_failed"
        elif not point.get("reason"):
            point["reason"] = (
                "simulation_passed"
                if point["status"] == "PASS"
                else "validation_failed"
            )
        points.append(point)

    successful_series = []
    for point in points:
        waveform_csv = point.get("waveform_csv")
        if point["status"] == "PASS" and waveform_csv:
            table = waveforms.read_csv(Path(waveform_csv))
            successful_series.append(
                {
                    "label": f"{request['parameter']}={point['value']}",
                    "table": table,
                    "signal": "V(out)",
                }
            )
    plot = None
    if successful_series:
        plot = waveforms.write_svg(
            successful_series,
            plot_path,
            f"{request['circuit_type']} {request['parameter']} sweep",
            "Time (s)",
            "Output voltage (V)",
        )

    _write_summary(points, summary_path)
    status = "PASS" if all(point["status"] == "PASS" for point in points) else "FAIL"
    report_path.write_text(
        _render_report(request, points, status, plot["path"] if plot else ""),
        encoding="utf-8",
    )
    result: Dict[str, Any] = {
        "ok": status == "PASS",
        "status": status,
        "circuit_type": request["circuit_type"],
        "parameter": request["parameter"],
        "points": points,
        "summary_csv": str(summary_path),
        "report": {"path": str(report_path)},
    }
    if plot:
        result["plot"] = plot
    return result
