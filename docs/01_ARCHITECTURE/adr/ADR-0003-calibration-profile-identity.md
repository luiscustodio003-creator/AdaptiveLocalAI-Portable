# ADR-0003 — Identidade e validade dos perfis de calibração

- Estado: Proposed
- Data: 2026-11-02
- Âmbito: Calibração e persistência

## Contexto

Um perfil de calibração só é reutilizável quando o modelo, runtime, hardware e ambiente relevante correspondem às condições em que foi validado.

## Proposta

Identificar o perfil através de fingerprints do artefacto, runtime e versão, binários e bibliotecas relevantes, hardware, sistema operativo, drivers, backend e algoritmo de calibração.

Estados: candidate, validated, degraded, invalidated, legacy e failed.

## Alternativas

1. Identificar apenas pelo nome do modelo.
2. Identificar pelo caminho do ficheiro.
3. Identificar por fingerprints compostos.

## Justificação

Nome e caminho não identificam inequivocamente conteúdo ou ambiente. Fingerprints compostos permitem invalidar apenas os perfis afectados.

## Consequências

- A migração de perfis exige esquema versionado.
- Perfis sem evidência permanecem legacy.
- Alterações irrelevantes não devem invalidar todos os perfis.
- O fingerprint exacto e os componentes relevantes devem ser confirmados na F0/F1.
