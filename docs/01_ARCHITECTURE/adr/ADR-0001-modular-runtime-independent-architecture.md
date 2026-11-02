# ADR-0001 — Arquitectura modular e independência de runtime

- Estado: Proposed
- Data: 2026-11-02
- Âmbito: Arquitectura global

## Contexto

A plataforma deve suportar diferentes modelos, formatos, runtimes e sistemas operativos. Acoplamento directo da aplicação a comandos ou estruturas internas de um runtime dificulta a portabilidade e a evolução.

## Proposta

Adoptar arquitectura modular em camadas, com contratos públicos para Runtime Adapter, Model Manager, Inference Service, Hardware Intelligence e Calibration Service. O núcleo não depende de um runtime específico.

llama.cpp é o primeiro adaptador de referência. MLC LLM permanece experimental. Outros runtimes são avaliados individualmente.

## Alternativas

1. Acoplamento directo a llama.cpp.
2. Abstracção comum com adaptadores.
3. Um runtime obrigatório para todas as plataformas.

## Justificação

A opção 2 reduz dependências cruzadas e permite seleccionar motores conforme plataforma, formato e hardware. O custo é manter contratos e testes de compatibilidade.

## Consequências

- Os consumidores usam serviços comuns.
- Adaptadores declaram capacidades reais.
- Funcionalidades opcionais não são simuladas.
- A introdução de runtimes exige testes de contrato.
- A decisão final depende da aprovação da F1.
