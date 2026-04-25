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

# Garante que o diretório raiz do projeto (onde está a pasta logs/) esteja no path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from logs.logging_config import get_logger  # noqa: E402

LOG_FILE = os.getenv("AGENTK_CLIENT_LOG_FILE", "agentk-client.log")

logger = get_logger("agentk.client", LOG_FILE)
