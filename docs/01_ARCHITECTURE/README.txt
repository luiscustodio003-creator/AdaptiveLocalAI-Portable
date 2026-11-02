ADAPTIVELOCALAI — MÓDULO DE DOCUMENTAÇÃO DE ARQUITECTURA
===========================================================

Módulo:
-------
01_ARCHITECTURE

Objectivo:
----------
Documentar a arquitectura global, as fronteiras dos módulos, os contratos
públicos, as dependências e as regras de migração do AdaptiveLocalAI.

Ficheiros:
----------
- README.md
  Índice e regras de utilização da documentação de arquitectura.

- architecture_baseline.md
  Camadas, subsistemas, responsabilidades, contratos e regras de dependência.

- compatibility_baseline.md
  Baseline de inferência e calibração, testes de não regressão, migração de
  perfis, gates de integração e rollback.

- adr/README.md
  Registo de decisões arquitecturais.

- adr/ADR-*.md
  Decisões individuais, alternativas, evidências e estado de aprovação.

Dependências:
-------------
- docs/00_PROJECT_OVERVIEW/roadmap.md
- Auditoria F0 do repositório e da cópia local.
- Testes de caracterização da inferência e calibração.

Regras:
-------
1. Não declarar implementado o que apenas está especificado.
2. Não alterar a sequência ou os nomes das fases F0–F14.
3. Não substituir inferência ou calibração sem testes de equivalência.
4. Manter decisões ainda não demonstradas como pendentes.
5. Actualizar os ADR quando uma decisão for aprovada ou substituída.
6. Documentar alterações incompatíveis e respectivos planos de migração.

Estado:
-------
Proposta para revisão. Este módulo documental não altera o comportamento
executável da aplicação.

Idioma:
-------
Português de Portugal.
