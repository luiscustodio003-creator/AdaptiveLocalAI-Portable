# ADR-0004 — Linguagem do núcleo

- Estado: Proposed — decisão pendente
- Data: 2026-11-02
- Âmbito: Platform Core e serviços

## Contexto

É necessário escolher a estratégia de implementação do núcleo multiplataforma sem comprometer manutenção, integração de runtimes e execução em hardware modesto.

## Alternativas a avaliar

- Python como linguagem predominante.
- Rust para componentes de sistema, mantendo serviços em Python.
- C/C++ para componentes de baixo nível e bindings.
- Arquitectura híbrida com fronteiras IPC estáveis.

## Critérios

- Portabilidade Windows/Linux/macOS/Android/iOS.
- Consumo de memória e tempo de arranque.
- Facilidade de integração com runtimes nativos.
- Segurança de memória e isolamento.
- Empacotamento e distribuição.
- Testabilidade.
- Manutenção e disponibilidade de bibliotecas.
- Capacidade de desenvolvimento incremental sem reescrita global.

## Decisão

Não seleccionada. A decisão exige uma prova de conceito limitada e comparação documentada. A linguagem não deve ser escolhida antes de se conhecerem os contratos e dependências reais da F0/F1.
