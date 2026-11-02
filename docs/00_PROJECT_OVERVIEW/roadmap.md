# Roadmap oficial F0–F14

Os nomes e a sequência abaixo são a referência oficial do projecto. Não renomear, fundir ou reordenar fases sem uma decisão arquitectural formal.

| Fase | Designação oficial | Objectivo |
|---|---|---|
| F0 | Auditoria e inventário | Inventariar o estado real, dependências, duplicações, riscos e testes. |
| F1 | Arquitectura e contratos | Aprovar arquitectura, módulos, interfaces, eventos, dados e migração. |
| F2 | Core multiplataforma | Criar serviços de configuração, filesystem, processos, IPC, persistência e eventos. |
| F3 | Hardware Intelligence | Detectar e monitorizar CPU, RAM, GPU, NPU, armazenamento, SO e backends. |
| F4 | Runtime & Model Manager | Gerir runtimes, catálogo, instalação, compatibilidade e execução de modelos. |
| F5 | Sandbox & Security | Isolar execução, gerir permissões, políticas, recursos e auditoria. |
| F6 | Benchmark Engine | Executar experiências reproduzíveis e recolher métricas de desempenho. |
| F7 | Quality Evaluation | Avaliar qualidade, consistência e regressões dos modelos. |
| F8 | Automatic Calibration | Optimizar configurações e persistir perfis validados. |
| F9 | Inference API | Disponibilizar API uniforme, streaming, cancelamento e gestão de pedidos. |
| F10 | Document & Project Intelligence | Indexar e analisar documentos e projectos com contexto selectivo e evidências. |
| F11 | Agent & Workflow Engine | Planear e executar tarefas com checkpoints, permissões e recuperação. |
| F12 | Interface completa | Disponibilizar dashboard, conversação, modelos, hardware, calibração e diagnósticos. |
| F13 | Integração multiplataforma | Integrar e validar Windows, Linux, macOS, Android, iOS/iPadOS e Web. |
| F14 | Testes finais e distribuição | Validar segurança, desempenho, migração, instalação, integridade e distribuição. |

## Critérios transversais

- Cada fase produz documentação, testes e critérios de aceitação.
- As fases podem ter trabalho preparatório em paralelo, mas a aprovação de saída de uma fase é necessária antes de declarar concluída a fase seguinte.
- A validação em Windows não implica validação em Linux, macOS ou dispositivos móveis.
- Funcionalidade parcial deve permanecer identificada como parcial.
- A F0 não autoriza reestruturação ou implementação; a F1 define os contratos que orientarão a implementação.
