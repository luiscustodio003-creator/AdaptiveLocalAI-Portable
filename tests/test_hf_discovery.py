from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import hf_discovery as hd
import model_eligibility as me


def test_text_repo_filter_excludes_audio_vision_and_allows_gguf_text():
    assert hd._is_text_repository({"id": "org/tiny-1b-GGUF", "tags": ["gguf"], "pipeline_tag": "text-generation"})
    assert not hd._is_text_repository({"id": "org/voice-gguf", "tags": ["gguf", "text-to-speech"]})
    assert not hd._is_text_repository({"id": "org/model-gguf", "tags": ["gguf"], "pipeline_tag": "text-to-image"})


def test_variant_selection_prefers_good_quant_that_fits_hardware():
    files = [
        {"path": "model-Q8_0.gguf", "size_bytes": 1_600_000_000, "oid": "b", "quantization": "Q8_0", "quant_rank": 10},
        {"path": "model-Q4_K_M.gguf", "size_bytes": 700_000_000, "oid": "a", "quantization": "Q4_K_M", "quant_rank": 0},
    ]
    hw = {"total_ram_gb": 15.9, "available_ram_gb": 7.0, "disk_free_gb": 24, "context": 2048}
    assert hd._select_file(files, hw)["path"] == "model-Q4_K_M.gguf"


def test_variant_selection_falls_back_to_smallest_if_none_fit():
    files = [
        {"path": "model-Q8_0.gguf", "size_bytes": 5_000_000_000, "quantization": "Q8_0", "quant_rank": 10},
        {"path": "model-Q4_K_M.gguf", "size_bytes": 3_500_000_000, "quantization": "Q4_K_M", "quant_rank": 0},
    ]
    hw = {"total_ram_gb": 8, "available_ram_gb": 1.5, "disk_free_gb": 24, "context": 2048}
    assert hd._select_file(files, hw)["path"] == "model-Q4_K_M.gguf"


def test_tree_parser_ignores_shards_and_non_model_files():
    rows = [
        {"path": "model-Q4_K_M.gguf", "size": 700_000_000, "oid": "a"},
        {"path": "model-00001-of-00002.gguf", "size": 900_000_000, "oid": "b"},
        {"path": "mmproj-model-f16.gguf", "size": 100_000_000, "oid": "c"},
        {"path": "README.md", "size": 1000, "oid": "d"},
    ]
    out = hd._usable_gguf_files(rows)
    assert [row["path"] for row in out] == ["model-Q4_K_M.gguf"]


def test_dynamic_discovery_returns_revision_pinned_file_and_caches(monkeypatch):
    hd._CACHE.update(expires_at=0.0, repos=[], error=None, fetched_at=None, repositories_checked=0)
    calls = []

    def fake_request(url, timeout):
        calls.append(url)
        if "/tree/" in url:
            return [
                {"path": "tiny.Q4_K_M.gguf", "size": 700_000_000, "oid": "blob-a"},
                {"path": "tiny.Q8_0.gguf", "size": 1_600_000_000, "oid": "blob-b"},
            ]
        return [{
            "id": "org/tiny-1b-GGUF", "pipeline_tag": "text-generation",
            "tags": ["gguf"], "downloads": 22, "likes": 4, "sha": "revision123",
        }]

    monkeypatch.setattr(hd, "_request_json", fake_request)
    first = hd.discover_text_gguf_candidates(
        total_ram_gb=15.9, available_ram_gb=7.0, disk_free_gb=24, context=2048, force_refresh=True,
    )
    assert first["state"] == "ready"
    assert first["candidates_found"] == 1
    candidate = first["candidates"][0]
    assert candidate["file_name"] == "tiny.Q4_K_M.gguf"
    assert "/resolve/revision123/" in candidate["file_url"]
    call_count = len(calls)

    second = hd.discover_text_gguf_candidates(
        total_ram_gb=15.9, available_ram_gb=6.0, disk_free_gb=24, context=2048,
    )
    assert second["cached"] is True
    assert len(calls) == call_count


def test_dynamic_candidate_is_filtered_by_existing_hardware_policy(tmp_path):
    hw = {"total_ram_gb": 15.86, "available_ram_gb": 7.2, "cpu_threads": 8, "disk_free_gb": 24, "context": 2048, "active_model": None}
    dynamic = {
        "id": "hf:org/tiny-0.5b-gguf:tiny.Q4_K_M.gguf",
        "task": "text", "name": "org/tiny-0.5b-gguf â€” tiny.Q4_K_M.gguf",
        "repo_id": "org/tiny-0.5b-gguf", "file_name": "tiny.Q4_K_M.gguf",
        "file_size_mb": 700.0, "file_size_bytes": 700_000_000, "estimated_size_gb": 0.652,
        "model_url": "https://huggingface.co/org/tiny-0.5b-gguf",
        "file_url": "https://huggingface.co/org/tiny-0.5b-gguf/resolve/abc/tiny.Q4_K_M.gguf",
        "runtime": "llama.cpp", "parameters": "0.5B", "quantization": "Q4_K_M",
        "languages": ["validate locally"], "min_total_ram_gb": 4.0, "disk_reserve_gb": 1.5,
        "summary": "dynamic fixture", "source_kind": "huggingface_dynamic", "downloads": 1,
    }
    result = me.build_recommendations(tmp_path, "text", [], hw, {}, {"llama.cpp": True}, remote_candidates=[dynamic])
    matches = [item for item in result["eligible_candidates"] if item.get("repo_id") == "org/tiny-0.5b-gguf"]
    assert len(matches) == 1
    assert matches[0]["eligible"] is True
    assert "_sort_score" not in str(result)


def test_dynamic_candidate_is_blocked_when_local_ram_is_too_low(tmp_path):
    hw = {"total_ram_gb": 8.0, "available_ram_gb": 1.0, "cpu_threads": 8, "disk_free_gb": 24, "context": 2048, "active_model": None}
    dynamic = {
        "id": "hf:org/tiny:tiny.Q4_K_M.gguf", "task": "text", "name": "org/tiny â€” tiny.Q4_K_M.gguf",
        "repo_id": "org/tiny", "file_name": "tiny.Q4_K_M.gguf", "file_size_mb": 700.0,
        "file_size_bytes": 700_000_000, "estimated_size_gb": 0.652,
        "model_url": "https://huggingface.co/org/tiny", "file_url": "https://huggingface.co/org/tiny/resolve/abc/tiny.Q4_K_M.gguf",
        "runtime": "llama.cpp", "parameters": "0.5B", "quantization": "Q4_K_M", "languages": [],
        "min_total_ram_gb": 4.0, "disk_reserve_gb": 1.5, "summary": "fixture", "source_kind": "huggingface_dynamic",
    }
    result = me.build_recommendations(tmp_path, "text", [], hw, {}, {"llama.cpp": True}, remote_candidates=[dynamic])
    assert result["recommended"] is None
    assert result["blocked_candidates"]