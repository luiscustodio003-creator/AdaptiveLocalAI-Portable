# ADR-0002 — Preservação de inferência e calibração

- Estado: Proposed
- Data: 2026-11-02
- Âmbito: Migração e compatibilidade

## Contexto

A aplicação já possui inferência local e calibração funcional. Uma reescrita prematura pode quebrar carregamento de modelos, consumo de perfis, API ou estabilidade.

## Proposta

Congelar uma baseline executável, criar testes de caracterização e migrar por extracção progressiva. Não alterar simultaneamente inferência e calibração. Não remover código anterior antes de equivalência, migração de dados e rollback serem demonstrados.

## Alternativas

1. Reescrita integral.
2. Migração incremental com adaptadores de compatibilidade.
3. Manter indefinidamente a implementação actual sem modularização.

## Justificação

A opção 2 protege o comportamento já desenvolvido e permite evoluir fronteiras sem exigir uma substituição imediata.

## Consequências

- A F0 deve confirmar a cópia local e a referência publicada.
- Testes reais com modelo e runtime são obrigatórios.
- Perfis antigos são preservados e classificados correctamente.
- A remoção do legado é uma decisão posterior, condicionada por evidências.
