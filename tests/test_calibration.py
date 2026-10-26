import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import calibration as c


def test_candidates_24_threads():
    assert c.candidate_threads(24) == [2, 4, 6, 9, 12]


def test_pick_best_chooses_lowest_within_three_percent():
    rows = [
        {"test": "tg32", "n_threads": 2, "avg_ts": 10.0},
        {"test": "tg32", "n_threads": 4, "avg_ts": 20.0},
        {"test": "tg32", "n_threads": 6, "avg_ts": 19.8},
    ]
    selected = c.pick_best(c.summarize(rows))
    assert selected["threads"] == 4


def _make_project(tmp_path):
    root = tmp_path
    models = root / "models"
    runtime = root / "runtime" / "llama-test"
    models.mkdir()
    runtime.mkdir(parents=True)
    model = models / "m.gguf"
    model.write_bytes(b"mock-gguf-model")
    bench = runtime / "llama-bench.exe"
    bench.write_bytes(b"mock-bench")
    return root, model, runtime


def _runner_rows(model_path, bench_path, thread_candidates, cancel, must_interrupt):
    rows = []
    for index, threads in enumerate(thread_candidates):
        # The slowest candidate is clearly slower; remaining candidates are close.
        rate = 10.0 if index == 0 else (20.0 if index == 1 else 19.8)
        rows.append({"test": "tg32", "n_threads": threads, "avg_ts": rate})
    return rows


def test_profile_is_saved_and_becomes_stale_after_model_changes(tmp_path):
    root, model, runtime = _make_project(tmp_path)
    worker = c.Calibrator(
        root, lambda: runtime, lambda: True,
        runner=_runner_rows,
        validator=lambda *args: {"status": "passed", "passed": True, "tests": 3},
        ram_provider=lambda: 8.0,
        idle_seconds=0,
        poll_interval=0.01,
    )
    assert worker.start(model.name)["accepted"] is True
    status = worker.wait(timeout=3)
    assert status["state"] == "done", status
    profile = worker.profile(model.name)
    assert profile is not None
    assert profile["threads"] == c.candidate_threads()[1] if len(c.candidate_threads()) > 1 else c.candidate_threads()[0]
    assert profile["stale"] is False

    os.utime(model, (1, 1))
    assert worker.profile(model.name) is None
    stale = worker.profile(model.name, include_stale=True)
    assert stale is not None and stale["stale"] is True


def test_interrupted_run_retries_after_idle_resumes(tmp_path):
    root, model, runtime = _make_project(tmp_path)
    calls = {"count": 0}

    def runner(model_path, bench_path, thread_candidates, cancel, must_interrupt):
        calls["count"] += 1
        if calls["count"] == 1:
            raise c.Interrupted("simulated busy interval")
        return _runner_rows(model_path, bench_path, thread_candidates, cancel, must_interrupt)

    worker = c.Calibrator(
        root, lambda: runtime, lambda: True,
        runner=runner,
        validator=lambda *args: {"status": "passed", "passed": True, "tests": 3},
        ram_provider=lambda: 8.0,
        idle_seconds=0,
        poll_interval=0.01,
    )
    worker.start(model.name)
    status = worker.wait(timeout=3)
    assert status["state"] == "done", status
    assert calls["count"] == 2


def test_cancel_waiting_calibration(tmp_path):
    root, model, runtime = _make_project(tmp_path)
    worker = c.Calibrator(
        root, lambda: runtime, lambda: False,
        runner=_runner_rows,
        ram_provider=lambda: 8.0,
        idle_seconds=0,
        poll_interval=0.01,
    )
    worker.start(model.name)
    worker.cancel()
    status = worker.wait(timeout=3)
    assert status["state"] == "cancelled", status
    assert not (root / "data" / "profiles.json").exists()


def test_missing_profile_returns_none(tmp_path):
    root, model, runtime = _make_project(tmp_path)
    worker = c.Calibrator(root, lambda: runtime, lambda: True, ram_provider=lambda: 8.0)
    assert worker.profile(model.name) is None


def test_summary_uses_generation_rows_not_prompt_rows():
    rows = [
        {"test": "pp32", "n_threads": 2, "avg_ts": 1000.0},
        {"test": "tg32", "n_threads": 2, "avg_ts": 10.0},
        {"test": "pp32", "n_threads": 4, "avg_ts": 1800.0},
        {"test": "tg32", "n_threads": 4, "avg_ts": 19.0},
    ]
    summary = c.summarize(rows)
    assert [item["tok_s"] for item in summary] == [10.0, 19.0]


def test_parse_bench_json_array():
    rows = c._parse_bench_json('[{"test":"tg32","n_threads":4,"avg_ts":12.5}]')
    assert rows[0]["n_threads"] == 4
    assert rows[0]["avg_ts"] == 12.5


def test_emergency_memory_floor_is_separate_from_start_threshold(tmp_path):
    available = {"gb": 3.0}
    worker = c.Calibrator(
        tmp_path, lambda: None, lambda: True,
        ram_provider=lambda: available["gb"],
        min_free_ram_gb=4.0,
        emergency_free_ram_gb=2.0,
    )
    # 3 GB is too low to start, but not yet an emergency once running.
    assert worker._must_interrupt() is False
    available["gb"] = 1.5
    assert worker._must_interrupt() is True

def test_inference_validation_is_saved_in_profile(tmp_path):
    root, model, runtime = _make_project(tmp_path)
    calls = []

    def validator(name, threads, cancel, should_abort):
        calls.append((name, threads))
        assert should_abort() is False
        return {
            "status": "passed", "passed": True, "tests": 3,
            "median_tok_s": 12.5, "runs": [{"tok_s": 12.0}, {"tok_s": 12.5}, {"tok_s": 13.0}],
        }

    worker = c.Calibrator(
        root, lambda: runtime, lambda: True,
        runner=_runner_rows, validator=validator,
        ram_provider=lambda: 8.0, idle_seconds=0, poll_interval=0.01,
    )
    worker.start(model.name)
    status = worker.wait(timeout=3)
    assert status["state"] == "done", status
    profile = worker.profile(model.name)
    assert profile is not None
    assert profile["validation"]["passed"] is True
    assert profile["validation"]["tests"] == 3
    assert calls == [(model.name, profile["threads"])]


def test_failed_inference_validation_does_not_commit_new_profile(tmp_path):
    root, model, runtime = _make_project(tmp_path)

    worker = c.Calibrator(
        root, lambda: runtime, lambda: True,
        runner=_runner_rows,
        validator=lambda *args: {"status": "failed", "passed": False},
        ram_provider=lambda: 8.0, idle_seconds=0, poll_interval=0.01,
    )
    worker.start(model.name)
    status = worker.wait(timeout=3)
    assert status["state"] == "error", status
    assert worker.profile(model.name) is None


def test_legacy_profile_without_validation_is_diagnostic_only(tmp_path):
    root, model, runtime = _make_project(tmp_path)
    worker = c.Calibrator(root, lambda: runtime, lambda: True)

    worker.profiles_path.parent.mkdir(parents=True, exist_ok=True)
    worker.profiles_path.write_text(
        json.dumps({
            "schema": c.PROFILE_SCHEMA,
            "profiles": {
                model.name: {
                    "model": model.name,
                    "threads": 2,
                    "fingerprint": worker._fingerprint(model, runtime / "llama-bench.exe"),
                }
            },
        }),
        encoding="utf-8",
    )

    assert worker.profile(model.name) is None
    diagnostic = worker.profile(model.name, include_stale=True)
    assert diagnostic is not None
    assert "validation" not in diagnostic
    assert diagnostic["stale"] is False


def test_profile_with_failed_validation_is_not_usable(tmp_path):
    root, model, runtime = _make_project(tmp_path)
    worker = c.Calibrator(root, lambda: runtime, lambda: True)

    worker.profiles_path.parent.mkdir(parents=True, exist_ok=True)
    worker.profiles_path.write_text(
        json.dumps({
            "schema": c.PROFILE_SCHEMA,
            "profiles": {
                model.name: {
                    "model": model.name,
                    "threads": 2,
                    "validation": {"status": "failed", "passed": False},
                    "fingerprint": worker._fingerprint(model, runtime / "llama-bench.exe"),
                }
            },
        }),
        encoding="utf-8",
    )

    assert worker.profile(model.name) is None
    diagnostic = worker.profile(model.name, include_stale=True)
    assert diagnostic is not None
    assert diagnostic["validation"]["passed"] is False


def test_calibration_without_validator_does_not_save_profile(tmp_path):
    root, model, runtime = _make_project(tmp_path)
    worker = c.Calibrator(
        root, lambda: runtime, lambda: True,
        runner=_runner_rows,
        ram_provider=lambda: 8.0,
        idle_seconds=0,
        poll_interval=0.01,
    )

    worker.start(model.name)
    status = worker.wait(timeout=3)

    assert status["state"] == "error", status
    assert worker.profile(model.name) is None
    assert not worker.profiles_path.exists()



def test_profile_rejects_changed_model_with_same_size_and_mtime(tmp_path):
    root, model, runtime = _make_project(tmp_path)
    worker = c.Calibrator(
        root, lambda: runtime, lambda: True,
        runner=_runner_rows,
        validator=lambda *args: {"status": "passed", "passed": True, "tests": 3},
        ram_provider=lambda: 8.0,
        idle_seconds=0,
        poll_interval=0.01,
    )

    assert worker.start(model.name)["accepted"] is True
    status = worker.wait(timeout=5)
    assert status["state"] == "done", status
    assert worker.profile(model.name) is not None

    original_stat = model.stat()
    original_bytes = model.read_bytes()

    # Alterar o conteúdo sem mudar o tamanho e restaurar o mtime original.
    replacement = bytes([original_bytes[0] ^ 1]) + original_bytes[1:]
    assert replacement != original_bytes
    assert len(replacement) == len(original_bytes)

    model.write_bytes(replacement)
    os.utime(
        model,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )

    current_stat = model.stat()
    assert current_stat.st_size == original_stat.st_size
    assert current_stat.st_mtime_ns == original_stat.st_mtime_ns

    # O perfil antigo não pode ser utilizado após a alteração do conteúdo.
    assert worker.profile(model.name) is None
def test_summary_rejects_unlabelled_rows_instead_of_guessing_generation():
    rows = [
        {"n_threads": 2, "avg_ts": 1000.0},
        {"n_threads": 4, "avg_ts": 20.0},
    ]
    assert c.summarize(rows) == []


def test_summary_rejects_prompt_only_rows():
    rows = [
        {"test": "pp32", "n_threads": 2, "avg_ts": 1000.0},
        {"test": "pp32", "n_threads": 4, "avg_ts": 1800.0},
    ]
    assert c.summarize(rows) == []


def test_file_identity_is_portable_and_content_sensitive(tmp_path):
    path = tmp_path / "model.gguf"
    path.write_bytes(b"first")
    first = c._file_info(path)
    path.write_bytes(b"other")
    second = c._file_info(path)
    assert first["path"] == second["path"] == "model.gguf"
    assert first["sha256"] != second["sha256"]
