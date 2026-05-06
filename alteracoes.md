# ANEXO A — RELATÓRIO TÉCNICO DE EVOLUÇÃO E IMPLEMENTAÇÃO DE SEGURANÇA NO ECOSSISTEMA AGENTK

Este documento detalha as modificações estruturais, lógicas e de segurança implementadas no projeto AgentK, visando a consolidação de um ambiente de orquestração de Kubernetes assistido por Inteligência Artificial (IA) com foco em conformidade, auditoria e controle de acesso granular.

## 1. ARQUITETURA DE AUTENTICAÇÃO E GESTÃO DE SESSÃO

A segurança de borda do ecossistema AgentK foi reforçada através da integração estrita com o protocolo OpenID Connect (OIDC) via Keycloak. A implementação focou na idempotência da sessão e na facilidade de encerramento de acesso (logout).

### 1.1 Implementação de Logout Centralizado

Para garantir que o encerramento da sessão ocorra tanto no provedor de identidade (Keycloak) quanto no proxy de autenticação (OAuth2 Proxy), foi desenvolvido um fluxo de redirecionamento coordenado. O código abaixo ilustra a montagem dinâmica das URLs de sign-out no cliente Streamlit:

```python
# Arquivo: client/app/main.py | Linha: 33
keycloak_logout_base = "https://agentk.local/keycloak/realms/agentk/protocol/openid-connect/logout"
post_logout_uri = "https://agentk.local/"
client_id = "oauth2-proxy"

params = {
    "client_id": client_id,
    "post_logout_redirect_uri": post_logout_uri
}
keycloak_logout_url = f"{keycloak_logout_base}?{urllib.parse.urlencode(params)}"
logout_url = f"/oauth2/sign_out?rd={urllib.parse.quote(keycloak_logout_url)}"
```

Este mecanismo assegura a invalidação de cookies locais e tokens de sessão remotos, mitigando riscos de sequestro de sessão após o uso do terminal.

## 2. MODERNIZAÇÃO DA CAMADA DE VALIDAÇÃO (GUARDRAIL)

O componente **Gateway**, responsável pela inspeção semântica de prompts, evoluiu de um modelo de processamento síncrono para uma arquitetura assíncrona baseada em filas e *long-polling*.

### 2.1 Processamento Assíncrono e Resiliência

A transição para o modelo assíncrono permite que o sistema gerencie latências elevadas do modelo de linguagem (LLM) local (Ollama) sem causar interrupções por *timeout* na conexão HTTP do cliente. O fluxo baseia-se em dois estágios: submissão e consulta de resultado.

```python
# Arquivo: client/app/services/chat_service.py | Linha: 280
submit_response = requests.post(gateway_url, json={"prompt": ultimo_prompt}, timeout=30)
if submit_response.status_code == 202:
    job_id = submit_response.json().get("job_id")
    result_url = f"https://agentk-gateway:8080/resultado/{job_id}"
    # Long-poll aguardando o veredito do Ollama
    result_response = requests.get(result_url, timeout=130)
    dados_gateway = result_response.json()
```

Esta mudança estrutural elevou a capacidade do sistema de lidar com picos de requisições e períodos de alta carga computacional no motor de inferência, garantindo que o veredito de segurança seja sempre obtido antes da execução da tarefa.

## 3. SISTEMA DE AUDITORIA E CONFORMIDADE FORENSE

Em conformidade com normas de segurança da informação, implementou-se um padrão de registro de eventos (logging) centralizado e rotulado, facilitando a ingestão por ferramentas de SIEM (*Security Information and Event Management*).

### 3.1 Padronização de Mensagens de Auditoria

Todas as ações críticas, desde validações de prompt até comandos de infraestrutura no Kubernetes, são registradas seguindo um esquema rígido de metadados em UTC:

```python
# Arquivo: client/logs/logging_config.py | Linha: 596
def format_audit_log(actor, action, resource, outcome, source_ip, context_data="N/A"):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"Timestamp: {timestamp} "
        f"Actor/User Identification: {actor} "
        f"Action/Event Type: {action} "
        f"Object/Resource: {resource} "
        f"Outcome: {outcome} "
        f"Source IP Address: {source_ip} "
        f"Contextual Data: {context_data}"
    )
```

Este padrão garante a rastreabilidade inequívoca das intenções do usuário e das respostas do sistema, permitindo auditorias retrospectivas detalhadas sobre o uso da IA no gerenciamento do cluster.

### 3.2 Auditoria de Operações Críticas no Servidor

A camada de servidor (AgentK-Server) também foi equipada com telemetria para registrar ações diretas no cluster Kubernetes, como a aplicação de manifestos YAML e a deleção de recursos:

```python
# Arquivo: server/app/main.py | Linha: 890
logger.info(format_audit_log(
    actor="AgentK-Server",
    action="APPLY_YAML",
    resource=f"namespace/{namespace}",
    outcome="STARTED",
    context_data=f"content_size={len(yaml_content)} chars"
))
```

### 3.3 Auditoria de Chamadas de Ferramentas (Tools)

O rastreamento de quando a IA invoca ferramentas externas para interagir com o cluster é fundamental para a integridade do sistema:

```python
# Arquivo: client/app/services/chat_service.py | Linha: 169
self.logger.info(format_audit_log(
    actor=ctx["user"],
    action="TOOL_CALL",
    resource=call.function.name,
    outcome="STARTED",
    source_ip=ctx["ip"],
    context_data=f"args={call.function.arguments}"
))
```

### 3.4 Auditoria de Remoção de Recursos

Operações destrutivas no servidor são registradas com nível de severidade `WARNING` para destacar ações de alto impacto:

```python
# Arquivo: server/app/main.py | Linha: 925
logger.warning(format_audit_log(
    actor="AgentK-Server",
    action="DELETE_RESOURCE",
    resource=f"{resource_type}/{name}",
    outcome="STARTED",
    context_data=f"namespace={namespace}"
))
```

## 4. GOVERNANÇA DE AÇÕES DE ALTO RISCO (PAM)

Introduziu-se o conceito de **Privileged Access Management (PAM)** dentro do fluxo de conversação. Prompts que solicitam ações tecnicamente válidas, porém perigosas (ex: deleção de recursos), recebem o veredito `RISKY`.

### 4.1 Autorização Delegada via Keycloak

Diferente de ações categorizadas como `UNSAFE` (bloqueadas permanentemente), as ações `RISKY` permitem a continuidade do fluxo mediante re-autenticação administrativa. O sistema invoca um diálogo de autorização que valida as credenciais diretamente no Keycloak:

```python
# Arquivo: client/app/services/chat_service.py | Linha: 211
@st.dialog("Ação Restrita: Risco Detectado")
def _show_risky_auth_dialog(self):
    st.warning("⚠️ O Gateway classificou esta ação como RISKY. Necessário privilégio administrativo.")
    password = st.text_input("Senha de Administrador (Keycloak)", type="password")
    if st.button("Autorizar"):
        if self._verify_keycloak_password(password):
            st.session_state.risky_authorized_pending_llm = True
            st.rerun()
```

Esta abordagem equilibra a agilidade operacional com a segurança necessária para operações críticas em ambientes de produção.

## 5. SINCRONIZAÇÃO PARA AUTOMAÇÃO DE TESTES (DOM SIGNALS)

Para viabilizar a validação em massa através de ferramentas de *crawling* e testes automatizados, implementou-se um mecanismo de sinalização via atributos de DOM. O sistema AgentK agora sinaliza explicitamente sua prontidão para o próximo comando:

```python
# Arquivo: client/app/main.py | Linha: 82
st.components.v1.html("<script>window.parent.document.body.removeAttribute('data-agentk-ready');</script>", height=0)
```

Este sinal é capturado por robôs de teste (ex: Playwright), eliminando estados de corrida (*race conditions*) e garantindo a integridade dos dados coletados durante os experimentos.

## 6. INFRAESTRUTURA E EMPACOTAMENTO EM CONTAINERS

A robustez da solução é sustentada por uma infraestrutura baseada em Docker, garantindo portabilidade e isolamento. As modificações incluíram o provisionamento automático de módulos de log e a orquestração via Docker Compose.

### 6.1 Gestão de Logs em Dockerfiles

Os manifestos de construção foram atualizados para garantir que o módulo de logging centralizado seja injetado corretamente em todos os microsserviços:

```dockerfile
# Arquivo: client/Dockerfile | Linha: 12
COPY logs/ ./app/logs/
```

### 6.2 Estética e UX: Interface de Logout

Além da funcionalidade lógica, a interface recebeu melhorias estéticas para facilitar a interação do usuário, como o botão de logout flutuante com efeitos de vidro (*glassmorphism*):

```css
# Arquivo: client/app/ui/styles/main.css | Linha: 438
.logout-button {
    position: fixed;
    top: 15px;
    right: 15px;
    z-index: 999999;
}
```

### 6.3 Orquestração e Conectividade de Rede

O arquivo `docker-compose.yml` foi otimizado para permitir a comunicação via HTTPS interno entre o cliente Streamlit e o Gateway Java, utilizando variáveis de ambiente para definir os endpoints de validação:

```yaml
# Arquivo: docker-compose.yml | Linha: 723
- GATEWAY_VALIDATE_URL=${GATEWAY_VALIDATE_URL:-https://agentk-gateway:8080/validar}
```

## 7. CONCLUSÃO

As alterações apresentadas transformam o AgentK em uma plataforma robusta para a operação de Kubernetes assistida por IA. A combinação de autenticação centralizada, validação semântica assíncrona, auditoria detalhada e governança de risco forma uma camada de defesa em profundidade (*Defense in Depth*), essencial para a mitigação de ataques de *Prompt Injection* e erros operacionais catastróficos.
