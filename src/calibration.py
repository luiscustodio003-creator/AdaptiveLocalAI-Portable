"""Safe, isolated calibration support for AdaptiveLocalAI-Portable.

This module uses only the Python standard library. It does not load models itself;
it asks llama-bench to measure thread configurations while the host application
reports itself idle. A profile is used only while its model/runtime/hardware
fingerprint still matches.
"""
from __future__ import annotations

import copy
import ctypes
import hashlib
import json
import os
import platform
import subprocess
import tempfile
import threading
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Iterable

PROFILE_SCHEMA = 3
# AUTO_VALIDATION_V1
DEFAULT_MIN_FREE_RAM_GB = 4.0
# CALIBRATION_RAM_GUARD_V1
DEFAULT_EMERGENCY_FREE_RAM_GB = 2.0
DEFAULT_IDLE_SECONDS = 30.0
DEFAULT_TIMEOUT_SECONDS = 240.0
DEFAULT_TOLERANCE = 0.03


class CalibrationError(RuntimeError):
    """A calibration run could not complete safely or produce usable data."""


class Interrupted(RuntimeError):
    """A benchmark must stop because the app is busy or the user cancelled it."""


def candidate_threads(logical_threads: int | None = None) -> list[int]:
    """Conservative thread candidates, capped at half the logical CPU count.

    The fractions intentionally match the proposed 24-thread test list:
    candidate_threads(24) -> [2, 4, 6, 9, 12].
    """
    n = max(1, int(logical_threads or os.cpu_count() or 1))
    if n <= 4:
        return list(range(1, n + 1))

    raw = (n / 12, n / 6, n / 4, 3 * n / 8, n / 2)
    values: list[int] = []
    for value in raw:
        rounded = int(value + 0.5)
        rounded = max(2, min(n // 2, rounded))
        if rounded not in values:
            values.append(rounded)
    return sorted(values)


def _safe_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result <= 0 or result != result or result == float("inf"):
        return None
    return result


def _is_generation_row(row: dict[str, Any]) -> bool:
    """Accept only explicitly labelled generation rows; never infer from throughput."""
    test_name = str(row.get("test", "") or "").strip().lower()
    return test_name.startswith("tg") or "generation" in test_name or test_name in {"gen", "generation"}


def summarize(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate generation throughput by thread count from llama-bench JSON."""
    materialized = [row for row in rows if isinstance(row, dict)]
    if not materialized:
        return []

    generation_rows = [row for row in materialized if _is_generation_row(row)]
    if not generation_rows:
        return []

    grouped: dict[int, list[float]] = {}
    for row in generation_rows:
        try:
            threads = int(row.get("n_threads", row.get("threads")))
        except (TypeError, ValueError):
            continue
        rate = _safe_float(row.get("avg_ts", row.get("tokens_per_second", row.get("tok_s"))))
        if threads < 1 or rate is None:
            continue
        grouped.setdefault(threads, []).append(rate)

    result = []
    for threads in sorted(grouped):
        rates = grouped[threads]
        result.append({
            "threads": threads,
            "tok_s": round(mean(rates), 4),
            "samples": len(rates),
            "min_tok_s": round(min(rates), 4),
            "max_tok_s": round(max(rates), 4),
        })
    return result


def pick_best(summary: Iterable[dict[str, Any]], tolerance: float = DEFAULT_TOLERANCE) -> dict[str, Any] | None:
    """Choose the least threads within ``tolerance`` of peak throughput."""
    candidates = []
    for item in summary:
        if not isinstance(item, dict):
            continue
        try:
            threads = int(item.get("threads"))
            rate = float(item.get("tok_s"))
        except (TypeError, ValueError):
            continue
        if threads > 0 and rate > 0 and rate == rate and rate != float("inf"):
            candidates.append({**item, "threads": threads, "tok_s": rate})

    if not candidates:
        return None
    fastest = max(item["tok_s"] for item in candidates)
    cutoff = fastest * (1.0 - max(0.0, min(float(tolerance), 0.5)))
    eligible = [item for item in candidates if item["tok_s"] >= cutoff]
    return dict(min(eligible, key=lambda item: (item["threads"], -item["tok_s"])))


def available_ram_gb() -> float | None:
    """Return available physical RAM in GiB, on Windows and common Unix hosts."""
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        try:
            status = MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return status.ullAvailPhys / (1024 ** 3)
        except Exception:
            return None

    try:
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return (pages * page_size) / (1024 ** 3)
    except (AttributeError, OSError, ValueError):
        return None


def _file_info(path: Path) -> dict[str, Any]:
    """Identify a file by metadata and SHA-256 without loading it into RAM."""
    before = path.stat()
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(4 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    after = path.stat()

    # Do not accept an identity computed while the file was changing.
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
    ):
        raise OSError(f"Ficheiro alterado durante o cálculo do SHA-256: {path}")

    return {
        # Relative identity keeps portable profiles independent of installation paths.
        "path": path.name,
        "size_bytes": after.st_size,
        "mtime_ns": after.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def _model_name(name: str) -> str:
    # Model files are discovered in one flat directory. Reject path traversal.
    base = Path(str(name)).name
    if not base or base in {".", ".."} or not base.lower().endswith(".gguf"):
        raise CalibrationError("Nome de modelo inválido; indica o nome de um ficheiro .gguf.")
    return base


class Calibrator:
    """Background llama-bench worker with idle/RAM guards and atomic profiles.

    ``runtime_provider`` may return either llama-bench.exe or a runtime directory.
    An injected ``runner`` is intended for tests and must accept the arguments
    ``(model_path, bench_path, thread_candidates, cancel_event, must_interrupt)``.
    """

    def __init__(
        self,
        root: str | Path,
        runtime_provider: Callable[[], str | Path | None],
        idle: Callable[[], bool],
        runner: Callable[..., list[dict[str, Any]]] | None = None,
        *,
        ram_provider: Callable[[], float | None] = available_ram_gb,
        min_free_ram_gb: float = DEFAULT_MIN_FREE_RAM_GB,
        emergency_free_ram_gb: float = DEFAULT_EMERGENCY_FREE_RAM_GB,
        idle_seconds: float = DEFAULT_IDLE_SECONDS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        tolerance: float = DEFAULT_TOLERANCE,
        poll_interval: float = 0.25,
        validator: Callable[[str, int, threading.Event, Callable[[], bool]], dict[str, Any]] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.models_dir = self.root / "models"
        self.profiles_path = self.root / "data" / "profiles.json"
        self.runtime_provider = runtime_provider
        self.idle = idle
        self.runner = runner or self._run_benchmark
        self.validator = validator
        self.ram_provider = ram_provider
        self.min_free_ram_gb = float(min_free_ram_gb)
        self.emergency_free_ram_gb = max(1.0, float(emergency_free_ram_gb))
        self.idle_seconds = max(0.0, float(idle_seconds))
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.tolerance = max(0.0, min(float(tolerance), 0.5))
        self.poll_interval = max(0.05, float(poll_interval))

        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self._status: dict[str, Any] = {
            "state": "idle", "model": None, "run_id": None, "started_at": None,
            "updated_at": None, "error": None, "result": None,
        }
        self._process: subprocess.Popen[bytes] | None = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._status)

    def execution_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": copy.deepcopy(self._status),
                "worker_alive": bool(
                    self._worker is not None and self._worker.is_alive()
                ),
            }


    def _set_status(self, state: str, **extra: Any) -> None:
        with self._lock:
            self._status.update(state=state, updated_at=_now(), **extra)

    def start(self, model_name: str) -> dict[str, Any]:
        name = _model_name(model_name)
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return {"accepted": False, "reason": "busy", **copy.deepcopy(self._status)}
            self._cancel = threading.Event()
            run_id = uuid.uuid4().hex
            self._status = {
                "state": "waiting_idle", "model": name, "run_id": run_id,
                "started_at": _now(), "updated_at": _now(),
                "error": None, "result": None,
            }
            self._worker = threading.Thread(
                target=self._worker_main,
                args=(name, self._cancel),
                name="AdaptiveLocalAI-Calibrator",
                daemon=True,
            )
            self._worker.start()
            return {"accepted": True, **copy.deepcopy(self._status)}

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            worker = self._worker
            if worker is None or not worker.is_alive():
                return {"accepted": False, **copy.deepcopy(self._status)}
            self._cancel.set()
            self._status.update(state="cancelling", updated_at=_now())
            process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        return {"accepted": True, **self.status()}

    def wait(self, timeout: float | None = None) -> dict[str, Any]:
        with self._lock:
            worker = self._worker
        if worker is not None:
            worker.join(timeout=timeout)
        return self.status()

    def profile(self, model_name: str, *, include_stale: bool = False) -> dict[str, Any] | None:
        name = _model_name(model_name)
        model_path = self.models_dir / name
        if not model_path.is_file():
            return None
        try:
            db = self._read_profiles()
            entry = db.get("profiles", {}).get(name)
            if not isinstance(entry, dict):
                return None
            validation = entry.get("validation")
            validation_passed = (
                isinstance(validation, dict)
                and validation.get("passed") is True
            )
            if not validation_passed and not include_stale:
                return None
            current = self._fingerprint(model_path, self._find_bench())
            stale = entry.get("fingerprint") != current
            if stale and not include_stale:
                return None
            result = copy.deepcopy(entry)
            result["stale"] = stale
            return result
        except (OSError, CalibrationError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def _worker_main(self, name: str, cancel: threading.Event) -> None:
        try:
            model_path = self.models_dir / name
            if not model_path.is_file():
                raise CalibrationError(f"Modelo não encontrado: {model_path}")
            bench_path = self._find_bench()
            candidates = candidate_threads()
            if not candidates:
                raise CalibrationError("Não foi possível calcular candidatos de threads.")

            while not cancel.is_set():
                self._wait_until_safe(cancel)
                if cancel.is_set():
                    self._set_status("cancelled", error=None)
                    return
                self._set_status("benchmarking", error=None)
                try:
                    rows = self.runner(
                        model_path, bench_path, candidates, cancel,
                        self._must_interrupt,
                    )
                    if cancel.is_set():
                        self._set_status("cancelled", error=None)
                        return
                    summaries = [item for item in summarize(rows) if item["threads"] in candidates]
                    best = pick_best(summaries, self.tolerance)
                    if best is None:
                        raise CalibrationError("llama-bench terminou sem medições válidas de geração (avg_ts).")
                    fingerprint = self._fingerprint(model_path, bench_path)
                    profile = {
                        "schema": PROFILE_SCHEMA,
                        "model": name,
                        "created_at": _now(),
                        "threads": best["threads"],
                        "generation_tok_s": best["tok_s"],
                        "tolerance": self.tolerance,
                        "candidates": candidates,
                        "measurements": summaries,
                        "fingerprint": fingerprint,
                    }
                    if self.validator is None:
                        raise CalibrationError(
                            "Calibracao sem validador de inferencia real; "
                            "o perfil nao foi guardado."
                        )
                    profile["validation"] = {"status": "not_configured", "passed": False}
                    if self.validator is not None:
                        self._set_status("validating", error=None,
                                         result={"threads": best["threads"], "generation_tok_s": best["tok_s"]})
                        validation = self.validator(name, int(best["threads"]), cancel,
                                                     lambda: self._must_abort_validation(cancel))
                        if cancel.is_set():
                            self._set_status("cancelled", error=None)
                            return
                        if not isinstance(validation, dict) or validation.get("passed") is not True:
                            raise CalibrationError("A validacao de inferencia real falhou; o novo perfil nao foi guardado.")
                        profile["validation"] = copy.deepcopy(validation)
                    # Reject profiles if model/runtime changed during validation.
                    final_fingerprint = self._fingerprint(model_path, bench_path)
                    if final_fingerprint != fingerprint:
                        raise CalibrationError(
                            "A identidade do modelo/runtime mudou durante a calibração; perfil não guardado."
                        )
                    self._write_profile(name, profile)
                    self._set_status("done", error=None, result=copy.deepcopy(profile))
                    return
                except Interrupted:
                    if cancel.is_set():
                        self._set_status("cancelled", error=None)
                        return
                    self._set_status("waiting_idle", error=None,
                                     message="Benchmark interrompido porque a aplicação deixou de estar ociosa; será retomado.")
                    continue
            if cancel.is_set():
                self._set_status("cancelled", error=None)
        except Exception as exc:
            if cancel.is_set():
                self._set_status("cancelled", error=None)
            else:
                self._set_status("error", error=f"{type(exc).__name__}: {exc}")

    def _wait_until_safe(self, cancel: threading.Event) -> None:
        idle_since: float | None = None
        while not cancel.is_set():
            try:
                is_idle = bool(self.idle())
            except Exception:
                is_idle = False
            free_gb = self.ram_provider()
            enough_ram = free_gb is not None and free_gb >= self.min_free_ram_gb

            if is_idle and enough_ram:
                if idle_since is None:
                    idle_since = time.monotonic()
                remaining = self.idle_seconds - (time.monotonic() - idle_since)
                if remaining <= 0:
                    return
                self._set_status("waiting_idle", wait_seconds=round(remaining, 1),
                                 free_ram_gb=round(free_gb, 2) if free_gb is not None else None)
            else:
                idle_since = None
                if not enough_ram:
                    self._set_status("waiting_memory", free_ram_gb=round(free_gb, 2) if free_gb is not None else None,
                                     required_ram_gb=self.min_free_ram_gb)
                else:
                    self._set_status("waiting_idle", wait_seconds=self.idle_seconds,
                                     free_ram_gb=round(free_gb, 2) if free_gb is not None else None)
            cancel.wait(self.poll_interval)

    def _must_interrupt(self) -> bool:
        if self._cancel.is_set():
            return True
        try:
            if not bool(self.idle()):
                return True
        except Exception:
            return True
        free_gb = self.ram_provider()
        return free_gb is None or free_gb < self.emergency_free_ram_gb

    def _must_abort_validation(self, cancel: threading.Event) -> bool:
        if cancel.is_set():
            return True
        try:
            free_gb = self.ram_provider()
        except Exception:
            return True
        return free_gb is None or free_gb < self.emergency_free_ram_gb

    def _find_bench(self) -> Path:
        supplied = self.runtime_provider()
        if supplied is None:
            raise CalibrationError("Runtime não encontrado.")
        path = Path(supplied).resolve()
        if path.is_file():
            if path.name.lower() != "llama-bench.exe" and path.name.lower() != "llama-bench":
                raise CalibrationError(f"O executável indicado não é llama-bench: {path}")
            bench = path
        elif path.is_dir():
            matches = sorted(path.rglob("llama-bench.exe")) + sorted(path.rglob("llama-bench"))
            if not matches:
                raise CalibrationError(f"llama-bench não encontrado em: {path}")
            bench = matches[0]
        else:
            raise CalibrationError(f"Runtime não existe: {path}")
        if not bench.is_file():
            raise CalibrationError(f"llama-bench não é um ficheiro: {bench}")
        return bench

    def _fingerprint(self, model_path: Path, bench_path: Path) -> dict[str, Any]:
        try:
            # Identify platform-specific shared libraries and the server used for inference.
            runtime_dir = bench_path.parent
            library_patterns = ("*.dll", "*.so", "*.so.*", "*.dylib")
            libraries = {
                path.resolve() for pattern in library_patterns
                for path in runtime_dir.glob(pattern) if path.is_file()
            }
            server_names = ("llama-server.exe", "llama-server")
            server_path = next((runtime_dir / name for name in server_names
                                if (runtime_dir / name).is_file()), None)
            runtime_libraries = [_file_info(path) for path in sorted(libraries, key=lambda p: p.name.lower())]
            return {
                "schema": PROFILE_SCHEMA,
                "model": _file_info(model_path),
                "runtime": {
                    "benchmark": _file_info(bench_path),
                    "server": _file_info(server_path) if server_path else None,
                    "libraries": runtime_libraries,
                    "platform": platform.system().lower(),
                    "architecture": platform.machine().lower(),
                },
                "benchmark_config": {
                    "prompt_tokens": 32,
                    "generation_tokens": 32,
                    "repetitions": 2,
                    "gpu_layers": 0,
                    "batch_size": 128,
                    "ubatch_size": 128,
                    "selection_metric": "generation_tok_s",
                },
                "hardware": {
                    "system": platform.system(),
                    "release": platform.release(),
                    "machine": platform.machine(),
                    "processor": platform.processor(),
                    "logical_threads": os.cpu_count() or 1,
                },
            }
        except OSError as exc:
            raise CalibrationError(f"Não foi possível identificar o modelo/runtime: {exc}") from exc

    def _read_profiles(self) -> dict[str, Any]:
        if not self.profiles_path.exists():
            return {"schema": PROFILE_SCHEMA, "profiles": {}}
        try:
            with self.profiles_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            raise CalibrationError(f"Não foi possível ler {self.profiles_path}: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("profiles", {}), dict):
            raise CalibrationError("O ficheiro de perfis tem uma estrutura inválida; foi preservado sem alterações.")
        return data

    def _write_profile(self, name: str, profile: dict[str, Any]) -> None:
        self.profiles_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._read_profiles()
        data["schema"] = PROFILE_SCHEMA
        data.setdefault("profiles", {})[name] = profile
        fd, temp_name = tempfile.mkstemp(
            prefix="profiles-", suffix=".tmp", dir=str(self.profiles_path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_name, self.profiles_path)
        finally:
            try:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
            except OSError:
                pass

    def _run_benchmark(
        self,
        model_path: Path,
        bench_path: Path,
        thread_candidates: list[int],
        cancel: threading.Event,
        must_interrupt: Callable[[], bool],
    ) -> list[dict[str, Any]]:
        """Run one JSON benchmark sweep; interrupt promptly when the app gets busy."""
        args = [
            str(bench_path), "-m", str(model_path),
            "-p", "32", "-n", "32", "-r", "2",
            "-t", ",".join(str(n) for n in thread_candidates),
            "-ngl", "0", "-b", "128", "-ub", "128",
            "-o", "json", "--offline",
        ]
        stdout_file = tempfile.TemporaryFile(mode="w+b")
        stderr_file = tempfile.TemporaryFile(mode="w+b")
        process: subprocess.Popen[bytes] | None = None
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            try:
                process = subprocess.Popen(
                    args,
                    cwd=str(self.root),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    creationflags=creationflags,
                )
            except OSError as exc:
                raise CalibrationError(f"Não foi possível iniciar llama-bench: {exc}") from exc

            with self._lock:
                self._process = process
            started = time.monotonic()
            while process.poll() is None:
                if cancel.is_set() or must_interrupt():
                    _stop_process(process)
                    if cancel.is_set():
                        raise Interrupted("Calibração cancelada pelo utilizador.")
                    raise Interrupted("A aplicação deixou de estar ociosa ou a RAM ficou abaixo do limite.")
                if time.monotonic() - started > self.timeout_seconds:
                    _stop_process(process)
                    raise CalibrationError(f"llama-bench excedeu {self.timeout_seconds:.0f} segundos.")
                time.sleep(self.poll_interval)

            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr = stderr_file.read().decode("utf-8", errors="replace")
            if process.returncode != 0:
                detail = (stderr or stdout).strip()[-1500:]
                raise CalibrationError(f"llama-bench terminou com código {process.returncode}. {detail}")
            return _parse_bench_json(stdout)
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None
            stdout_file.close()
            stderr_file.close()


def _parse_bench_json(output: str) -> list[dict[str, Any]]:
    raw = output.strip()
    if not raw:
        raise CalibrationError("llama-bench não produziu JSON no stdout.")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # Permit newline-delimited JSON from compatible future builds.
        payload = []
        for line in raw.splitlines():
            line = line.strip().rstrip(",")
            if line.startswith("{"):
                try:
                    payload.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if not payload:
            raise CalibrationError("Não foi possível interpretar o JSON produzido por llama-bench.")
    if isinstance(payload, dict):
        for key in ("results", "data", "benchmarks"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise CalibrationError("O JSON de llama-bench não contém uma lista de medições.")
    rows = [row for row in payload if isinstance(row, dict)]
    if not rows:
        raise CalibrationError("O JSON de llama-bench não contém linhas de resultados.")
    return rows


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=2.0)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=2.0)
        except Exception:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
