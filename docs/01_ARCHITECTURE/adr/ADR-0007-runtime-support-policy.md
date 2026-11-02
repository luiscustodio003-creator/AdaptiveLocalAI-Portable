# ADR-0007 — Política de suporte de runtimes

- Estado: Proposed
- Data: 2026-11-02
- Âmbito: Runtime Manager

## Contexto

A arquitectura deve admitir vários runtimes, mas a manutenção de cada adaptador tem custos de integração, testes, distribuição e suporte.

## Proposta

Classificar cada runtime por nível:
- Reference: adaptador de referência com testes completos.
- Supported: adaptador suportado em plataformas e capacidades declaradas.
- Experimental: integração sujeita a alterações.
- Research: apenas investigação, sem compromisso de suporte.

llama.cpp inicia como runtime de referência. MLC LLM inicia como experimental. Ollama e LocalAI ficam em avaliação. Core ML, LiteRT, WebLLM e vLLM permanecem em investigação até existir evidência.

## Critérios

- Plataformas e arquitecturas.
- Formatos suportados.
- Compatibilidade multimodal.
- Streaming e cancelamento.
- Memória e desempenho.
- Licenciamento e distribuição.
- Manutenção e testes automatizados.

## Decisão

A política de níveis é proposta. O estado de cada adaptador deverá ser confirmado através de testes reais por plataforma.
