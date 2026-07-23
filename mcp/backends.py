import plistlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional


def _expand_executable(value: Optional[str], command: str) -> Optional[Path]:
    if value:
        candidate = Path(value).expanduser().resolve()
        if candidate.is_dir() and candidate.suffix == ".app":
            candidate = candidate / "Contents" / "MacOS" / "LTspice"
        return candidate if candidate.exists() else None
    found = shutil.which(command)
    return Path(found) if found else None


def _find_ltspice(value: Optional[str] = None) -> Optional[Path]:
    explicit = _expand_executable(value, "LTspice")
    if explicit:
        return explicit
    for app in (
        Path("/Applications/LTspice.app"),
        Path.home() / "Applications" / "LTspice.app",
    ):
        executable = app / "Contents" / "MacOS" / "LTspice"
        if executable.exists():
            return executable
    return None


def _ltspice_version(executable: Optional[Path]) -> Optional[str]:
    if not executable:
        return None
    app = executable.parents[2] if len(executable.parents) >= 3 else None
    plist_path = app / "Contents" / "Info.plist" if app else None
    if not plist_path or not plist_path.exists():
        return None
    try:
        with plist_path.open("rb") as handle:
            info = plistlib.load(handle)
        return info.get("CFBundleShortVersionString") or info.get("CFBundleVersion")
    except Exception:
        return None


def _command_version(executable: Optional[Path]) -> Optional[str]:
    if not executable:
        return None
    try:
        completed = subprocess.run(
            [str(executable), "--version"],
            text=True,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (completed.stdout or completed.stderr).strip()
    return text.splitlines()[0] if text else None


def detect_simulators(
    ltspice_path: Optional[str] = None,
    ngspice_path: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    ltspice = _find_ltspice(ltspice_path)
    ngspice = _expand_executable(ngspice_path, "ngspice")
    return {
        "ltspice": {
            "found": ltspice is not None,
            "executable": str(ltspice) if ltspice else None,
            "version": _ltspice_version(ltspice),
        },
        "ngspice": {
            "found": ngspice is not None,
            "executable": str(ngspice) if ngspice else None,
            "version": _command_version(ngspice),
        },
    }


def select_backend(name: str, detections: Dict[str, Dict[str, Any]]) -> str:
    normalized = (name or "auto").lower()
    if normalized not in {"auto", "ltspice", "ngspice"}:
        raise RuntimeError("backend must be auto, ltspice, or ngspice")
    if normalized == "auto":
        for candidate in ("ltspice", "ngspice"):
            if detections.get(candidate, {}).get("found"):
                return candidate
        raise RuntimeError("Neither LTspice nor ngspice is available")
    if not detections.get(normalized, {}).get("found"):
        label = "LTspice" if normalized == "ltspice" else "ngspice"
        raise RuntimeError(f"{label} backend is not available")
    return normalized


def _derived_paths(input_path: Path) -> Dict[str, Path]:
    return {
        "raw": input_path.with_suffix(".raw"),
        "log": input_path.with_suffix(".log"),
        "op_raw": input_path.with_suffix(".op.raw"),
        "net": input_path.with_suffix(".net"),
        "db": input_path.with_suffix(".db"),
    }


def _clear_derived(paths: Dict[str, Path]) -> None:
    for path in paths.values():
        if path.exists() and path.is_file():
            path.unlink()


def _run(
    command: list,
    cwd: Path,
    timeout_seconds: int,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
    )


def _status(
    completed: subprocess.CompletedProcess,
    backend: str,
    executable: str,
    command: list,
    cwd: Path,
    raw_path: Path,
    log_path: Path,
    staged_for_whitespace: bool,
) -> Dict[str, Any]:
    if completed.returncode != 0:
        reason = f"{backend}_returncode_nonzero"
    elif not raw_path.exists() or raw_path.stat().st_size == 0:
        reason = "waveform_missing"
    else:
        reason = "simulation_passed"
    result: Dict[str, Any] = {
        "ok": reason == "simulation_passed",
        "reason": reason,
        "backend": backend,
        "executable": executable,
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
        "staged_for_whitespace": staged_for_whitespace,
    }
    if raw_path.exists() and raw_path.stat().st_size > 0:
        result["raw_path"] = str(raw_path)
    if log_path.exists():
        result["log_path"] = str(log_path)
    return result


def run_portable(
    input_path: Path,
    backend: str = "auto",
    timeout_seconds: int = 60,
    ltspice_path: Optional[str] = None,
    ngspice_path: Optional[str] = None,
) -> Dict[str, Any]:
    circuit = Path(input_path).expanduser().resolve()
    if not circuit.exists() or not circuit.is_file():
        raise RuntimeError("input_path must point to an existing SPICE input file")
    if timeout_seconds <= 0:
        raise RuntimeError("timeout_seconds must be positive")

    detections = detect_simulators(ltspice_path, ngspice_path)
    chosen = select_backend(backend, detections)
    executable = str(detections[chosen]["executable"])
    expected = _derived_paths(circuit)
    _clear_derived(expected)

    staged_for_whitespace = chosen == "ltspice" and " " in str(circuit)
    if staged_for_whitespace:
        with tempfile.TemporaryDirectory(prefix="ltspice-v060-") as tmp:
            staged_input = Path(tmp) / circuit.name
            shutil.copy2(circuit, staged_input)
            staged_paths = _derived_paths(staged_input)
            command = [executable, "-b", "-ascii", str(staged_input)]
            completed = _run(command, staged_input.parent, timeout_seconds)
            for name in ("raw", "log", "op_raw", "net", "db"):
                if staged_paths[name].exists():
                    shutil.copy2(staged_paths[name], expected[name])
    elif chosen == "ltspice":
        command = [executable, "-b", "-ascii", str(circuit)]
        completed = _run(command, circuit.parent, timeout_seconds)
    else:
        command = [
            executable,
            "-b",
            "-o",
            str(expected["log"]),
            "-r",
            str(expected["raw"]),
            str(circuit),
        ]
        completed = _run(command, circuit.parent, timeout_seconds)

    return _status(
        completed,
        chosen,
        executable,
        command,
        circuit.parent,
        expected["raw"],
        expected["log"],
        staged_for_whitespace,
    )
