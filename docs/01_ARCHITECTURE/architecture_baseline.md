# Baseline arquitectural do AdaptiveLocalAI

**Identificador:** ALAI-ARCH-001  
**Versão:** 1.0  
**Estado:** Proposta para aprovação  
**Âmbito:** Arquitectura lógica, responsabilidades, contratos e dependências  
**Referência de código:** main @ 4adad6bb7bf116d61044a22a98afe4fccb9bece6

## 1. Objectivo

Definir uma arquitectura modular, multiplataforma e independente de runtimes. O sistema deverá permitir acrescentar modelos, formatos, motores de inferência, backends e plataformas sem propagar dependências específicas por toda a aplicação.

Esta especificação não declara implementados os módulos aqui descritos. A implementação efectiva deverá ser confirmada na F0 e registada no manifesto de módulos.

## 2. Princípios vinculativos propostos

1. Não duplicar funcionalidades existentes.
2. Não confundir código existente com funcionalidade validada.
3. Não substituir inferência ou calibração funcionais sem equivalência comprovada.
4. Separar artefacto original de pacote preparado para runtime.
5. Separar detecção de hardware, disponibilidade e capacidade testada.
6. Separar benchmark de avaliação de qualidade.
7. Tratar CPU como caminho de compatibilidade de referência.
8. Tratar GPU/NPU como aceleradores opcionais.
9. Não impor um runtime, modelo, linguagem ou fabricante ao núcleo.
10. Encaminhar operações de agentes através do sistema de segurança.
11. Preservar dados e perfis através de esquemas versionados.
12. Registar decisões e evidências de validação.

## 3. Arquitectura em camadas

| Camada | Responsabilidade |
|---|---|
| Presentation | Interfaces Desktop, Mobile e Web |
| Application Services | Casos de utilização e coordenação |
| Intelligence | Documentos, projectos, memória, agentes e workflows |
| Inference | API uniforme, sessões, filas, streaming e cancelamento |
| Runtime | Gestão de motores e adaptadores |
| Model | Catálogo, providers, instalação, compatibilidade e armazenamento |
| Calibration | Benchmark, qualidade, estabilidade e perfis |
| Hardware | Detecção e monitorização de recursos |
| Security | Sandbox, políticas, permissões e auditoria |
| Platform Core | Configuração, filesystem, processos, IPC, persistência e eventos |
| Platform Adapters | Integração específica com cada sistema operativo |

A separação em camadas é lógica. Não obriga a criar um processo ou pacote independente por cada componente.

## 4. Subsistemas

### 4.1 Platform Core

Responsabilidades:
- Configuration Manager.
- Filesystem e Path Resolver.
- Process Manager e IPC.
- Persistence Manager.
- Event Bus.
- Logging e Diagnostics.
- Dependency Manager.
- Shutdown e Integrity Manager.
- Update Manager.

O núcleo não deve conter lógica de negócio específica de um runtime ou sistema operativo.

### 4.2 Hardware Intelligence

Componentes:
- CPU e ISA Capability Detector.
- RAM Manager.
- GPU e VRAM Detector.
- NPU Detector.
- Storage Analyzer.
- OS e Driver Detector.
- Backend Capability Detector.
- Resource Monitor.
- Hardware Fingerprint Manager.

Cada capacidade deve ser classificada como DETECTED, AVAILABLE ou TESTED. Uma GPU detectada não prova que um runtime consiga utilizá-la.

### 4.3 Runtime Manager

Responsabilidades:
- Registo, descoberta e validação de runtimes.
- Instalação e actualização.
- Declaração de capacidades.
- Arranque, paragem e monitorização.
- Recuperação e diagnóstico.
- Selecção do runtime compatível.

O primeiro adaptador de referência será llama.cpp. MLC LLM será experimental. Ollama e LocalAI serão avaliados como integrações opcionais. Core ML, LiteRT, WebLLM e vLLM são candidatos de investigação, não capacidades declaradas.

### 4.4 Model Manager

Componentes:
- Model Catalog.
- Model Source Manager.
- Providers.
- Download Manager.
- Metadata Parser.
- Model Compatibility Engine.
- Model Installer.
- Model Registry.
- Model Storage.
- Integrity Validator.
- Recommendation Engine.

Providers previstos: Hugging Face, Ollama Registry, LocalAI Gallery, catálogo oficial, fontes personalizadas e importação local.

O Download Manager deverá suportar progresso, cancelamento, retoma quando a origem o permitir, retries, checksum, ficheiros temporários e instalação atómica.

### 4.5 Artefacto e pacote de runtime

Model Artifact é o ficheiro ou conjunto original de pesos e dependências, identificado por hash e metadados.

Runtime Model Package é a representação preparada, convertida, compilada ou importada para um runtime específico.

Não assumir que um artefacto é directamente executável em todos os runtimes. A preparação deve ser da responsabilidade do adaptador ou de um pipeline explicitamente registado.

### 4.6 Runtime Adapter Contract

Contrato conceptual:

- identify()
- get_version()
- get_capabilities()
- validate_model(artifact)
- prepare_model(artifact)
- start(config)
- stop()
- get_status()
- load_model(package, config)
- unload_model()
- generate(request)
- stream(request)
- cancel(request_id)
- health_check()
- collect_metrics()

As operações opcionais devem ser declaradas como capacidades não suportadas. Não simular streaming, cancelamento ou multimodalidade quando o runtime não os suporta.

Capacidades declaradas:
- Plataformas e arquitecturas.
- Formatos e quantizações.
- Backends CPU/GPU/NPU.
- Visão, áudio e outras modalidades.
- Streaming e cancelamento.
- Limites de contexto e concorrência.
- Requisitos de memória e instalação.

### 4.7 Model Compatibility Engine

A compatibilidade é função do artefacto, runtime e versão, sistema operativo, arquitectura, hardware, backend e funcionalidades requeridas.

Resultados normalizados:
- COMPATIBLE.
- COMPATIBLE_WITH_LIMITATIONS.
- INCOMPATIBLE.
- NOT_VERIFIED.

Estimativas de memória devem ser identificadas como estimativas, nunca como medições.

### 4.8 Benchmark Engine

Cada experiência deve registar:
- experiment_id.
- model_id e artifact fingerprint.
- runtime_id e versão.
- hardware fingerprint.
- configuração completa.
- dataset e versão.
- warmup_runs e measured_runs.
- métricas, erros e timestamp.
- estado e condições da experiência.

Métricas possíveis: TTFT, processamento de prompt, tokens/s de geração, latência média/mediana/P95, RAM, VRAM, CPU/GPU, KV cache, temperatura e energia quando mensurável.

### 4.9 Quality Evaluation

Subsistema separado do benchmark. Datasets e critérios devem abranger Português de Portugal, instruções, raciocínio, matemática, programação, documentos, saídas estruturadas, multimodalidade, consistência e resistência a prompt injection.

O resultado de qualidade deve ser independente das medições de velocidade.

### 4.10 Automatic Calibration

Integra Hardware Intelligence, Runtime Manager, Model Registry, Benchmark Engine, Quality Evaluation e Stability Monitor.

Restrições obrigatórias:
1. Compatibilidade.
2. Limites de memória.
3. Estabilidade.
4. Qualidade mínima.
5. Desempenho.
6. Energia, quando mensurável.

Uma configuração rápida que falhe qualidade, estabilidade ou memória é rejeitada.

Perfis de utilização propostos: balanced, performance, quality, low_memory, long_context e battery_saver. Estes perfis não substituem a identidade do perfil calibrado.

### 4.11 Inference Service

Responsável por:
- Pedidos e respostas uniformes.
- Sessões e filas.
- Streaming e cancelamento quando suportados.
- Limites de contexto.
- Concorrência.
- Estado do runtime.
- Recuperação de falhas.
- Métricas e utilização de tokens.

Os consumidores não devem conhecer comandos ou estruturas internas do runtime.

### 4.12 Sandbox & Security

Componentes:
- Sandbox Manager.
- Policy Engine.
- Permission Manager.
- Workspace Manager.
- Command Validator.
- Resource Limits.
- Process Supervisor.
- Audit Logger.
- Artifact Manager.
- Environment Templates.

Ambientes:
- A — desenvolvimento e programação.
- B — benchmarks e avaliação de modelos, com artefactos originais read-only.
- C — ferramentas e agentes, com permissões granulares e aprovação.
- D — workspace documental e de projectos, inicialmente read-only.

A rede deve estar desactivada por defeito. Aplicar limites de CPU, RAM, disco e tempo, validação de caminhos, controlo de processos, registo de operações e aprovação humana para acções destrutivas.

Processo separado não equivale a sandbox segura. Se não existir isolamento forte, reduzir as operações permitidas.

### 4.13 Document & Project Intelligence

Project Intelligence:
- Scanner e classificador de ficheiros.
- Parser de código e indexador de símbolos.
- Mapa de repositório.
- Análise de dependências e arquitectura.
- Gestão de contexto.
- Análise de impacto de alterações.

Document Intelligence:
- Ingestão e normalização.
- Parsers PDF/DOCX/XLSX/PPTX.
- OCR e extracção de imagens/tabelas.
- Chunking e embeddings.
- Pesquisa híbrida, reranking e contexto.
- Citações e proveniência.

A indexação deve preservar origem, página, secção, posição e referências. O sistema deve trabalhar incrementalmente e não depender de enviar um projecto inteiro num único prompt.

### 4.14 Agent & Workflow Engine

Agentes lógicos propostos: Coordinator, Planner, Researcher, Analyst, Architect, Developer, Reviewer, Tester, Security Auditor e Documentation.

Não é obrigatório um modelo distinto por agente. A especialização pode resultar de instruções, contexto, ferramentas e permissões.

Estados de workflow: PENDING, READY, RUNNING, WAITING_APPROVAL, PAUSED, FAILED, RETRYING, COMPLETED e CANCELLED.

Cada etapa deve possuir entradas, saídas, estado, tentativas, evidências e checkpoint. Toda a execução de ferramentas passa pelo Sandbox Manager.

### 4.15 Memory & Knowledge

- Working Memory: contexto temporário da tarefa.
- Project Memory: decisões e conhecimento persistente do projecto.
- Semantic Memory: informação recuperável por pesquisa.

Cada registo deve preservar origem, data, projecto, confiança, versão e relações. A base vectorial é um adaptador opcional, não uma dependência obrigatória do núcleo.

## 5. Contratos comuns e eventos

Serviços conceptuais:
- hardware.detect() / hardware.capabilities()
- models.discover() / models.validate() / models.compatibility()
- runtime.select() / runtime.start() / runtime.stop()
- calibration.run() / calibration.get_profile()
- inference.generate() / inference.stream() / inference.cancel()
- sandbox.create() / sandbox.execute() / sandbox.destroy()
- projects.analyze() / projects.index()
- agents.plan() / agents.execute() / agents.resume()

Eventos principais:
- hardware.detected
- model.discovered / model.validated / model.installation.completed
- runtime.started / runtime.stopped / runtime.failed
- calibration.started / calibration.progress / calibration.completed / calibration.failed
- inference.started / inference.token / inference.completed / inference.failed / inference.cancelled
- sandbox.command_approved / sandbox.execution_completed
- agent.checkpoint_saved / agent.execution_completed
- project.analysis_completed

Envelope de evento:
- event_id
- event_type
- event_version
- timestamp
- correlation_id
- source_module
- payload

Eventos e interfaces devem ser versionados. Alterações incompatíveis exigem nova versão e migração dos consumidores.

## 6. Persistência e identidade

Proposta de armazenamento:
- SQLite para metadados, sessões, perfis e workflows.
- JSON versionado para configuração e manifestos.
- Ficheiros para modelos e artefactos.
- JSONL para logs estruturados.
- Vector Store Adapter para índices semânticos quando necessário.

Entidades principais:
- ModelArtifact.
- Runtime.
- RuntimePackage.
- HardwareProfile.
- CalibrationProfile.
- BenchmarkExperiment.
- QualityEvaluation.
- InferenceSession.
- Workflow.
- Project.
- SandboxExecution.

Os identificadores devem ser estáveis e independentes de caminhos absolutos locais.

## 7. Identidade de calibração

Um perfil depende, no mínimo, de:
- Hash do artefacto.
- Runtime e versão.
- Fingerprint dos binários e bibliotecas relevantes, incluindo o servidor de inferência.
- Hardware fingerprint.
- Sistema operativo e drivers relevantes.
- Backend.
- Configuração.
- Versão do algoritmo de calibração.

Estados possíveis: candidate, validated, degraded, invalidated, legacy e failed.

A alteração de uma dependência deve invalidar apenas os perfis afectados. Perfis antigos sem evidência não podem ser promovidos automaticamente a validated.

## 8. Observabilidade

Serviços:
- Structured Logging.
- Metrics Collector.
- Trace Manager.
- Health Monitor.
- Error Registry.
- Crash Reporter.
- Diagnostic Bundle.
- Resource Monitor.

As decisões de runtime e calibração devem poder ser explicadas através da configuração escolhida, alternativas, motivos de rejeição e evidências.

## 9. Regras de dependência

- UI depende apenas de serviços e contratos públicos.
- Intelligence depende de Inference Service, memória e serviços públicos, nunca de llama.cpp directamente.
- Agents dependem de Sandbox Manager para ferramentas.
- Calibration depende de interfaces de hardware, runtime, benchmark e qualidade.
- Runtime adapters implementam o contrato comum; não são importados directamente pelos consumidores.
- Platform Core não depende de módulos de negócio.
- Persistência não depende de runtime específico.
- Adaptadores de plataforma concentram operações específicas do sistema operativo.

## 10. Manifesto de módulo

Cada módulo deverá declarar:
- module_id e module_version.
- responsibility.
- dependencies.
- public_interfaces.
- events_published e events_consumed.
- configuration.
- data_schema.
- tests.
- implementation_status.
- validation_status.
- platform_support.

Estados de implementação e validação são independentes.

## 11. Tecnologias por decidir

Não ficam fechadas nesta versão:
- Linguagem do núcleo: Python ou combinação com Rust/C++.
- Tecnologia de UI Desktop/Mobile.
- Vector Store.
- Nível de suporte de Ollama e LocalAI.
- Viabilidade de Core ML, LiteRT, WebLLM e vLLM por plataforma.

Cada decisão requer ADR com alternativas, critérios, evidências, consequências e plano de reversão.

## 12. Critério de conformidade

Um módulo só está conforme quando possui responsabilidade delimitada, contrato documentado, dependências declaradas, testes relevantes, documentação em português de Portugal e estado de validação sustentado por evidências.
