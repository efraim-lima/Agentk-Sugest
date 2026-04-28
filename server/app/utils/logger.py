"""
Logger do AgentK Server.

Importa a configuração central e expõe um logger pronto para uso
em todos os módulos do servidor.

Uso:
    from utils.logger import logger
    logger.info("Servidor iniciado na porta %s", port)
    logger.debug("Parâmetros recebidos: %s", params)
    logger.warning("Tentativa com configuração inexistente")
    logger.error("Falha ao aplicar recurso: %s", err)
    logger.critical("Processo Kubernetes inacessível")
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

LOG_FILE = os.getenv("AGENTK_SERVER_LOG_FILE", "agentk-server.log")

logger = get_logger("agentk.server", LOG_FILE)
