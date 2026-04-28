import sys
import os

# Adicionar caminhos necessários
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)

from logs.logging_config import get_logger, format_audit_log

def test_audit_logs():
    logger = get_logger("test.audit", "test-audit.log")
    
    # Teste de formatação
    log_msg = format_audit_log(
        actor="test-user",
        action="TEST_ACTION",
        resource="test-resource",
        outcome="SUCCESS",
        source_ip="127.0.0.1",
        context_data="test-context"
    )
    
    print("Formatted message:")
    print(log_msg)
    
    logger.info(log_msg)
    print("\nLog written to Agentk-Sugest/logs/test-audit.log")

if __name__ == "__main__":
    test_audit_logs()
