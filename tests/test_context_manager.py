import math
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from context_manager import (
    adaptive_chat,
    estimate_tokens,
    fit_recent_history,
    should_chunk_latest_user,
    split_text,
)


def test_estimate_tokens_is_zero_for_empty_and_conservative_for_text():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcdefghij") == math.ceil(10 / 3)


def test_split_text_preserves_every_character_and_bounds_chunks():
    text = ("Primeiro parágrafo com informação relevante.\n\n" * 40) + "FIM"
    chunks = split_text(text, 500)
    assert len(chunks) > 1
    assert "".join(chunks) == text
    assert all(len(chunk) <= 500 for chunk in chunks)


def test_split_text_handles_a_single_long_line():
    text = "x" * 2300
    chunks = split_text(text, 700)
    assert "".join(chunks) == text
    assert all(len(chunk) <= 700 for chunk in chunks)


def test_long_latest_user_submission_uses_incremental_mode():
    messages = [{"role": "user", "content": "detalhe " * 2500}]
    assert should_chunk_latest_user(messages, context_tokens=2048, system_prompt="s")


def test_short_latest_user_submission_stays_on_fast_path_even_with_old_large_history():
    messages = [
        {"role": "user", "content": "documento antigo " * 2000},
        {"role": "assistant", "content": "Resumo antigo."},
        {"role": "user", "content": "Olá, resume isto."},
    ]
    assert not should_chunk_latest_user(messages, context_tokens=2048, system_prompt="s")
    fitted = fit_recent_history(messages, context_tokens=2048, system_prompt="s")
    assert fitted[-1]["content"] == "Olá, resume isto."
    assert len(fitted) < len(messages)


def test_short_request_streams_directly_and_emits_progressive_tokens():
    observed = []

    def call_once(messages, max_tokens=512, timeout=600):
        return {"content": "nao devia ser chamado", "seconds": 0.1, "tokens": 4, "tok_s": 40.0}

    def call_stream(messages, max_tokens=512, timeout=600, on_delta=None):
        if on_delta:
            on_delta("Olá")
            on_delta("!")
        return {"content": "Olá!", "seconds": 0.2, "tokens": 2, "tok_s": 10.0}

    result = adaptive_chat(
        [{"role": "user", "content": "Diz olá."}],
        call_once=call_once,
        call_stream=call_stream,
        emit=observed.append,
        context_tokens=2048,
        system_prompt="s",
    )
    assert result["mode"] == "direct"
    assert result["content"] == "Olá!"
    assert any(event.get("type") == "token" for event in observed)
    assert result["history_summary"] is None


def test_long_request_analyzes_parts_then_streams_final_answer():
    calls = []
    observed = []

    def call_once(messages, max_tokens=512, timeout=600):
        calls.append(messages[-1]["content"])
        if "CONTEÚDO DA PARTE" in messages[-1]["content"]:
            return {"content": "Facto importante; referência preservada.", "seconds": 0.1, "tokens": 8, "tok_s": 80.0}
        if "Consolida as notas" in messages[-1]["content"]:
            return {"content": "Notas consolidadas [Parte 1].", "seconds": 0.1, "tokens": 6, "tok_s": 60.0}
        return {"content": "Resposta final", "seconds": 0.1, "tokens": 4, "tok_s": 40.0}

    def call_stream(messages, max_tokens=512, timeout=600, on_delta=None):
        prompt = messages[-1]["content"]
        calls.append(prompt)
        if on_delta:
            on_delta("Resposta ")
            on_delta("final")
        return {"content": "Resposta final", "seconds": 0.2, "tokens": 4, "tok_s": 20.0}

    source = "Explica este conteúdo.\n\n" + ("O sistema deve conservar os identificadores 12345 e validar o resultado.\n\n" * 160)
    result = adaptive_chat(
        [{"role": "user", "content": source}],
        call_once=call_once,
        call_stream=call_stream,
        emit=observed.append,
        context_tokens=2048,
        system_prompt="Responde em português.",
    )
    assert result["mode"] == "chunked"
    assert result["chunks"] > 1
    assert result["content"] == "Resposta final"
    assert result["history_summary"]
    assert any(event.get("phase") == "analysis" for event in observed)
    assert any("CONTEÚDO DA PARTE" in call for call in calls)
    assert any(event.get("phase") == "synthesis" for event in observed)


def test_long_request_without_streaming_uses_legacy_non_streaming_output():
    def call_once(messages, max_tokens=512, timeout=600):
        prompt = messages[-1]["content"]
        return {"content": "Notas da parte processada." if "CONTEÚDO DA PARTE" in prompt else "Resposta final não streaming.",
                "seconds": 0.1, "tokens": 10, "tok_s": 100.0}

    def call_stream(messages, **kwargs):
        raise AssertionError("stream não devia ser usado nesta chamada")

    result = adaptive_chat(
        [{"role": "user", "content": "texto longo " * 1400}],
        call_once=call_once,
        call_stream=call_stream,
        context_tokens=2048,
        system_prompt="s",
    )
    assert result["mode"] == "chunked"
    assert result["content"] == "Resposta final não streaming."


def test_long_working_buffer_is_compacted_before_all_chunks_finish():
    events = []
    calls = {"parts": 0, "reductions": 0}

    def call_once(messages, max_tokens=512, timeout=600):
        prompt = messages[-1]["content"]
        if "CONTEÚDO DA PARTE" in prompt:
            calls["parts"] += 1
            return {"content": ("Identificador 12345 e detalhe importante. " * 8),
                    "seconds": 0.1, "tokens": 40, "tok_s": 400.0}
        if "Consolida as notas" in prompt:
            calls["reductions"] += 1
            return {"content": "Resumo consolidado; conservar [Parte 1] e identificador 12345.",
                    "seconds": 0.1, "tokens": 12, "tok_s": 120.0}
        return {"content": "Síntese final.", "seconds": 0.1, "tokens": 5, "tok_s": 50.0}

    def call_stream(messages, max_tokens=512, timeout=600, on_delta=None):
        if on_delta:
            on_delta("Síntese final.")
        return {"content": "Síntese final.", "seconds": 0.1, "tokens": 5, "tok_s": 50.0}

    result = adaptive_chat(
        [{"role": "user", "content": "Analisa este texto.\n\n" + ("linha informativa 12345. " * 2500)}],
        call_once=call_once,
        call_stream=call_stream,
        emit=events.append,
        context_tokens=2048,
        system_prompt="s",
    )
    assert result["mode"] == "chunked"
    assert calls["parts"] >= 8
    assert calls["reductions"] > 0
    assert any(event.get("phase") == "buffer" for event in events)
