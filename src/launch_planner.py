"""Conservative launch planning; hardware facts never imply unsupported backends."""
from __future__ import annotations

from typing import Any


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def launch_plan(hardware: dict[str, Any], model: dict[str, Any] | str,
                *, requested_context: int | None = None,
                available_backends: list[str] | None = None) -> dict[str, Any]:
    """Produce a conservative CPU-first plan until a GPU backend is verified."""
    logical = max(1, int(hardware.get("logical_threads") or 1))
    physical = hardware.get("physical_cores")
    threads = max(1, min(logical, int(physical))) if physical else max(1, logical // 2)
    mem_available = hardware.get("memory_available_bytes")
    model_bytes = model.get("size_bytes") if isinstance(model, dict) else None
    # Reserve the OS and runtime memory; do not assume the model file size equals RAM use.
    context = 2048
    reason_context = "contexto conservador por defeito"
    if isinstance(mem_available, (int, float)) and isinstance(model_bytes, (int, float)):
        headroom = int(mem_available - model_bytes * 1.35 - 1024 ** 3)
        if headroom >= 1024 ** 3:
            context = _clamp(int(headroom / (64 * 1024)), 2048, 16384)
            reason_context = "contexto limitado pelo orçamento estimado de memória"
    if requested_context is not None:
        context = _clamp(int(requested_context), 2048, 16384)
        reason_context = "contexto explicitamente solicitado, limitado ao intervalo suportado"
    backends = available_backends or ["cpu"]
    backend = "cpu" if "cpu" in backends else backends[0]
    gpu_layers = 0
    why = [f"{threads} threads iniciais", reason_context,
           f"backend {backend}; GPU só será usada após deteção e compatibilidade confirmadas"]
    return {
        "threads": threads, "context": context, "backend": backend,
        "gpu_layers": gpu_layers, "thread_batch": threads,
        "flash_attention": False, "why": why,
    }
