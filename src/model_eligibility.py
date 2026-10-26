"""Hardware-aware shortlist for models that are safe to consider in AdaptiveLocalAI.

The catalog is intentionally curated: model popularity is not a compatibility signal.
Only llama.cpp text models are loadable by the current app. Audio models are listed as
blocked references until an audio.cpp runtime and app integration are present. Resource
figures are conservative estimates; only the calibration engine can provide measured data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

TASKS: dict[str, str] = {
    "text": "Geração de texto / chat",
    "vision": "Compreensão de imagens",
    "tts": "Texto para fala (TTS)",
    "asr": "Reconhecimento de fala (ASR)",
    "image_generation": "Geração de imagens",
}

_ALIASES = {
    "chat": "text", "llm": "text", "text_generation": "text", "text-generation": "text", "text-to-text": "text",
    "image": "image_generation", "image-generation": "image_generation", "text-to-image": "image_generation", "txt2img": "image_generation",
    "speech": "tts", "text-to-speech": "tts", "speech_synthesis": "tts", "speech-synthesis": "tts",
    "speech-to-text": "asr", "stt": "asr", "transcription": "asr",
    "multimodal": "vision", "image-understanding": "vision",
}

# Exact file-level references checked against the upstream repository on 2026-10-23.
# The browser downloads the selected file; this endpoint does not yet install it into models/.
_REMOTE_MODELS: tuple[dict[str, Any], ...] = (
    {
        "id": "qwen2.5-0.5b-instruct-q4km",
        "task": "text",
        "name": "Qwen2.5 0.5B Instruct — Q4_K_M",
        "repo_id": "Qwen/Qwen2.5-0.5B-Instruct-GGUF",
        "file_name": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "file_size_mb": 491,
        "estimated_size_gb": 0.50,
        "model_url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/blob/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "file_url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "file_sha256": "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
        "runtime": "llama.cpp",
        "parameters": "0.5B",
        "quantization": "Q4_K_M",
        "languages": ["multilingual; validate Portuguese (Portugal) quality locally"],
        "min_total_ram_gb": 4.0,
        "disk_reserve_gb": 1.5,
        "summary": "Alternativa remota compacta para texto, com ficheiro GGUF Q4_K_M de cerca de 491 MB.",
        "source_kind": "curated_remote",
    },
    {
        "id": "pockettts-portuguese-q8",
        "task": "tts",
        "name": "PocketTTS — variante portuguesa Q8_0",
        "repo_id": "audio-cpp/audio.cpp-gguf",
        "file_name": "pocket-tts-portuguese-q8_0.gguf",
        "file_size_mb": 128,
        "estimated_size_gb": 0.13,
        "model_url": "https://huggingface.co/audio-cpp/audio.cpp-gguf/tree/main/PocketTTS-GGUF/portuguese",
        "file_url": "https://huggingface.co/audio-cpp/audio.cpp-gguf/resolve/main/PocketTTS-GGUF/portuguese/pocket-tts-portuguese-q8_0.gguf",
        "file_sha256": None,
        "runtime": "audio.cpp",
        "parameters": "PocketTTS",
        "quantization": "Q8_0",
        "languages": ["Português; variante PT-PT não confirmada"],
        "min_total_ram_gb": None,
        "disk_reserve_gb": 1.0,
        "summary": "Referência de modelo de TTS com variante portuguesa; poderá necessitar dos assets de embeddings do pacote.",
        "source_kind": "curated_remote",
        "runtime_block_reason": "A aplicação integra atualmente llama.cpp, não audio.cpp. Este ficheiro não é carregável pelo llama-server atual; não descarregar como modelo utilizável até integrar e testar o runtime de áudio.",
        "resource_status": "unknown_until_audio_runtime_benchmark",
    },
    {
        "id": "qwen3-asr-0.6b-q8",
        "task": "asr",
        "name": "Qwen3-ASR 0.6B — Q8_0 (audio.cpp)",
        "repo_id": "audio-cpp/audio.cpp-gguf",
        "file_name": "qwen3-asr-0.6b-q8_0.gguf",
        "file_size_mb": 1150,
        "estimated_size_gb": 1.15,
        "model_url": "https://huggingface.co/audio-cpp/audio.cpp-gguf/blob/main/Qwen3-ASR-0.6B-GGUF/qwen3-asr-0.6b-q8_0.gguf",
        "file_url": "https://huggingface.co/audio-cpp/audio.cpp-gguf/resolve/main/Qwen3-ASR-0.6B-GGUF/qwen3-asr-0.6b-q8_0.gguf",
        "file_sha256": None,
        "runtime": "audio.cpp",
        "parameters": "0.6B",
        "quantization": "Q8_0",
        "languages": ["multilingual; verificar suporte e qualidade de português"],
        "min_total_ram_gb": None,
        "disk_reserve_gb": 2.0,
        "summary": "Modelo de referência para reconhecimento de fala, mas requer o runtime audio.cpp.",
        "source_kind": "curated_remote",
        "runtime_block_reason": "A aplicação ainda não integra audio.cpp nem a pipeline de áudio; o modelo não é executável pelo runtime atual.",
        "resource_status": "unknown_until_audio_runtime_benchmark",
    },
)


def normalize_task(task: str | None) -> str:
    value = str(task or "text").strip().lower().replace("_", "-")
    value = _ALIASES.get(value, value)
    if value not in TASKS:
        raise ValueError(f"Tarefa desconhecida: {value}. Tarefas suportadas: {', '.join(TASKS)}")
    return value


def estimate_peak_ram_gb(size_bytes: int, context: int = 2048) -> float:
    """Conservative estimate for llama.cpp text GGUFs, not a measured guarantee."""
    size_gb = max(0, int(size_bytes)) / (1024 ** 3)
    context = max(512, min(int(context or 2048), 32768))
    kv_estimate = context * 0.00058
    return round(0.8 + (size_gb * 1.6) + kv_estimate, 2)


def _number(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        return result if result >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _candidate_check(candidate: dict[str, Any], hardware: dict[str, Any], runtimes: dict[str, Any], *, remote: bool) -> dict[str, Any]:
    item = dict(candidate)
    reasons: list[str] = []
    runtime = str(item.get("runtime") or "")
    total_ram = _number(hardware.get("total_ram_gb"))
    free_ram = _number(hardware.get("available_ram_gb"))
    disk_free = _number(hardware.get("disk_free_gb"))
    context = int(hardware.get("context") or 2048)

    item["eligible"] = False
    item["eligibility_state"] = "blocked"
    item["estimated_peak_ram_gb"] = None
    item["required_free_ram_gb"] = None
    item["reasons"] = reasons

    if runtime == "llama.cpp":
        if not runtimes.get("llama.cpp", False):
            reasons.append("O runtime llama.cpp não foi encontrado no projeto.")
    elif runtime == "audio.cpp":
        # Runtime availability alone is insufficient: app integration is deliberately required.
        if not runtimes.get("audio.cpp_integrated", False):
            reasons.append(str(item.get("runtime_block_reason") or "Runtime audio.cpp não integrado na aplicação."))
    else:
        reasons.append(f"Runtime não suportado pela aplicação: {runtime or 'não especificado'}.")

    if remote and disk_free is not None:
        need_disk = float(item.get("estimated_size_gb") or 0) + float(item.get("disk_reserve_gb") or 1.0)
        if disk_free < need_disk:
            reasons.append(f"Espaço livre insuficiente: necessita de cerca de {need_disk:.1f} GB livres; disponíveis {disk_free:.1f} GB.")

    if runtime == "llama.cpp" and item.get("file_size_bytes") is not None:
        peak = estimate_peak_ram_gb(int(item["file_size_bytes"]), context)
        item["estimated_peak_ram_gb"] = peak
        item["required_free_ram_gb"] = round(peak + 1.0, 2)
        min_total = max(float(item.get("min_total_ram_gb") or 0), peak + 1.5)
        if total_ram is None:
            reasons.append("Não foi possível determinar a RAM total; não é seguro confirmar a elegibilidade.")
        elif total_ram < min_total:
            reasons.append(f"RAM total estimada abaixo do necessário: cerca de {min_total:.1f} GB; disponíveis {total_ram:.1f} GB.")
        if free_ram is None:
            reasons.append("Não foi possível determinar a RAM livre.")
        elif free_ram < peak + 1.0:
            reasons.append(f"RAM livre insuficiente: exige cerca de {peak + 1.0:.1f} GB incluindo margem; disponíveis {free_ram:.1f} GB.")
    elif runtime == "audio.cpp":
        item["estimated_peak_ram_gb"] = None
        item["required_free_ram_gb"] = None
        if item.get("resource_status"):
            reasons.append("Consumo de memória ainda não medido neste hardware e com o runtime necessário.")

    if runtime == "llama.cpp" and not reasons:
        item["eligible"] = True
        item["eligibility_state"] = "eligible"
        item["reasons"] = [str(item.get("summary") or "Compatível com o runtime e com a estimativa de recursos atuais.")]
    elif not reasons:
        reasons.append("A elegibilidade técnica ainda não foi comprovada com medições reais.")
    item["reasons"] = reasons
    item["download_action"] = "browser_direct_file" if remote and item["eligible"] else "blocked_or_installed"
    return item


def build_recommendations(
    root: str | Path,
    task: str,
    installed_models: Iterable[dict[str, Any]],
    hardware: dict[str, Any],
    profiles: dict[str, dict[str, Any]],
    runtimes: dict[str, Any],
    remote_candidates: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return eligible candidates first, and explain blocked candidates explicitly."""
    normalized = normalize_task(task)
    # root is accepted for a stable call contract; installed sizes arrive from discover_models().
    Path(root)  # validate/coerce the project-root argument without accessing the filesystem
    eligible: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    installed_names: set[str] = set()
    context = int(hardware.get("context") or 2048)

    for entry in installed_models:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        if not name:
            continue
        installed_names.add(name.lower())
        category = str(entry.get("category") or "text").lower()
        if normalized == "text" and category == "text":
            size_bytes = int(entry.get("size_bytes") or 0)
            profile = profiles.get(name) if isinstance(profiles, dict) else None
            profile_ok = isinstance(profile, dict) and not bool(profile.get("stale", False))
            calibrated = profile_ok and isinstance(profile.get("threads"), (int, float))
            active = Path(str(hardware.get("active_model") or "")).name.lower() == name.lower()
            item = {
                "id": f"installed:{name}", "name": name, "task": normalized,
                "source_kind": "installed", "installed": True,
                "file_name": name, "file_size_mb": round(size_bytes / 1_000_000, 1),
                "file_size_bytes": size_bytes, "runtime": "llama.cpp",
                "model_url": None, "file_url": None, "quantization": "inferida do nome/ficheiro",
                "summary": "Já instalado localmente; não precisa de download.",
                "active": active,
                "calibrated": bool(calibrated),
                "calibration": {
                    "threads": profile.get("threads") if profile_ok else None,
                    "generation_tok_s": profile.get("generation_tok_s") if profile_ok else None,
                    "stale": bool(profile.get("stale", False)) if profile else None,
                    "validation_status": (profile.get("validation") or {}).get("status", "not_run") if profile_ok else "not_run",
                    "validation_passed": bool((profile.get("validation") or {}).get("passed", False)) if profile_ok else False,
                },
                "min_total_ram_gb": 4.0,
                "disk_reserve_gb": 0.0,
            }
            item = _candidate_check(item, hardware, runtimes, remote=False)
            # Existing active model is proven loadable. It still needs a small emergency margin.
            if active and runtimes.get("llama.cpp", False) and (_number(hardware.get("available_ram_gb")) or 0) >= 1.0:
                item["eligible"] = True
                item["eligibility_state"] = "eligible"
                item["reasons"] = ["Modelo já ativo nesta aplicação; a elegibilidade de execução está confirmada neste momento."]
            item["_sort_score"] = (100 if active else 80 if calibrated else 60)
            if item["eligible"]:
                eligible.append(item)
            else:
                blocked.append(item)
        elif normalized == "vision" and category == "vision":
            dep = entry.get("dependency")
            blocked.append({
                "id": f"installed:{name}", "name": name, "task": normalized,
                "source_kind": "installed", "installed": True, "eligible": False,
                "eligibility_state": "blocked", "runtime": "llama.cpp",
                "model_url": None, "file_url": None, "file_size_mb": round(int(entry.get("size_bytes") or 0) / 1_000_000, 1),
                "reasons": ["O carregador atual ainda não passa o mmproj ao llama-server nem valida um pedido com imagem; não é seguro classificá-lo como modelo de visão elegível." + (f" Dependência detectada: {dep}." if dep else " Falta confirmar a dependência mmproj necessária.")],
                "_sort_score": 0,
            })

    remote_pool = list(_REMOTE_MODELS)
    if remote_candidates is not None:
        known_remote = {
            (str(entry.get("repo_id") or "").lower(), str(entry.get("file_name") or "").lower())
            for entry in remote_pool
        }
        for candidate in remote_candidates:
            if not isinstance(candidate, dict):
                continue
            key = (str(candidate.get("repo_id") or "").lower(), str(candidate.get("file_name") or "").lower())
            if key not in known_remote:
                remote_pool.append(dict(candidate))
                known_remote.add(key)

    for entry in remote_pool:
        if entry["task"] != normalized:
            continue
        if str(entry.get("file_name") or "").lower() in installed_names:
            continue
        item = dict(entry)
        item["installed"] = False
        item["file_size_bytes"] = int(float(item.get("file_size_mb") or 0) * 1_000_000)
        item = _candidate_check(item, hardware, runtimes, remote=True)
        item["_sort_score"] = 40 if item["eligible"] else 0
        if item["eligible"]:
            eligible.append(item)
        else:
            blocked.append(item)

    # Do not return Python-only/internal sort fields to the browser.
    for model in blocked:
        model.pop("_sort_score", None)
    eligible.sort(key=lambda model: (-int(model.pop("_sort_score", 0)), float(model.get("file_size_mb") or 0)))
    blocked.sort(key=lambda model: (str(model.get("name") or "").lower()))

    if normalized == "vision":
        message = "Não há ainda um modelo de visão totalmente integrado e validado no carregador atual." if not eligible else "Modelos de visão elegíveis para o hardware atual."
    elif normalized in {"tts", "asr"}:
        message = "O hardware é apenas uma parte da decisão: falta integrar e validar audio.cpp na aplicação. Os candidatos bloqueados são referências diretas, não recomendações para descarregar agora."
    elif normalized == "image_generation":
        message = "A aplicação atual não possui um runtime de geração de imagens integrado; por isso não recomenda downloads de modelos de imagem sem suporte de execução."
    elif eligible:
        message = "Ordenado por compatibilidade com o hardware e evidência local; não por popularidade do repositório. As necessidades de RAM são estimativas conservadoras, não garantias."
    else:
        message = "Não foi encontrado um candidato comprovadamente elegível com os recursos e runtimes atuais."

    recommended = eligible[0] if eligible else None
    summary_keys = ("total_ram_gb", "available_ram_gb", "cpu_threads", "disk_free_gb", "context", "active_model")
    hw_summary = {key: hardware.get(key) for key in summary_keys}
    return {
        "ok": True,
        "task": normalized,
        "task_label": TASKS[normalized],
        "hardware": hw_summary,
        "runtimes": dict(runtimes),
        "recommended": recommended,
        "eligible_candidates": eligible,
        "blocked_candidates": blocked,
        "counts": {"eligible": len(eligible), "blocked": len(blocked)},
        "message": message,
        "policy": "Hardware + runtime + task compatibility first; no popularity-only ranking.",
        "download_note": "Os links abrem o ficheiro direto no navegador. A instalação gerida na pasta models/ ainda não está implementada; só um ficheiro concluído em models/ ativa o watcher atual.",
    }
