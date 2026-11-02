# ADR-0005 — Tecnologia de interface

- Estado: Proposed — decisão pendente
- Data: 2026-11-02
- Âmbito: Presentation Layer

## Contexto

A interface actual contém funcionalidades que devem ser preservadas. A evolução deverá suportar Desktop e, futuramente, experiências móveis e Web sem introduzir dependências indevidas no núcleo.

## Alternativas a avaliar

- Manter a interface actual e modularizá-la.
- Evoluir a tecnologia Desktop existente.
- Partilhar componentes Web entre Desktop e Web, com integração nativa móvel separada.
- Criar interfaces nativas específicas por plataforma.

## Critérios

- Reutilização da interface existente.
- Acessibilidade e desempenho.
- Integração segura com serviços locais.
- Streaming e cancelamento.
- Distribuição e actualização.
- Separação de privilégios e IPC.
- Viabilidade real em Android e iOS.

## Decisão

Não seleccionada. A F0 deve inventariar a UI e os contratos que consome. A escolha deverá ser sustentada por uma prova de conceito e matriz de plataformas.
