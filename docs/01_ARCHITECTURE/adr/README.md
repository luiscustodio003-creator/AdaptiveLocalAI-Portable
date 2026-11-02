# Architecture Decision Records (ADR)

Este registo documenta decisões arquitecturais, alternativas e evidências. Uma proposta não deve ser apresentada como decisão aprovada.

## Estado

| ADR | Tema | Estado |
|---|---|---|
| ADR-0001 | Arquitectura modular e independência de runtime | Proposta |
| ADR-0002 | Preservação de inferência e calibração durante migração | Proposta |
| ADR-0003 | Persistência e identidade dos perfis | Proposta |
| ADR-0004 | Linguagem do núcleo | Pendente de avaliação |
| ADR-0005 | Tecnologia de interface | Pendente de avaliação |
| ADR-0006 | Vector Store | Pendente de avaliação |
| ADR-0007 | Nível de suporte dos runtimes adicionais | Pendente de avaliação |

## Processo

Cada ADR deve conter:
- Contexto e problema.
- Requisitos e critérios.
- Alternativas consideradas.
- Decisão e estado.
- Justificação e evidências.
- Consequências positivas e negativas.
- Plano de migração e reversão.
- Data e responsável pela aprovação.

Estados permitidos: Proposed, Accepted, Rejected, Superseded e Deprecated.

## Regra

Não escolher uma linguagem, base vectorial ou runtime apenas por popularidade. As decisões devem considerar portabilidade, consumo de recursos, licenciamento, manutenção, segurança, compatibilidade e evidências em hardware real.
