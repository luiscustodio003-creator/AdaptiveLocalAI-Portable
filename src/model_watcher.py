"""Detect newly completed GGUF models and queue background calibration.

The watcher seeds a baseline on first start, then reacts to new/replaced files.
A GGUF is considered stable only after repeated unchanged observations and a
valid GGUF magic header. A downloader should call notify_model_installed() only
AFTER finalizing a completed download; the folder watcher remains a fallback.
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ModelDirectoryWatcher:
    def __init__(self, root: str | Path, calibrator: Any, *, poll_seconds: float = 3.0,
                 stable_observations: int = 10) -> None:
        self.root = Path(root).resolve()
        self.models_dir = self.root / "models"
        self.state_path = self.root / "data" / "model_install_state.json"
        self.calibrator = calibrator
        self.poll_seconds = max(0.5, float(poll_seconds))
        self.stable_observations = max(2, int(stable_observations))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._inventory: dict[str, dict[str, Any]] = {}
        self._stable: dict[str, dict[str, Any]] = {}
        self._initialized = False
        self._active_model: str | None = None
        self._active_run_id: str | None = None
        self._status: dict[str, Any] = {
            "enabled": True, "state": "stopped", "model": None,
            "queued": 0, "last_event": None, "error": None,
        }
        self._load_state()

    def _load_state(self) -> None:
        if not self.state_path.is_file():
            self._inventory = {}
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            inventory = data.get("models", {}) if isinstance(data, dict) else {}
            if not isinstance(inventory, dict):
                raise ValueError("campo models invalido")
            self._inventory = {
                str(name): dict(record)
                for name, record in inventory.items()
                if isinstance(name, str) and isinstance(record, dict)
            }
            for name, record in self._inventory.items():
                if record.get("status") == "calibrating":
                    record["status"] = "pending"
                    record["error"] = "A aplicacao reiniciou antes de confirmar o resultado; nova tentativa agendada."
        except Exception as exc:
            # Fail closed: never overwrite a malformed persistent inventory silently.
            self._status.update(state="error", error=f"Nao foi possivel ler {self.state_path}: {exc}")
            self._inventory = {}
            self._initialized = True

    @staticmethod
    def _signature(path: Path) -> dict[str, Any] | None:
        try:
            stat = path.stat()
            if stat.st_size <= 0:
                return None
            with path.open("rb") as stream:
                magic = stream.read(4)
            if magic != b"GGUF":
                return None
            return {"size_bytes": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}
        except OSError:
            return None

    def _collect(self) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        if not self.models_dir.is_dir():
            return found
        try:
            files = list(self.models_dir.glob("*.gguf"))
        except OSError:
            return found
        for path in files:
            if path.name.lower().startswith("mmproj"):
                continue
            signature = self._signature(path)
            if signature is not None:
                found[path.name] = signature
        return found

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": 1, "updated_at": _now(), "models": self._inventory}
        temp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.state_path)

    def initialize(self) -> None:
        """Seed already-present models on first run; do not surprise-calibrate them."""
        with self._lock:
            if self._initialized:
                return
            current = self._collect()
            if not self.state_path.exists():
                self._inventory = {
                    name: {"signature": signature, "status": "baseline", "updated_at": _now(), "error": None}
                    for name, signature in current.items()
                }
                self._save()
            else:
                # Recovery: pending tasks are resumed by the worker; removed files are dropped.
                for name in list(self._inventory):
                    if name not in current:
                        self._inventory.pop(name, None)
                for name, signature in current.items():
                    record = self._inventory.get(name)
                    if record and record.get("signature") != signature:
                        self._stable[name] = {"signature": signature, "count": 1}
                self._save()
            self._initialized = True
            self._status.update(state="watching", last_event="baseline_ready", error=None)

    def start(self) -> None:
        self.initialize()
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="AdaptiveLocalAI-ModelWatcher", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        with self._lock:
            worker = self._thread
        if worker is not None:
            worker.join(timeout=max(0.0, timeout))
        with self._lock:
            self._status["state"] = "stopped"

    def status(self) -> dict[str, Any]:
        with self._lock:
            result = copy.deepcopy(self._status)
            result["queued"] = sum(1 for record in self._inventory.values() if record.get("status") == "pending")
            return result

    def notify_model_installed(self, model_name: str, *, force: bool = False) -> dict[str, Any]:
        name = Path(str(model_name)).name
        if not name.lower().endswith(".gguf") or name.lower().startswith("mmproj"):
            return {"accepted": False, "reason": "invalid_model_name"}
        path = self.models_dir / name
        signature = self._signature(path)
        if signature is None:
            return {"accepted": False, "reason": "model_missing_or_invalid_gguf"}
        with self._lock:
            existing = self._inventory.get(name, {})
            if existing.get("status") == "calibrating":
                return {"accepted": False, "reason": "busy", "model": name}
            if existing.get("signature") == signature and existing.get("status") in {"done", "baseline"} and not force:
                try:
                    profile = self.calibrator.profile(name)
                except Exception:
                    profile = None
                if profile is not None and not profile.get("stale", False):
                    return {"accepted": False, "reason": "already_calibrated", "model": name}
            self._inventory[name] = {
                "signature": signature, "status": "pending", "updated_at": _now(), "error": None,
            }
            self._save()
            self._status.update(state="queued", model=name, last_event="model_installed", error=None)
        return {"accepted": True, "model": name, "state": "pending", "forced": bool(force)}

    def recalibrate_existing(self, model_name: str) -> dict[str, Any]:
        """Explicitly queue a model from the initial baseline for a fresh calibration."""
        return self.notify_model_installed(model_name, force=True)

    def scan_once(self) -> list[str]:
        """One scan interval, exposed for deterministic unit tests."""
        if not self._initialized:
            self.initialize()
            return []
        current = self._collect()
        enqueued: list[str] = []
        changed = False
        with self._lock:
            for name in list(self._inventory):
                if name not in current and (self.models_dir / name).exists() is False:
                    self._inventory.pop(name, None)
                    self._stable.pop(name, None)
                    changed = True
            for name, signature in current.items():
                record = self._inventory.get(name)
                if record is not None and record.get("signature") == signature:
                    self._stable.pop(name, None)
                    continue
                previous = self._stable.get(name)
                if previous and previous.get("signature") == signature:
                    previous["count"] = int(previous.get("count", 0)) + 1
                else:
                    self._stable[name] = {"signature": signature, "count": 1}
                stable = self._stable[name]
                if int(stable["count"]) >= self.stable_observations:
                    self._inventory[name] = {
                        "signature": signature, "status": "pending", "updated_at": _now(), "error": None,
                    }
                    self._stable.pop(name, None)
                    enqueued.append(name)
                    changed = True
                    self._status.update(state="queued", model=name, last_event="stable_model_detected", error=None)
            if changed:
                self._save()
        return enqueued

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
                self._advance_queue()
            except Exception as exc:
                with self._lock:
                    self._status.update(state="error", error=f"{type(exc).__name__}: {exc}")
            self._stop.wait(self.poll_seconds)

    def _advance_queue(self) -> None:
        with self._lock:
            active = self._active_model
        if active is not None:
            cal_status = self.calibrator.status()
            state = str(cal_status.get("state", "unknown"))
            with self._lock:
                expected_run_id = self._active_run_id
            actual_run_id = cal_status.get("run_id")
            if not expected_run_id or actual_run_id != expected_run_id:
                snapshot_fn = getattr(self.calibrator, "execution_snapshot", None)
                snapshot = snapshot_fn() if callable(snapshot_fn) else {}
                worker_alive = bool(snapshot.get("worker_alive", False))

                with self._lock:
                    record = self._inventory.get(active)
                    if record is not None:
                        record["status"] = "pending"
                        record["updated_at"] = _now()
                        record["error"] = "Execução divergente; modelo devolvido à fila."
                    self._active_model = None
                    self._active_run_id = None
                    self._status.update(
                        state="waiting_calibrator" if worker_alive else "watching",
                        model=active,
                        last_event="calibration_run_mismatch",
                        error="Identidade da execução divergente; modelo devolvido à fila."
                    )
                    self._save()
                return
            if cal_status.get("model") != active:
                with self._lock:
                    self._status.update(
                        state="error", model=active,
                        last_event="calibration_model_mismatch",
                        error="O resultado da calibração pertence a outro modelo."
                    )
                return
            if state not in {"done", "error", "cancelled"}:
                with self._lock:
                    self._status.update(state="calibrating", model=active, error=None)
                return
            with self._lock:
                record = self._inventory.get(active)
                if record is not None:
                    record["status"] = "done" if state == "done" else state
                    record["updated_at"] = _now()
                    record["error"] = cal_status.get("error")
                self._active_model = None
                self._active_run_id = None
                self._status.update(state="watching" if state == "done" else state,
                                    model=active, last_event=f"calibration_{state}", error=cal_status.get("error"))
                self._save()
            return

        with self._lock:
            pending = sorted(
                (name for name, record in self._inventory.items() if record.get("status") == "pending"),
                key=lambda name: str(self._inventory[name].get("updated_at", "")),
            )
        if not pending:
            with self._lock:
                if self._status.get("state") not in {"error", "cancelled"}:
                    self._status.update(state="watching", model=None, error=None)
            return

        name = pending[0]
        try:
            result = self.calibrator.start(name)
        except Exception as exc:
            with self._lock:
                record = self._inventory.get(name)
                if record is not None:
                    record["status"] = "error"
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    record["updated_at"] = _now()
                self._status.update(state="error", model=name,
                                    last_event="calibration_start_failed",
                                    error=record.get("error") if record else str(exc))
                self._save()
            return
        if result.get("accepted"):
            with self._lock:
                self._active_model = name
                self._active_run_id = result.get("run_id")
                record = self._inventory.get(name)
                if record is not None:
                    record["status"] = "calibrating"
                    record["updated_at"] = _now()
                self._status.update(state="calibrating", model=name, last_event="calibration_started", error=None)
                self._save()
        elif result.get("reason") == "busy":
            with self._lock:
                record = self._inventory.get(name)
                if record is not None:
                    record["status"] = "pending"
                    record["updated_at"] = _now()
                self._status.update(
                    state="waiting_calibrator",
                    model=name,
                    last_event="calibration_waiting_for_busy_worker",
                    error=None,
                )
                self._save()
        else:
            with self._lock:
                record = self._inventory.get(name)
                if record is not None:
                    record["status"] = "error"
                    record["error"] = result.get("error") or result.get("reason") or "Calibracao recusada."
                    record["updated_at"] = _now()
                self._status.update(state="error", model=name, error=record.get("error") if record else "Calibracao recusada.")
                self._save()
