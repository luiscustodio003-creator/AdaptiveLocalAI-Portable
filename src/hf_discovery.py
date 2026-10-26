"""Dynamic, cached discovery of small CPU-oriented text GGUFs from Hugging Face.

This module only discovers metadata and direct file URLs. It never downloads or runs a
remote model. Eligibility is still calculated locally by model_eligibility.py.
"""
from __future__ import annotations

import copy
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

USER_AGENT = "AdaptiveLocalAI-Portable/1.0"
CACHE_TTL_SECONDS = 1800
MAX_LIST_TIMEOUT = 3.0
MAX_TREE_TIMEOUT = 4.0
MAX_REPOSITORIES_TO_INSPECT = 12

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {
    "expires_at": 0.0,
    "repos": [],
    "error": None,
    "fetched_at": None,
    "repositories_checked": 0,
}

_EXCLUDED_TERMS = (
    "text-to-speech", "text to speech", "automatic-speech-recognition", "speech-to-text",
    "audio", "asr", "tts", "whisper", "stable-diffusion", "text-to-image",
    "image-generation", "image generation", "embedding", "reranker", "rerank",
    "classification", "classifier", "vision", "llava", "minicpm-v", "qwen3-vl",
    "mmproj", "diffusion", "music-generation", "music generation", "vocoder",
)
_ALLOWED_PIPELINES = {"text-generation", "text2text-generation", "conversational", "text-generation-inference"}
_QUANT_RANK = {
    "q4_k_m": 0, "q5_k_m": 1, "q4_k_s": 2, "q4_0": 3,
    "iq4_xs": 4, "q5_k_s": 5, "q6_k": 6, "q3_k_m": 7,
    "q3_k_s": 8, "q2_k": 9, "q8_0": 10, "q4_1": 11,
}


def _request_json(url: str, timeout: float) -> Any:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError("Resposta do Hugging Face excede o limite de 5 MB.")
    return json.loads(raw.decode("utf-8"))


def _is_text_repository(item: dict[str, Any]) -> bool:
    repo_id = str(item.get("id") or "").strip()
    if not repo_id or bool(item.get("private")) or bool(item.get("disabled")):
        return False
    pipeline = str(item.get("pipeline_tag") or "").strip().lower()
    if pipeline and pipeline not in _ALLOWED_PIPELINES:
        return False
    tags = item.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    haystack = " ".join([repo_id, pipeline, *(str(tag) for tag in tags)]).lower()
    if any(term in haystack for term in _EXCLUDED_TERMS):
        return False
    # The Hub query is filtered by the GGUF tag; retain name/tag checks as a guard.
    if "gguf" not in haystack:
        return False
    return True


def _quantization(file_name: str) -> tuple[str, int]:
    lowered = file_name.lower()
    for quant in sorted(_QUANT_RANK, key=len, reverse=True):
        if quant in lowered:
            return quant.upper(), _QUANT_RANK[quant]
    match = re.search(r"(?i)(f16|bf16|f32|q\d+_[a-z0-9]+|iq\d+_[a-z0-9]+)", file_name)
    if match:
        return match.group(1).upper(), 90
    return "nao identificada", 99


def _usable_gguf_files(tree: Any) -> list[dict[str, Any]]:
    if not isinstance(tree, list):
        return []
    found: list[dict[str, Any]] = []
    for row in tree:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or row.get("rfilename") or "")
        lowered = path.lower()
        if not lowered.endswith(".gguf"):
            continue
        if any(term in lowered for term in ("mmproj", "adapter", "lora", "imatrix", "tokenizer", "vocab", "draft")):
            continue
        if re.search(r"-\d{5}-of-\d{5}\.gguf$", lowered):
            # A shard is not a standalone model; do not link to just one part.
            continue
        size = row.get("size")
        if size is None and isinstance(row.get("lfs"), dict):
            size = row["lfs"].get("size")
        try:
            size_bytes = int(size)
        except (TypeError, ValueError, OverflowError):
            continue
        if size_bytes <= 0:
            continue
        quant, rank = _quantization(path)
        if rank == 99:
            # Keep a full-precision file only as a last-resort candidate; hardware filters it.
            rank = 100
        found.append({
            "path": path,
            "size_bytes": size_bytes,
            "oid": str(row.get("oid") or ""),
            "quantization": quant,
            "quant_rank": rank,
        })
    return found


def _size_gb(size_bytes: int) -> float:
    return int(size_bytes) / (1024 ** 3)


def _fits_known_budget(file_row: dict[str, Any], hardware: dict[str, Any]) -> bool:
    try:
        size_gb = _size_gb(int(file_row["size_bytes"]))
        context = max(512, min(int(hardware.get("context") or 2048), 32768))
        estimated_peak = 0.8 + size_gb * 1.6 + context * 0.00058
        total = float(hardware.get("total_ram_gb"))
        free = float(hardware.get("available_ram_gb"))
        disk = float(hardware.get("disk_free_gb"))
    except (TypeError, ValueError, OverflowError):
        return False
    return total >= max(4.0, estimated_peak + 1.5) and free >= estimated_peak + 1.0 and disk >= size_gb + 1.5


def _select_file(files: list[dict[str, Any]], hardware: dict[str, Any]) -> dict[str, Any] | None:
    if not files:
        return None
    fitting = [row for row in files if _fits_known_budget(row, hardware)]
    choices = fitting or files
    # Prefer a good quantization that fits; if none fit, choose the smallest file so the
    # ordinary eligibility engine can explain why it is blocked.
    if fitting:
        return dict(sorted(choices, key=lambda row: (int(row.get("quant_rank", 99)), int(row["size_bytes"])))[0])
    return dict(sorted(choices, key=lambda row: (int(row["size_bytes"]), int(row.get("quant_rank", 99))))[0])


def _list_url(search: str | None) -> str:
    params: list[tuple[str, str]] = [
        ("filter", "gguf"), ("sort", "downloads"), ("direction", "-1"), ("limit", "12"),
        ("expand[]", "sha"), ("expand[]", "pipeline_tag"), ("expand[]", "tags"),
        ("expand[]", "downloads"), ("expand[]", "likes"),
    ]
    if search:
        params.append(("search", search))
    return "https://huggingface.co/api/models?" + urlencode(params)


def _fetch_model_lists(timeout: float) -> tuple[list[dict[str, Any]], list[str]]:
    # Search small parameter classes as well as the general GGUF catalog. Popularity is
    # used to discover repositories, not to rank the final hardware-compatible choices.
    searches: list[str | None] = ["0.5B", "1B", "2B", "3B", None]
    urls = [_list_url(value) for value in searches]
    executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="hf-list")
    futures = {executor.submit(_request_json, url, timeout): url for url in urls}
    done, pending = wait(futures, timeout=3.5)
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    # Do not block the recommendations HTTP handler indefinitely on an unresponsive Hub.
    url_order = {url: index for index, url in enumerate(urls)}
    for future in sorted(done, key=lambda item: url_order.get(futures[item], 99)):
        try:
            payload = future.result()
            query_index = url_order.get(futures[future], len(searches) - 1)
            query_group = searches[query_index] or "__general__"
            if isinstance(payload, list):
                for row in payload:
                    if isinstance(row, dict):
                        enriched = dict(row)
                        enriched["_discovery_query"] = query_group
                        items.append(enriched)
        except Exception as exc:
            errors.append(str(exc)[:160])
    for future in pending:
        future.cancel()
    executor.shutdown(wait=False, cancel_futures=True)

    seen: set[str] = set()
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        repo_id = str(item.get("id") or "").strip()
        key = repo_id.lower()
        if key and key not in seen and _is_text_repository(item):
            seen.add(key)
            group = str(item.get("_discovery_query") or "__general__")
            groups.setdefault(group, []).append(item)

    # Round-robin small-model search buckets so one size query cannot fill the whole shortlist.
    ordered: list[dict[str, Any]] = []
    group_order = ["0.5B", "1B", "2B", "3B", "__general__"]
    while any(groups.values()):
        progressed = False
        for group in group_order:
            bucket = groups.get(group) or []
            if bucket:
                ordered.append(bucket.pop(0))
                progressed = True
        if not progressed:
            break
    return ordered, errors


def _fetch_repo_tree(repo: dict[str, Any], timeout: float) -> dict[str, Any] | None:
    repo_id = str(repo.get("id") or "").strip()
    if not repo_id:
        return None
    revision = str(repo.get("sha") or "main")
    path = quote(repo_id, safe="/")
    rev = quote(revision, safe="")
    url = f"https://huggingface.co/api/models/{path}/tree/{rev}?recursive=true&expand=true&limit=100"
    tree = _request_json(url, timeout)
    files = _usable_gguf_files(tree)
    if not files:
        return None
    # Keep the compact metadata needed to make a direct, revision-pinned file link.
    return {
        "repo_id": repo_id,
        "revision": revision,
        "downloads": int(repo.get("downloads") or 0),
        "likes": int(repo.get("likes") or 0),
        "pipeline_tag": repo.get("pipeline_tag"),
        "tags": repo.get("tags") if isinstance(repo.get("tags"), list) else [],
        "files": files,
    }


def _fetch_raw_repositories() -> tuple[list[dict[str, Any]], str | None, int]:
    models, list_errors = _fetch_model_lists(MAX_LIST_TIMEOUT)
    # Inspect at most 12 repositories; the Hub request is bounded and cached afterwards.
    models = models[:MAX_REPOSITORIES_TO_INSPECT]
    if not models:
        return [], "; ".join(list_errors)[:500] or "O Hugging Face nao devolveu repositorios GGUF de texto.", 0

    executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="hf-tree")
    futures = {executor.submit(_fetch_repo_tree, model, MAX_TREE_TIMEOUT): model for model in models}
    done, pending = wait(futures, timeout=4.5)
    repos: list[dict[str, Any]] = []
    errors = list(list_errors)
    for future in done:
        try:
            repo = future.result()
            if repo:
                repos.append(repo)
        except Exception as exc:
            errors.append(str(exc)[:160])
    for future in pending:
        future.cancel()
    executor.shutdown(wait=False, cancel_futures=True)
    error = "; ".join(errors)[:500] if errors and not repos else None
    return repos, error, len(models)


def _candidate_from_repo(repo: dict[str, Any], hardware: dict[str, Any]) -> dict[str, Any] | None:
    file_row = _select_file(repo.get("files", []), hardware)
    if not file_row:
        return None
    repo_id = str(repo["repo_id"])
    revision = str(repo.get("revision") or "main")
    path = str(file_row["path"])
    encoded_repo = quote(repo_id, safe="/")
    encoded_path = quote(path, safe="/")
    encoded_revision = quote(revision, safe="")
    size_bytes = int(file_row["size_bytes"])
    parameter_match = re.search(r"(?i)(\d+(?:\.\d+)?\s*[bm])", repo_id + " " + path)
    return {
        "id": f"hf:{repo_id}:{path}",
        "task": "text",
        "name": f"{repo_id} — {path}",
        "repo_id": repo_id,
        "file_name": path.rsplit("/", 1)[-1],
        "file_path": path,
        "file_size_mb": round(size_bytes / 1_000_000, 1),
        "file_size_bytes": size_bytes,
        "estimated_size_gb": round(_size_gb(size_bytes), 3),
        "model_url": f"https://huggingface.co/{encoded_repo}",
        "file_url": f"https://huggingface.co/{encoded_repo}/resolve/{encoded_revision}/{encoded_path}",
        "file_sha256": None,
        "file_oid": file_row.get("oid"),
        "repo_revision": revision,
        "downloads": int(repo.get("downloads") or 0),
        "likes": int(repo.get("likes") or 0),
        "runtime": "llama.cpp",
        "parameters": parameter_match.group(1).replace(" ", "") if parameter_match else "nao indicado",
        "quantization": str(file_row.get("quantization") or "nao identificada"),
        "languages": ["validar idiomas e qualidade localmente"],
        "min_total_ram_gb": 4.0,
        "disk_reserve_gb": 1.5,
        "summary": "Descoberto dinamicamente no Hugging Face; elegibilidade calculada localmente por RAM, disco e runtime.",
        "source_kind": "huggingface_dynamic",
    }


def discover_text_gguf_candidates(
    *,
    total_ram_gb: float | None = None,
    available_ram_gb: float | None = None,
    disk_free_gb: float | None = None,
    context: int = 2048,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return locally filtered candidates and cache/discovery status; never download files."""
    now = time.monotonic()
    with _CACHE_LOCK:
        cache_valid = bool(_CACHE["expires_at"] > now and _CACHE["fetched_at"] is not None)
        if not force_refresh and cache_valid:
            raw_repos = copy.deepcopy(_CACHE["repos"])
            cache_error = _CACHE.get("error")
            fetched_at = _CACHE.get("fetched_at")
            checked = int(_CACHE.get("repositories_checked") or 0)
            was_cached = True
        else:
            raw_repos = []
            cache_error = None
            fetched_at = None
            checked = 0
            was_cached = False

    if not was_cached:
        try:
            new_repos, error, checked_count = _fetch_raw_repositories()
        except Exception as exc:
            new_repos, error, checked_count = [], str(exc)[:500], 0
        with _CACHE_LOCK:
            _CACHE.update(
                expires_at=time.monotonic() + CACHE_TTL_SECONDS,
                repos=copy.deepcopy(new_repos),
                error=error,
                fetched_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                repositories_checked=checked_count,
            )
            raw_repos = copy.deepcopy(new_repos)
            cache_error = error
            fetched_at = _CACHE["fetched_at"]
            checked = checked_count

    hardware = {
        "total_ram_gb": total_ram_gb,
        "available_ram_gb": available_ram_gb,
        "disk_free_gb": disk_free_gb,
        "context": context,
    }
    candidates = []
    for repo in raw_repos:
        candidate = _candidate_from_repo(repo, hardware)
        if candidate:
            candidates.append(candidate)

    # Output shortlist is bounded and sorted for compact model files first, not download count.
    candidates.sort(key=lambda item: (int(item.get("file_size_bytes") or 0), str(item.get("name") or "").lower()))
    candidates = candidates[:12]
    if raw_repos:
        state = "ready"
    elif cache_error:
        state = "degraded"
    else:
        state = "empty"
    return {
        "state": state,
        "source": "Hugging Face Hub API",
        "cached": was_cached,
        "fetched_at": fetched_at,
        "repositories_checked": checked,
        "candidates_found": len(candidates),
        "error": cache_error,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "ranking": "memory/disk/runtime eligibility first; download count is only a discovery signal",
        "candidates": candidates,
    }