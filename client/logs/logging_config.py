"""
Configuração centralizada de logging para o AgentK.

Níveis suportados (do menos ao mais crítico):
  DEBUG    - Detalhes de diagnóstico para desenvolvimento
  INFO     - Confirmações de operações normais
  WARNING  - Algo inesperado aconteceu, mas a aplicação segue funcionando
  ERROR    - Erro grave; parte da funcionalidade foi prejudicada
  CRITICAL - Falha grave; a aplicação pode não conseguir continuar

Variáveis de ambiente que controlam o comportamento:
  AGENTK_LOG_LEVEL   - Nível mínimo a registrar (default: DEBUG)
  AGENTK_LOG_DIR     - Diretório de destino dos arquivos de log
                       Em container: /var/log/agentk  (via volume)
                       Em execução local: ./logs
  AGENTK_LOG_MAX_MB  - Tamanho máximo de cada arquivo antes de rotacionar (default: 10)
  AGENTK_LOG_BACKUPS - Quantos arquivos de backup manter após rotação (default: 5)
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path


# ─── Parâmetros configuráveis via variável de ambiente ───────────────────────

def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


LOG_LEVEL_NAME: str = _env("AGENTK_LOG_LEVEL", "DEBUG").upper()
LOG_LEVEL: int = getattr(logging, LOG_LEVEL_NAME, logging.DEBUG)

# Diretório de logs: prioriza variável de ambiente, depois /var/log/agentk se
# gravável (dentro do container com volume montado), senão usa ./logs local.
def _resolve_log_dir() -> Path:
    env_dir = _env("AGENTK_LOG_DIR", "")
    if env_dir:
        return Path(env_dir)
    system_dir = Path("/var/log/agentk")
    try:
        system_dir.mkdir(parents=True, exist_ok=True)
        # Teste de permissão de escrita
        test_file = system_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
        return system_dir
    except (PermissionError, OSError):
        # Fallback: diretório logs/ relativo ao arquivo de configuração
        fallback = Path(__file__).parent
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


LOG_DIR: Path = _resolve_log_dir()
LOG_MAX_BYTES: int = int(_env("AGENTK_LOG_MAX_MB", "10")) * 1024 * 1024
LOG_BACKUP_COUNT: int = int(_env("AGENTK_LOG_BACKUPS", "5"))

# ─── Formato das mensagens ────────────────────────────────────────────────────

FORMATTER = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _rotating_file_handler(filename: str) -> logging.handlers.RotatingFileHandler:
    """Cria um RotatingFileHandler apontando para LOG_DIR/filename."""
    log_path = LOG_DIR / filename
    handler = logging.handlers.RotatingFileHandler(
        filename=str(log_path),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(FORMATTER)
    return handler


def _stdout_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(FORMATTER)
    return handler


# ─── Função pública ───────────────────────────────────────────────────────────

def get_logger(name: str, log_file: str | None = None) -> logging.Logger:
    """
    Retorna um logger configurado com os handlers de arquivo e stdout.

    Args:
        name:     Nome do logger (geralmente __name__ do módulo chamador).
        log_file: Nome do arquivo de log a usar (ex.: "agentk-server.log").
                  Se None, o arquivo não é criado e os logs vão apenas para stdout.

    Returns:
        logging.Logger configurado e pronto para uso.

    Exemplo:
        from logs.logging_config import get_logger
        logger = get_logger(__name__, "agentk-server.log")
        logger.info("Servidor iniciado")
        logger.debug("Valor da variável x=%s", x)
        logger.warning("Configuração ausente, usando padrão")
        logger.error("Falha ao conectar: %s", err)
        logger.critical("Estado inconsistente; encerrando")
    """
    logger = logging.getLogger(name)

    # Evita adicionar handlers duplicados em re-importações
    if logger.handlers:
        return logger

    logger.setLevel(LOG_LEVEL)

    logger.addHandler(_stdout_handler())

    if log_file:
        try:
            logger.addHandler(_rotating_file_handler(log_file))
        except (PermissionError, OSError) as exc:
            logger.warning(
                "Não foi possível criar arquivo de log '%s' em '%s': %s. "
                "Logs serão emitidos apenas no stdout.",
                log_file, LOG_DIR, exc,
            )

    # Não propaga para o root logger para evitar duplicação
    logger.propagate = False

    return logger
