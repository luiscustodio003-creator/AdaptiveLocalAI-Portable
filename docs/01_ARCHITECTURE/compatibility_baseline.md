# Baseline de compatibilidade, inferência e calibração

**Identificador:** ALAI-COMPAT-001  
**Versão:** 1.0  
**Estado:** Proposta para aprovação  
**Objectivo:** proteger o comportamento funcional antes de qualquer migração estrutural.

## 1. Referência

A referência publicada analisada é a branch main no commit 4adad6bb7bf116d61044a22a98afe4fccb9bece6.

A auditoria preliminar encontrou diferenças entre a cópia local anteriormente analisada e a versão publicada de src/app.py. A F0 deve comparar os dois estados antes de congelar uma baseline executável. Não assumir que a cópia local e a publicação são equivalentes.

## 2. Componentes actuais identificados

| Componente | Papel observado | Risco de migração |
|---|---|---|
| src/app.py | API local, servidor HTTP, ciclo de vida do llama-server e inferência | Elevado |
| src/calibration.py | llama-bench, exploração de threads, validação e persistência de perfis | Elevado |
| src/model_watcher.py | Observação de novos GGUF e fila de calibração | Médio |
| src/context_manager.py | Divisão incremental e consolidação de contexto | Médio |
| src/model_eligibility.py | Elegibilidade e recomendações por recursos | Médio |
| src/hf_discovery.py | Descoberta de candidatos GGUF no Hugging Face | Baixo |
| src/ui/index.html | Interface e integração com endpoints | Médio |
| data/profiles.json | Perfis históricos | Elevado |

Esta tabela é inventário preliminar, não certificação de qualidade.

## 3. Baseline de inferência observada

Na referência publicada:
- UI local usa a porta 8080 por omissão.
- llama-server usa a porta 8089 por omissão.
- O contexto inicial está definido em 2048.
- A execução identificada usa -ngl 0.
- O número de threads tem um valor por omissão calculado a partir dos processadores lógicos, limitado a quatro.
- A descoberta de modelos percorre ficheiros GGUF.
- A identificação Qwen3VL depende do nome e da procura de um ficheiro mmproj correspondente.
- A aplicação verifica saúde e identidade do modelo no servidor.
- A configuração de threads de um perfil de calibração é consumida no carregamento do modelo.
- O endpoint da aplicação está associado a 127.0.0.1 na configuração observada.

Estes valores são características da implementação actual, não decisões universais da nova arquitectura.

## 4. Testes de caracterização obrigatórios

Antes de extrair ou substituir componentes, criar testes que registem o comportamento actual.

### Runtime e inferência
1. Descoberta do executável correcto por plataforma.
2. Arranque do servidor com argumentos esperados.
3. Health check.
4. Verificação de identidade do modelo carregado.
5. Pedido simples de inferência.
6. Pedidos repetidos.
7. Pedido próximo do limite de contexto.
8. Tratamento de timeout e falha de processo.
9. Encerramento do processo.
10. Libertação da porta.
11. Recuperação após encerramento inesperado.
12. Comportamento com dependências multimodais em falta.

### API
1. Contratos e códigos HTTP existentes.
2. Validação de pedidos.
3. Respostas de erro.
4. Estado do runtime e do modelo.
5. Compatibilidade dos endpoints usados pela UI.
6. Streaming, se exposto pela versão efectiva da aplicação.
7. Cancelamento, se suportado pela implementação efectiva.

### Critério
Os testes devem utilizar um modelo real pequeno e o runtime efectivamente distribuído. Testes simulados são complementares, não substitutos dos testes reais.

## 5. Baseline de calibração observada

A implementação identificada em src/calibration.py:
- Executa llama-bench para medir configurações de threads.
- Aguarda condições de inactividade da aplicação.
- Monitoriza memória livre e possui limiar de emergência.
- Pode interromper ou adiar quando a aplicação fica ocupada.
- Executa três pedidos de inferência na validação operacional identificada.
- Persiste o perfil usando ficheiro temporário e os.replace.
- Calcula fingerprints do modelo, benchmark, bibliotecas ggml e dados de hardware/configuração.
- Não inclui explicitamente llama-server.exe no fingerprint observado.
- Explora principalmente threads; outros parâmetros não são ainda optimizados de forma abrangente.
- A validação operacional não constitui avaliação semântica de qualidade.

O perfil actual é consumido pela inferência pelo menos no parâmetro de threads. A cobertura de outros parâmetros deverá ser medida antes de se definir equivalência.

## 6. Testes de não regressão da calibração

1. Executar calibração na versão de referência.
2. Registar ambiente, modelo, runtime e configuração.
3. Guardar todos os resultados de benchmark.
4. Confirmar validação operacional com os pedidos reais.
5. Confirmar persistência atómica.
6. Reiniciar a aplicação e carregar o perfil.
7. Confirmar que a inferência consome a configuração validada.
8. Alterar o modelo e confirmar que o perfil anterior não é aplicado indevidamente.
9. Alterar binários relevantes do runtime e confirmar invalidação adequada.
10. Interromper calibração e verificar recuperação.
11. Simular memória insuficiente e confirmar paragem segura.
12. Utilizar a aplicação durante a calibração e confirmar que não há degradação perigosa.
13. Confirmar que perfis anteriores continuam disponíveis para rollback.

A validação semântica da qualidade será adicionada como camada independente; não deve ser atribuída retroactivamente aos perfis antigos.

## 7. Migração de perfis

O ficheiro data/profiles.json contém um perfil histórico com esquema v1, enquanto o código actual identifica PROFILE_SCHEMA = 2.

Regras:
- Preservar o original.
- Detectar e registar o esquema de origem.
- Converter apenas campos com correspondência inequívoca.
- Marcar dados incompletos ou sem validação como legacy.
- Não inferir medições em falta.
- Não promover perfis legacy para validated.
- Exportar relatório de migração.
- Permitir rollback.
- Separar perfis de exemplo dos perfis reais do utilizador.

## 8. Migração incremental

| Etapa | Alteração | Gate obrigatório |
|---|---|---|
| M0 | Congelar referência e dados | Commit, hashes, backups e testes de referência |
| M1 | Definir contratos | Revisão e aprovação das interfaces |
| M2 | Criar testes de caracterização | Testes reproduzem comportamento actual |
| M3 | Extrair configuração/persistência | Inferência inalterada |
| M4 | Introduzir adaptador llama.cpp | Testes de inferência equivalentes |
| M5 | Extrair Model Registry | Descoberta e carregamento preservados |
| M6 | Integrar calibração por contrato | Perfis continuam legíveis e consumidos |
| M7 | Versionar fingerprints e perfis | Migração e rollback testados |
| M8 | Separar benchmark e qualidade | Métricas e avaliações independentes |
| M9 | Introduzir runtime adicional | Compatibilidade demonstrada sem afectar llama.cpp |
| M10 | Remover legado redundante | Apenas depois de equivalência e período de observação |

Não executar simultaneamente alterações estruturais em inferência e calibração.

## 9. Critérios de equivalência

A equivalência deve considerar:
- Mesmos modelos e artefactos.
- Mesmo hardware e ambiente.
- Mesma versão do runtime, excepto quando a alteração é o objecto do teste.
- Mesma configuração funcional.
- Respostas válidas e comportamento dos endpoints.
- Tempos dentro de tolerâncias justificadas por medições repetidas.
- Ausência de regressão de memória, estabilidade e qualidade.

Não exigir igualdade exacta de latência entre execuções.

## 10. Rollback

Cada migração deverá possuir:
- Identificador de versão anterior.
- Backup dos dados afectados.
- Plano de reversão de esquema.
- Testes da implementação anterior.
- Critérios objectivos de rollback.
- Registo de resultados e decisão.

Os modelos originais nunca devem ser alterados pela calibração. Os perfis e bases de dados devem ser copiados antes de migrações de esquema.

## 11. Condições que bloqueiam a migração

Bloquear a migração quando:
- A baseline local não corresponde à referência analisada e a diferença não está explicada.
- Não existem testes reais de inferência.
- Não se consegue ler os perfis existentes.
- A nova implementação não consome a configuração de calibração esperada.
- A API usada pela UI deixa de ser compatível sem plano de transição.
- Não existe rollback testado.
- A segurança ou integridade dos dados fica comprometida.

## 12. Resultado esperado

A migração é aceite apenas quando a nova estrutura oferece os mesmos resultados funcionais relevantes, preserva os dados, mantém a calibração utilizável e demonstra que as novas fronteiras arquitecturais não introduzem regressões.
