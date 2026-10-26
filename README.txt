AdaptiveLocalAI-Portable — Etapa 1: reorganização da interface

CONTEÚDO
- payload/src/ui/index.html: interface atualizada, baseada no index.html fornecido para auditoria.
- payload/tests/test_ui_stage1.py: testes específicos da interface da Etapa 1.
- install.ps1: cria backup, instala o HTML e executa os testes; reverte automaticamente se falharem.
- rollback.ps1: repõe o HTML anterior a partir do backup da Etapa 1.

INSTALAÇÃO
1. Extrair o conteúdo deste ZIP diretamente para a raiz do projeto:
   D:\Dev\Python\AdaptiveLocalAI-Portable
   (A pasta payload e os scripts install.ps1/rollback.ps1 devem ficar nessa raiz.)
2. Abrir PowerShell na raiz do projeto.
3. Executar: .\install.ps1
4. Confirmar que o pytest termina com todos os testes aprovados.

REVERSÃO
Na raiz do projeto, executar:
.\rollback.ps1 -ProjectRoot "D:\Dev\Python\AdaptiveLocalAI-Portable"

ESCOPO E LIMITAÇÕES DESTA ETAPA
- Reorganiza a navegação lateral e o compositor; o seletor continua ligado ao mesmo código de carregamento de modelos.
- Mantém o endpoint de streaming, o gestor de modelos, a apresentação de blocos de código, a cópia de código, a barra lateral ajustável e os painéis recolhíveis.
- O botão de anexos é intencionalmente desativado: anexos ainda não estão integrados.
- Histórico persistente, projetos persistentes e agentes não são implementados nesta etapa. Os respetivos itens de navegação informam que são etapas futuras.
- Não altera src/app.py, os modelos, runtime, perfis nem o estado de instalação.

TESTES
O instalador executa:
py -3.12 -m pytest .\tests -v --import-mode=importlib
A opção limita a recolha aos testes do projeto e evita conflito de importação com cópias guardadas em backups.
