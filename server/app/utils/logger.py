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

# Garante que o diretório raiz do projeto (onde está a pasta logs/) esteja no path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from logs.logging_config import get_logger  # noqa: E402

LOG_FILE = os.getenv("AGENTK_SERVER_LOG_FILE", "agentk-server.log")

logger = get_logger("agentk.server", LOG_FILE)
