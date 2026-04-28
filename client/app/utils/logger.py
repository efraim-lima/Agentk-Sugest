"""
Logger do AgentK Client.

Importa a configuração central e expõe um logger pronto para uso
em todos os módulos do cliente.

Uso:
    from utils.logger import logger
    logger.info("Conexão MCP estabelecida com %s", host)
    logger.debug("Ferramentas disponíveis: %s", tools)
    logger.warning("Sessão MCP não inicializada; reconectando")
    logger.error("Chamada de ferramenta falhou: %s", err)
    logger.critical("Serviço LLM inacessível")
"""

import os
import sys

# Busca o diretório 'logs' subindo na estrutura de pastas
def _add_logs_to_path():
    current = os.path.abspath(os.path.dirname(__file__))
    for _ in range(5):
        if os.path.isdir(os.path.join(current, "logs")):
            if current not in sys.path:
                sys.path.insert(0, current)
            return
        current = os.path.dirname(current)

_add_logs_to_path()

from logs.logging_config import get_logger, format_audit_log  # noqa: E402

LOG_FILE = os.getenv("AGENTK_CLIENT_LOG_FILE", "agentk-client.log")

logger = get_logger("agentk.client", LOG_FILE)
