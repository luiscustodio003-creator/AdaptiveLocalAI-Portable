from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import model_eligibility as me


HW = {
    "total_ram_gb": 15.86,
    "available_ram_gb": 7.2,
    "cpu_threads": 8,
    "disk_free_gb": 24,
    "context": 2048,
    "active_model": "gemma-3-1b-it-Q4_K_M.gguf",
}
RUNTIMES = {"llama.cpp": True, "audio.cpp_integrated": False}


def test_normalize_task_aliases_and_rejects_unknown():
    assert me.normalize_task("text-to-speech") == "tts"
    assert me.normalize_task("chat") == "text"
    with pytest.raises(ValueError):
        me.normalize_task("flight-control")


def test_estimate_ram_grows_with_model_size():
    small = me.estimate_peak_ram_gb(500_000_000, 2048)
    large = me.estimate_peak_ram_gb(2_000_000_000, 2048)
    assert large > small


def test_current_calibrated_model_ranks_before_remote_candidate(tmp_path):
    installed = [{
        "name": "gemma-3-1b-it-Q4_K_M.gguf", "category": "text", "size_bytes": 806_058_240,
    }]
    profiles = {
        "gemma-3-1b-it-Q4_K_M.gguf": {
            "threads": 3, "generation_tok_s": 46.57, "stale": False,
            "validation": {"status": "not_run", "passed": False},
        }
    }
    result = me.build_recommendations(tmp_path, "text", installed, HW, profiles, RUNTIMES)
    assert result["recommended"]["name"] == "gemma-3-1b-it-Q4_K_M.gguf"
    assert result["recommended"]["calibration"]["threads"] == 3
    assert result["recommended"]["eligible"] is True
    assert any(item["id"] == "qwen2.5-0.5b-instruct-q4km" for item in result["eligible_candidates"])


def test_remote_text_candidate_is_blocked_when_ram_too_low(tmp_path):
    hardware = dict(HW, total_ram_gb=4.0, available_ram_gb=1.0)
    result = me.build_recommendations(tmp_path, "text", [], hardware, {}, RUNTIMES)
    assert result["recommended"] is None
    candidate = next(item for item in result["blocked_candidates"] if item["id"] == "qwen2.5-0.5b-instruct-q4km")
    assert candidate["eligible"] is False
    assert any("RAM" in reason for reason in candidate["reasons"])


def test_text_remote_candidate_requires_llama_runtime(tmp_path):
    result = me.build_recommendations(tmp_path, "text", [], HW, {}, {"llama.cpp": False})
    candidate = next(item for item in result["blocked_candidates"] if item["id"] == "qwen2.5-0.5b-instruct-q4km")
    assert candidate["eligible"] is False
    assert any("llama.cpp" in reason for reason in candidate["reasons"])


def test_tts_is_blocked_until_audio_runtime_is_integrated(tmp_path):
    result = me.build_recommendations(tmp_path, "tts", [], HW, {}, RUNTIMES)
    assert result["recommended"] is None
    candidate = next(item for item in result["blocked_candidates"] if item["id"] == "pockettts-portuguese-q8")
    assert candidate["eligible"] is False
    assert "audio.cpp" in " ".join(candidate["reasons"])
    assert candidate["file_url"].endswith("pocket-tts-portuguese-q8_0.gguf")


def test_asr_is_blocked_until_audio_runtime_is_integrated(tmp_path):
    result = me.build_recommendations(tmp_path, "asr", [], HW, {}, RUNTIMES)
    candidate = next(item for item in result["blocked_candidates"] if item["id"] == "qwen3-asr-0.6b-q8")
    assert not result["eligible_candidates"]
    assert candidate["eligible"] is False


def test_vision_model_is_not_advertised_as_eligible_until_mmproj_support(tmp_path):
    installed = [{
        "name": "Qwen3VL-2B-Instruct-Q4_K_M.gguf", "category": "vision", "size_bytes": 1_056_000_000,
        "dependency": "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf",
    }]
    result = me.build_recommendations(tmp_path, "vision", installed, HW, {}, RUNTIMES)
    assert result["recommended"] is None
    assert result["blocked_candidates"][0]["eligible"] is False
    assert "mmproj" in " ".join(result["blocked_candidates"][0]["reasons"])


def test_image_generation_is_explicitly_unsupported(tmp_path):
    result = me.build_recommendations(tmp_path, "image_generation", [], HW, {}, RUNTIMES)
    assert result["recommended"] is None
    assert result["eligible_candidates"] == []
    assert "runtime" in result["message"]


def test_api_payload_does_not_include_private_sort_fields(tmp_path):
    result = me.build_recommendations(tmp_path, "text", [], HW, {}, RUNTIMES)
    assert "_sort_score" not in str(result)
