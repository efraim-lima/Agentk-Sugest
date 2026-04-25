# Alterações de Logging do Ambiente AgentK

Data: 2026-04-24

## Objetivo
Centralizar e padronizar os logs do cliente e do servidor, com suporte a níveis de log (DEBUG, INFO, WARNING, ERROR, CRITICAL), gravação em arquivo de sistema e rotação de arquivos.

## Arquivos criados

### 1) logs/logging_config.py
Configuração centralizada de logging para todo o projeto.

Implementado:
- Leitura de variáveis de ambiente:
  - AGENTK_LOG_LEVEL
  - AGENTK_LOG_DIR
  - AGENTK_LOG_MAX_MB
  - AGENTK_LOG_BACKUPS
- Resolução de diretório de log:
  - Prioriza AGENTK_LOG_DIR
  - Tenta /var/log/agentk
  - Fallback para diretório local logs/
- Formato padrão de log com timestamp + nível + logger + mensagem
- Handlers:
  - stdout
  - arquivo com rotação (RotatingFileHandler)
- Função pública get_logger(name, log_file)

### 2) server/app/utils/logger.py
Wrapper de logger do servidor.

Implementado:
- Ajuste de path para importar a configuração central em logs/logging_config.py
- Definição de arquivo padrão:
  - AGENTK_SERVER_LOG_FILE (default: agentk-server.log)
- Exposição de logger com nome agentk.server

### 3) client/app/utils/logger.py
Wrapper de logger do cliente.

Implementado:
- Ajuste de path para importar a configuração central em logs/logging_config.py
- Definição de arquivo padrão:
  - AGENTK_CLIENT_LOG_FILE (default: agentk-client.log)
- Exposição de logger com nome agentk.client

## Arquivos alterados

### 4) server/app/main.py
Refatoração do logging antigo para o novo modelo centralizado.

Alterações:
- Removido logging.basicConfig local
- Removido FileHandler local mcp_server.log
- Adicionado import do logger central:
  - from utils.logger import logger

Impacto:
- Servidor passa a usar configuração única e controlada por variáveis de ambiente

### 5) client/app/classes/mcp_client.py
Substituição do debug manual por logging estruturado.

Alterações:
- Removido método _debug_log que gravava em client.log
- Removida flag booleana _debug
- Adicionado import do logger central:
  - from app.utils.logger import logger
- Adicionados logs de operação nos métodos principais:
  - initialize_with_stdio
  - initialize_with_http
  - get_tools
  - get_resources
  - get_prompts
  - call_tool (com tratamento de erro e logger.error)
  - get_resource
  - invoke_prompt
  - cleanup

Impacto:
- Cliente passa a registrar eventos relevantes com níveis apropriados

### 6) docker-compose.yml
Configuração de persistência e compartilhamento de logs no ambiente containerizado.

Alterações no serviço agentk-server:
- Variáveis adicionadas:
  - AGENTK_LOG_LEVEL
  - AGENTK_LOG_DIR=/var/log/agentk
  - AGENTK_LOG_MAX_MB
  - AGENTK_LOG_BACKUPS
  - AGENTK_SERVER_LOG_FILE=agentk-server.log
- Volume adicionado:
  - agentk-logs:/var/log/agentk

Alterações no serviço agentk-client:
- Variáveis adicionadas:
  - AGENTK_LOG_LEVEL
  - AGENTK_LOG_DIR=/var/log/agentk
  - AGENTK_LOG_MAX_MB
  - AGENTK_LOG_BACKUPS
  - AGENTK_CLIENT_LOG_FILE=agentk-client.log
- Volume adicionado:
  - agentk-logs:/var/log/agentk

Resultado:
- Cliente e servidor gravam logs no mesmo diretório de sistema dentro do container
- Persistência via volume Docker agentk-logs

## Níveis de log contemplados
- DEBUG
- INFO
- WARNING
- ERROR
- CRITICAL

## Diretório de logs
Prioridade de destino:
1. AGENTK_LOG_DIR (quando definido)
2. /var/log/agentk (quando disponível e gravável)
3. logs/ local do projeto (fallback)

## Rotação de logs
Implementada via RotatingFileHandler:
- Tamanho máximo por arquivo: AGENTK_LOG_MAX_MB (default 10 MB)
- Quantidade de backups: AGENTK_LOG_BACKUPS (default 5)

## Observações
- O arquivo central de configuração permite controle fino de emissão sem alterar código-fonte.
- A separação por arquivo (agentk-server.log e agentk-client.log) facilita troubleshooting.
- Logs continuam sendo emitidos no stdout, útil para observabilidade com docker logs.
