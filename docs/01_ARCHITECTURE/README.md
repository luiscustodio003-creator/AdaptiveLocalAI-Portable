# Arquitectura e contratos

## Objectivo

Definir as fronteiras dos módulos, os contratos públicos e as regras de dependência do AdaptiveLocalAI.

## Documentos

- [Baseline arquitectural](architecture_baseline.md): camadas, subsistemas, responsabilidades e contratos conceptuais.
- [Baseline de compatibilidade e migração](compatibility_baseline.md): protecção da inferência, calibração, perfis e migração incremental.
- [Registo ADR](adr/README.md): decisões tomadas, propostas e questões pendentes.

## Estado

Proposta para revisão. Não é uma autorização automática para modificar o código.

## Regras de implementação

1. Auditar o módulo existente antes de criar outro.
2. Definir responsabilidade, entradas, saídas, erros e dependências.
3. Expor interfaces públicas versionadas.
4. Não permitir dependências circulares.
5. Não permitir que a UI, agentes ou inteligência documental executem comandos de runtime directamente.
6. Manter adaptadores de plataforma e runtime nas respectivas fronteiras.
7. Criar testes de contrato e regressão antes de migrar consumidores.
8. Documentar cada módulo em português de Portugal e incluir README.txt próprio.
