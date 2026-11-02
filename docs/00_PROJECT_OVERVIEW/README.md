# AdaptiveLocalAI — Visão geral

## Missão

Construir uma plataforma de inteligência artificial local, portátil, adaptativa e multiplataforma, capaz de seleccionar e executar modelos de acordo com as capacidades efectivamente disponíveis no equipamento.

A plataforma deverá gerir o ciclo completo de modelos e runtimes, executar inferência através de uma interface uniforme, medir desempenho e qualidade, calibrar configurações, preservar perfis reutilizáveis e disponibilizar serviços seguros de análise documental, projectos e agentes.

## Princípios

- Independência de runtime, modelo, fabricante e sistema operativo.
- Núcleo multiplataforma e adaptadores específicos por plataforma.
- CPU-first e offline-first, sem excluir aceleração opcional.
- Detecção, disponibilidade e validação de capacidades como estados distintos.
- Calibração persistente, reproduzível e condicionada ao ambiente.
- Segurança por permissões mínimas e execução isolada.
- Ausência de duplicação funcional.
- Evidência de testes antes de declarar uma capacidade validada.
- Evolução incremental, sem reescrita global.

## Modos de operação

- Portable: execução a partir de armazenamento externo, com verificação de integridade e remoção segura.
- Desktop: aplicação instalada no equipamento.
- Server: serviços locais ou de rede, com políticas de acesso explícitas.
- Mobile: integração nativa e runtimes compatíveis com o dispositivo.
- Web: interface browser e execução apenas onde as capacidades do ambiente o permitam.

## Limites de responsabilidade

O AdaptiveLocalAI é o produto principal e não depende de ferramentas externas de desenvolvimento, como REA-Claude ou OpenCode. Essas ferramentas podem apoiar a engenharia, mas não constituem dependências de execução do produto.
