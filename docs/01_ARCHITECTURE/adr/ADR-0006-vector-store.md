# ADR-0006 — Armazenamento vectorial

- Estado: Proposed — decisão pendente
- Data: 2026-11-02
- Âmbito: Document & Project Intelligence

## Contexto

A pesquisa semântica poderá ser necessária para documentos e projectos extensos, mas não deverá tornar o núcleo dependente de um serviço pesado ou remoto.

## Alternativas a avaliar

- Chroma.
- SQLite com extensão ou mecanismo vectorial embutido.
- FAISS ou biblioteca local equivalente.
- Adaptador para múltiplos backends.

## Critérios

- Execução offline.
- Consumo de RAM e disco.
- Portabilidade e compatibilidade de arquitectura.
- Persistência e recuperação.
- Pesquisa híbrida e filtros por metadados.
- Migração e reindexação.
- Licença e manutenção.

## Decisão

Não seleccionada. A arquitectura deverá expor um Vector Store Adapter. A implementação concreta será decidida após benchmark com corpus representativo e hardware modesto.
