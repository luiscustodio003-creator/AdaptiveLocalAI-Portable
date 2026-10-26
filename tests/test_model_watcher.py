import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from model_watcher import ModelDirectoryWatcher


class FakeCalibrator:
    def __init__(self):
        self.started = []
        self.current = {"state": "idle", "model": None, "run_id": None, "error": None}
        self.counter = 0
        self.worker_alive = False

    def start(self, name):
        if self.worker_alive:
            return {"accepted": False, "reason": "busy", **self.current}
        self.started.append(name)
        self.counter += 1
        run_id = f"fake-run-{self.counter}"
        self.current = {"state": "waiting_idle", "model": name, "run_id": run_id, "error": None}
        self.worker_alive = True
        return {"accepted": True, **self.current}

    def status(self):
        return dict(self.current)

    def execution_snapshot(self):
        return {"status": dict(self.current), "worker_alive": self.worker_alive}

    def profile(self, name):
        return None


def make_file(path, payload=b"x" * 1024):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"GGUF" + payload)
    return path


def test_first_run_seeds_existing_models_without_auto_calibrating(tmp_path):
    make_file(tmp_path / "models" / "old.gguf")
    watcher = ModelDirectoryWatcher(tmp_path, FakeCalibrator(), stable_observations=2)
    watcher.initialize()
    assert watcher.scan_once() == []
    assert watcher._inventory["old.gguf"]["status"] == "baseline"


def test_new_stable_gguf_is_queued(tmp_path):
    calibrator = FakeCalibrator()
    watcher = ModelDirectoryWatcher(tmp_path, calibrator, stable_observations=3)
    watcher.initialize()
    make_file(tmp_path / "models" / "new.gguf")
    assert watcher.scan_once() == []
    assert watcher.scan_once() == []
    assert watcher.scan_once() == ["new.gguf"]
    assert watcher._inventory["new.gguf"]["status"] == "pending"


def test_mmproj_is_excluded(tmp_path):
    watcher = ModelDirectoryWatcher(tmp_path, FakeCalibrator(), stable_observations=2)
    watcher.initialize()
    make_file(tmp_path / "models" / "mmproj-test.gguf")
    assert watcher.scan_once() == []
    assert "mmproj-test.gguf" not in watcher._inventory


def test_notify_requires_real_gguf_file(tmp_path):
    watcher = ModelDirectoryWatcher(tmp_path, FakeCalibrator())
    watcher.initialize()
    invalid = tmp_path / "models" / "partial.gguf"
    invalid.parent.mkdir(parents=True, exist_ok=True)
    invalid.write_bytes(b"not a gguf file")
    assert watcher.notify_model_installed("partial.gguf")["accepted"] is False


def test_notify_installed_model_queues_immediately(tmp_path):
    watcher = ModelDirectoryWatcher(tmp_path, FakeCalibrator())
    watcher.initialize()
    make_file(tmp_path / "models" / "ready.gguf")
    result = watcher.notify_model_installed("ready.gguf")
    assert result["accepted"] is True
    assert watcher._inventory["ready.gguf"]["status"] == "pending"


def test_mismatched_run_id_requeues_model_without_false_success(tmp_path):
    calibrator = FakeCalibrator()
    watcher = ModelDirectoryWatcher(tmp_path, calibrator)
    watcher.initialize()

    make_file(tmp_path / "models" / "auto.gguf")
    result = watcher.notify_model_installed("auto.gguf")
    assert result["accepted"] is True

    watcher._advance_queue()
    assert watcher._active_model == "auto.gguf"
    assert watcher._inventory["auto.gguf"]["status"] == "calibrating"

    # Outra calibra??o est? a decorrer: o resultado n?o pode validar auto.gguf.
    calibrator.current = {
        "state": "waiting_idle",
        "model": "manual.gguf",
        "run_id": "another-run",
        "error": None,
    }
    calibrator.worker_alive = True
    watcher._advance_queue()

    assert watcher._active_model is None
    assert watcher._active_run_id is None
    assert watcher._inventory["auto.gguf"]["status"] == "pending"
    assert watcher.status().get("last_event") == "calibration_run_mismatch"
    assert "auto.gguf" not in []

    # A tentativa seguinte encontra o calibrador ocupado e preserva a fila.
    watcher._advance_queue()
    assert watcher._active_model is None
    assert watcher._inventory["auto.gguf"]["status"] == "pending"
    assert watcher.status().get("state") == "waiting_calibrator"
    assert calibrator.started == ["auto.gguf"]

    # Quando o worker termina, o modelo pendente pode ser iniciado novamente.
    calibrator.current = {
        "state": "done",
        "model": "manual.gguf",
        "run_id": "another-run",
        "error": None,
    }
    calibrator.worker_alive = False
    watcher._advance_queue()

    assert watcher._active_model == "auto.gguf"
    assert watcher._active_run_id == "fake-run-2"
    assert watcher._inventory["auto.gguf"]["status"] == "calibrating"
    assert calibrator.started == ["auto.gguf", "auto.gguf"]

