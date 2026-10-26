"""Adaptive context budgeting and hierarchical long-input processing.

The module is runtime-agnostic: model calls and UI event delivery are injected by
app.py. It deliberately uses a conservative character/token estimate because
llama.cpp tokenizers are not exposed through a stable local API in this app.
"""
from __future__ import annotations

import math
import re
import time
from typing import Any, Callable, Iterable

DEFAULT_CONTEXT_TOKENS = 2048
DEFAULT_OUTPUT_TOKENS = 512
CONTEXT_SAFETY_MARGIN = 160
CHUNK_OUTPUT_TOKENS = 190
REDUCE_OUTPUT_TOKENS = 170
FINAL_NOTES_TOKEN_BUDGET = 500


def estimate_tokens(value: Any) -> int:
    """Conservative token estimate; deliberately errs on the safe side."""
    text = value if isinstance(value, str) else str(value or "")
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 3.0))


def estimate_messages_tokens(messages: Iterable[dict[str, Any]], system_prompt: str = "") -> int:
    total = estimate_tokens(system_prompt) + 8
    for message in messages:
        if not isinstance(message, dict):
            continue
        total += estimate_tokens(message.get("content", "")) + 8
    return total


def latest_user_index(messages: list[dict[str, Any]]) -> int:
    for index in range(len(messages) - 1, -1, -1):
        item = messages[index]
        if isinstance(item, dict) and item.get("role") == "user":
            return index
    return -1


def should_chunk_latest_user(
    messages: list[dict[str, Any]],
    context_tokens: int = DEFAULT_CONTEXT_TOKENS,
    system_prompt: str = "",
    max_output_tokens: int = DEFAULT_OUTPUT_TOKENS,
) -> bool:
    """Chunk only when the latest user submission itself cannot safely fit.

    Old history is compacted separately, so a previous long message does not
    unnecessarily force a short current question into document-analysis mode.
    """
    index = latest_user_index(messages)
    if index < 0:
        return False
    content = messages[index].get("content", "")
    if not isinstance(content, str):
        content = str(content or "")
    input_budget = max(128, int(context_tokens) - int(max_output_tokens) - CONTEXT_SAFETY_MARGIN)
    latest_cost = estimate_tokens(content) + estimate_tokens(system_prompt) + 48
    return latest_cost > input_budget


def fit_recent_history(
    messages: list[dict[str, Any]],
    context_tokens: int = DEFAULT_CONTEXT_TOKENS,
    system_prompt: str = "",
    max_output_tokens: int = DEFAULT_OUTPUT_TOKENS,
) -> list[dict[str, str]]:
    """Keep a recent suffix of conversation that fits the input-token budget."""
    budget = max(128, int(context_tokens) - int(max_output_tokens) - CONTEXT_SAFETY_MARGIN)
    used = estimate_tokens(system_prompt) + 8
    selected: list[dict[str, str]] = []
    for message in reversed(messages or []):
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant", "system"}:
            continue
        content = message.get("content", "")
        if not isinstance(content, str):
            content = str(content or "")
        cost = estimate_tokens(content) + 8
        if used + cost > budget:
            # Stop rather than leapfrog an oversized earlier message and break
            # the chronology of the surviving conversation suffix.
            break
        selected.append({"role": str(message["role"]), "content": content})
        used += cost
    selected.reverse()
    return selected


def split_text(text: str, max_chars: int) -> list[str]:
    """Split text near paragraph/line/sentence/word boundaries without loss."""
    if not text:
        return [""]
    max_chars = max(200, int(max_chars))
    chunks: list[str] = []
    start = 0
    length = len(text)
    while start < length:
        hard_end = min(start + max_chars, length)
        if hard_end == length:
            end = length
        else:
            lower_bound = start + int(max_chars * 0.55)
            search_region = text[lower_bound:hard_end]
            choices = [
                (search_region.rfind("\n\n"), 2),
                (search_region.rfind("\n"), 1),
                (search_region.rfind(". "), 2),
                (search_region.rfind("; "), 2),
                (search_region.rfind(" "), 1),
            ]
            valid = [(position, width) for position, width in choices if position >= 0]
            if valid:
                # Prefer the strongest structural boundary, unless it is too
                # early; the lower_bound already protects against tiny chunks.
                position, width = max(valid, key=lambda item: (item[1], item[0]))
                end = lower_bound + position + width
            else:
                end = hard_end
        if end <= start:
            end = hard_end
        chunks.append(text[start:end])
        start = end
    return chunks


def _task_hint(text: str) -> str:
    """Retain likely instructions from both ends of a long submission."""
    if len(text) <= 1700:
        return text
    beginning = text[:500]
    ending = text[-800:]
    return beginning + "\n\n[... conteúdo intermédio analisado em partes ...]\n\n" + ending


def _note_groups(notes: list[str], max_group_chars: int = 1650) -> list[list[str]]:
    groups: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for note in notes:
        size = len(note)
        if current and (len(current) >= 4 or current_chars + size > max_group_chars):
            groups.append(current)
            current = []
            current_chars = 0
        current.append(note)
        current_chars += size
    if current:
        groups.append(current)
    return groups


def _compact_notes(
    notes: list[str],
    call_once: Callable[..., dict[str, Any]],
    emit: Callable[[dict[str, Any]], None] | None,
    context_tokens: int,
) -> str:
    target_tokens = min(FINAL_NOTES_TOKEN_BUDGET, max(240, context_tokens // 3))
    current = list(notes)
    round_index = 0
    while estimate_tokens("\n".join(current)) > target_tokens and len(current) > 1:
        round_index += 1
        groups = _note_groups(current)
        reduced: list[str] = []
        for group_index, group in enumerate(groups, start=1):
            if emit:
                emit({
                    "type": "progress",
                    "phase": "consolidation",
                    "current": group_index,
                    "total": len(groups),
                    "message": f"A consolidar notas ({round_index}.ª passagem, grupo {group_index}/{len(groups)})…",
                })
            prompt = (
                "Consolida as notas de análise abaixo em português de Portugal. "
                "Preserva conclusões importantes, números, nomes, caminhos, erros, "
                "dependências e referências [Parte N]. Não inventes factos. Remove "
                "repetições, mas não elimines detalhes únicos que possam responder "
                "à tarefa original. Produz notas compactas, não a resposta final.\n\n"
                + "\n\n".join(group)
            )
            result = call_once([{"role": "user", "content": prompt}], max_tokens=REDUCE_OUTPUT_TOKENS, timeout=600)
            result_text = str(result.get("content", "")).strip()
            if result_text:
                reduced.append(result_text)
            else:
                reduced.extend(group)
        if len(reduced) >= len(current):
            # Emergency fallback: bounded local compression keeps progress
            # possible even if a model returns unusually long summaries.
            reduced = [note[:1650] for note in reduced]
        current = reduced
        if round_index >= 8:
            break
    joined = "\n\n".join(current)
    if estimate_tokens(joined) > target_tokens:
        # Keep the strongest bounded prefix and suffix rather than sending a
        # prompt that is known to exceed the active context.
        max_chars = max(300, (target_tokens - 40) * 3)
        joined = joined[: max_chars // 2] + "\n[notas intermédias compactadas]\n" + joined[-max_chars // 2 :]
    return joined


def adaptive_chat(
    messages: list[dict[str, Any]],
    call_once: Callable[..., dict[str, Any]],
    call_stream: Callable[..., dict[str, Any]],
    emit: Callable[[dict[str, Any]], None] | None = None,
    context_tokens: int = DEFAULT_CONTEXT_TOKENS,
    system_prompt: str = "",
) -> dict[str, Any]:
    """Run a direct chat or a bounded, multi-pass analysis for long inputs."""
    if not isinstance(messages, list) or not messages:
        raise ValueError("A mensagem da conversa está vazia ou tem formato inválido.")
    normalized = [m for m in messages if isinstance(m, dict) and m.get("role") in {"user", "assistant", "system"}]
    user_index = latest_user_index(normalized)
    if user_index < 0:
        raise ValueError("Não foi encontrada uma mensagem do utilizador.")
    user_text = normalized[user_index].get("content", "")
    if not isinstance(user_text, str):
        user_text = str(user_text or "")
    started = time.monotonic()

    if not should_chunk_latest_user(normalized, context_tokens, system_prompt):
        compact = fit_recent_history(normalized, context_tokens, system_prompt)
        if emit:
            emit({"type": "meta", "mode": "direct", "message": "Pedido dentro do orçamento de contexto; via rápida."})
        result = call_stream(
            compact,
            max_tokens=min(DEFAULT_OUTPUT_TOKENS, max(128, context_tokens // 4)),
            timeout=600,
            on_delta=(lambda delta: emit({"type": "token", "delta": delta}) if emit else None),
        ) if emit else call_once(
            compact,
            max_tokens=min(DEFAULT_OUTPUT_TOKENS, max(128, context_tokens // 4)),
            timeout=600,
        )
        result = dict(result)
        result["mode"] = "direct"
        result["total_seconds"] = round(time.monotonic() - started, 2)
        result["history_summary"] = None
        return result

    # The original submission remains intact in this function; only bounded
    # excerpts and compact notes are carried into each individual model call.
    chunk_chars = max(700, min(1500, (int(context_tokens) - 650) * 2))
    chunks = split_text(user_text, chunk_chars)
    if emit:
        emit({
            "type": "meta", "mode": "chunked", "chunks": len(chunks),
            "message": f"Texto extenso: análise incremental em {len(chunks)} partes.",
        })

    notes: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        if emit:
            emit({
                "type": "progress", "phase": "analysis", "current": index,
                "total": len(chunks), "message": f"A analisar parte {index}/{len(chunks)}…",
            })
        prompt = (
            f"Analisa a parte {index}/{len(chunks)} de uma submissão extensa. "
            "Cria notas de trabalho concisas e fiéis, em português de Portugal. "
            "Regista factos, argumentos, nomes, números, caminhos de ficheiros, "
            "funções, erros e dependências relevantes; assinala contradições e "
            "referencia esta parte como [Parte " + str(index) + "]. Não inventes "
            "e não apresentes ainda uma resposta final. Se for código, conserva "
            "nomes exatos e relações entre componentes.\n\n"
            f"CONTEÚDO DA PARTE {index}:\n{chunk}"
        )
        result = call_once([{"role": "user", "content": prompt}], max_tokens=CHUNK_OUTPUT_TOKENS, timeout=600)
        note = str(result.get("content", "")).strip()
        if not note:
            raise RuntimeError(f"A análise da parte {index}/{len(chunks)} não produziu notas.")
        notes.append(f"[Parte {index}] {note}")
        # Keep the working buffer bounded during very long submissions rather
        # than waiting until every part has been processed.
        if len(notes) >= 8:
            if emit:
                emit({"type": "progress", "phase": "buffer", "current": index,
                      "total": len(chunks), "message": "A compactar o buffer de trabalho para libertar contexto…"})
            rolling_summary = _compact_notes(notes, call_once, emit, int(context_tokens))
            notes = [f"[Resumo acumulado das partes 1-{index}]\n{rolling_summary}"]

    compacted = _compact_notes(notes, call_once, emit, int(context_tokens))
    hint = _task_hint(user_text)
    final_prompt = (
        "Responde à tarefa original em português de Portugal, com clareza e rigor. "
        "Usa as notas de todas as partes como evidência; combina conclusões sem "
        "repetições, identifica incertezas e não inventes informação ausente. "
        "Se a submissão pedir uma explicação, explica; se pedir extração ou revisão, "
        "executa essa tarefa. As referências [Parte N] podem ser usadas para indicar "
        "a origem de um ponto. A submissão foi analisada integralmente em partes; "
        "o excerto inicial/final abaixo serve para recuperar o pedido original.\n\n"
        "CONTEXTO DO PEDIDO (início e fim da submissão):\n" + hint +
        "\n\nNOTAS CONSOLIDADAS DA ANÁLISE:\n" + compacted +
        "\n\nProduz agora a resposta final, sem descrever o processo interno de análise."
    )
    if emit:
        emit({"type": "progress", "phase": "synthesis", "current": 1, "total": 1,
              "message": "Partes analisadas. A preparar a resposta final…"})
        final = call_stream(
            [{"role": "user", "content": final_prompt}],
            max_tokens=min(DEFAULT_OUTPUT_TOKENS, max(128, context_tokens // 4)),
            timeout=600,
            on_delta=lambda delta: emit({"type": "token", "delta": delta}),
        )
    else:
        final = call_once(
            [{"role": "user", "content": final_prompt}],
            max_tokens=min(DEFAULT_OUTPUT_TOKENS, max(128, context_tokens // 4)),
            timeout=600,
        )
    final = dict(final)
    final["mode"] = "chunked"
    final["chunks"] = len(chunks)
    final["total_seconds"] = round(time.monotonic() - started, 2)
    final["history_summary"] = compacted[:1500]
    return final
