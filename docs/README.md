# AdaptiveLocalAI — Documentação técnica

Esta pasta contém a documentação directora do AdaptiveLocalAI-Portable.

## Estrutura

- [Visão geral e princípios](00_PROJECT_OVERVIEW/README.md)
- [Roadmap oficial F0–F14](00_PROJECT_OVERVIEW/roadmap.md)
- [Arquitectura e contratos](01_ARCHITECTURE/README.md)
- [Baseline de compatibilidade e migração](01_ARCHITECTURE/compatibility_baseline.md)
- [Registo de decisões arquitecturais](01_ARCHITECTURE/adr/README.md)

## Estado documental

A documentação da arquitectura constitui uma proposta técnica para revisão. Não autoriza, por si só, alterações estruturais ao código nem a substituição dos mecanismos actuais de inferência e calibração.

A referência de código usada na preparação inicial é a branch main, commit 4adad6bb7bf116d61044a22a98afe4fccb9bece6. Antes de qualquer migração deverá ser confirmada a correspondência entre esta referência publicada e a cópia local de desenvolvimento.

## Regras

1. A sequência e os nomes das fases F0–F14 são preservados.
2. Funcionamento e validação são estados diferentes.
3. Inferência e calibração existentes são protegidas por testes de caracterização.
4. Novos módulos dependem de contratos públicos, não de detalhes internos.
5. Decisões tecnológicas ainda não demonstradas permanecem registadas como pendentes.
