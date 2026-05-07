from typing import Optional, Dict, Any
import os
from app.classes.llm_client import LLmClient
from app.classes.mcp_client import McpClient
from app.ui.components.chat_interface import ChatInterface
from app.core.async_utils import run_task
from app.config import settings
from app.services.export_service import ExportService
import streamlit as st
import json
import datetime
import time
import urllib.parse
import requests

from app.utils.logger import logger, format_audit_log

class ChatService:
    """
    Service for managing chat interactions, with support for tool execution.
    """
    
    def __init__(self, llm_client: LLmClient):
        self.llm_client = llm_client
        self.chat_interface = ChatInterface()
        self.logger = logger
        # Usa um serviço de exportação compartilhado na sessão
        if 'export_service' not in st.session_state:
            st.session_state.export_service = ExportService()
        self.export_service = st.session_state.export_service

    def _get_user_context(self) -> dict:
        """Extrai a identidade do usuário e IP dos headers ou contexto Streamlit."""
        context = {
            "user": os.environ.get("USER", "anonymous"),
            "ip": "unknown"
        }
        try:
            # Streamlit 1.34+ headers
            if hasattr(st, 'context'):
                h = st.context.headers
                context["user"] = h.get('X-Forwarded-Email', h.get('X-Forwarded-User', context["user"]))
                context["ip"] = h.get('X-Forwarded-For', h.get('X-Real-IP', "unknown"))
        except Exception:
            pass
        return context

    def _get_user_info(self) -> str:
        """Mantido para compatibilidade simples, extrai apenas o ID do usuário."""
        return self._get_user_context()["user"]

    def process_single_tool_call(self, call) -> None:
        try:
            # Registra o início da chamada da ferramenta
            tool_start_time = self.export_service.record_request_start()
            
            async def do_call():
                client = McpClient()
                
                # Verificar se deve usar HTTP/SSE ou stdio
                mcp_server_url = os.getenv("MCP_SERVER_URL")
                
                if mcp_server_url:
                    # Modo container/HTTP - conectar via SSE
                    await client.initialize_with_http(mcp_server_url)
                else:
                    # Modo local/desenvolvimento - usar stdio
                    await client.initialize_with_stdio("mcp", ["run", settings.TOOL_PATH])

                tool_result = await client.call_tool(
                    call.function.name,
                    json.loads(call.function.arguments)
                )

                await client.cleanup()
                return tool_result

            ctx = self._get_user_context()
            self.logger.info(format_audit_log(
                actor=ctx["user"],
                action="TOOL_CALL",
                resource=call.function.name,
                outcome="STARTED",
                source_ip=ctx["ip"],
                context_data=f"args={call.function.arguments}"
            ))
            
            call_result = run_task(do_call())
            
            # Registra o fim da chamada da ferramenta
            self.export_service.record_request_end(tool_start_time)
            
            result_text = ''.join(item.text for item in call_result.content if item.type == 'text')
            self.logger.info(format_audit_log(
                actor=ctx["user"],
                action="TOOL_RESULT",
                resource=call.function.name,
                outcome="SUCCESS",
                source_ip=ctx["ip"]
            ))
            return result_text
        except Exception as e:
            ctx = self._get_user_context()
            self.logger.error(format_audit_log(
                actor=ctx["user"],
                action="TOOL_RESULT",
                resource=call.function.name,
                outcome="ERROR",
                source_ip=ctx["ip"],
                context_data=f"error={str(e)}"
            ))
            return f"Error calling tool: {str(e)}"
    
    def resolve_chat(self, response):
        llm_client = st.session_state.llm_client
        tools = st.session_state.tools

        if response.choices[0].finish_reason == 'tool_calls':
            tool_reply = response.choices[0].message.content 

            # Só exibe a mensagem do assistente se houver conteúdo não-vazio
            if tool_reply is not None and tool_reply.strip():
                with st.chat_message("assistant"):
                    st.markdown(tool_reply)

            calls = response.choices[0].message.tool_calls  

            llm_client.add_assistant_message({
                "content": tool_reply,
                "tool_calls": calls,
                "role": "assistant"
            })

            for call in calls:
                with st.chat_message(name="tool", avatar=":material/build:"):
                    st.markdown(f'LLM chamando tool {call.function.name}')
                    with st.expander("Visualizar argumentos"):
                        st.code(call.function.arguments)

                with st.spinner(f"Processando chamada para {call.function.name}..."):
                    result = self.process_single_tool_call(call)

                with st.chat_message(name="tool", avatar=":material/data_object:"):
                    with st.expander("Visualizar resposta"):
                        st.code(result)

                llm_client.add_tool_message({
                    "tool_call_id": call.id,
                    "content": result,
                    "role": "tool"
                })

            with st.spinner("Gerando resposta final..."):
                next_response = llm_client.complete_chat(tools)

            self.resolve_chat(next_response)

        else:
            assistant_reply = response.choices[0].message.content

            with st.chat_message("assistant"):
                st.markdown(assistant_reply)

            llm_client.add_assistant_message({
                "content": assistant_reply,
                "role": "assistant"
            })
            
            # Incrementa contador de mensagens
            if 'message_count' not in st.session_state:
                st.session_state.message_count = 0
            st.session_state.message_count += 1
            
            # Registra timestamp da mensagem do assistente
            self.export_service.record_message_timestamp(st.session_state.message_count)

    @st.dialog("Ação Restrita: Risco Detectado")
    def _show_risky_auth_dialog(self):
        st.warning("⚠️ O Gateway classificou esta ação como RISKY. Necessário privilégio administrativo.")
        password = st.text_input("Senha de Administrador (Keycloak)", type="password")
        if st.button("Autorizar"):
            if self._verify_keycloak_password(password):
                st.success("Autorizado com sucesso!")
                st.session_state.risky_authorized_pending_llm = True
                st.rerun()
            else:
                st.error("Senha inválida ou falha na autenticação.")

    def _verify_keycloak_password(self, password: str) -> bool:
        try:
            token_url = "http://keycloak:8080/realms/agentk/protocol/openid-connect/token"
            admin_user = os.environ.get("KEYCLOAK_ADMIN", "admin")
            
            # Tenta autenticar usando o client admin-cli que por padrão permite password grant
            data = {
                "client_id": "admin-cli",
                "grant_type": "password",
                "username": admin_user,
                "password": password
            }
            
            response = requests.post(token_url, data=data, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def render_chat_history(self) -> None:
        """Render the complete chat history."""
        for message in st.session_state.llm_client.history:
            if message["role"] != "tool":
                # Só renderiza a mensagem se houver conteúdo válido
                content = message.get("content", "")
                if content and content.strip():
                    with st.chat_message(message["role"]):
                        st.markdown(content)

                if message["role"] == 'assistant' and "tool_calls" in message and message["tool_calls"]:
                    for call in message["tool_calls"]:
                        with st.chat_message(name="tool", avatar=":material/build:"):
                            st.markdown(f'LLM chamando tool {call.function.name}')
                            with st.expander("Visualizar resultado"):
                                st.code(call.function.arguments)
            else:
                with st.chat_message(name="tool", avatar=":material/data_object:"):
                    with st.expander("Visualizar resposta"):
                        st.code(message["content"])
    
    def process_llm_request(self, tools=[]):
        """
        Processa requisição com validação de integridade e veredito via JSON.
        Versão de Teste: Bypassa OpenAI e exibe apenas o veredito do Gateway.
        """
        ultimo_prompt = ""
        for message in reversed(self.llm_client.history):
            if message.get("role") == "user":
                ultimo_prompt = message.get("content")
                break

        if ultimo_prompt:
            # Se a requisição RISKY acabou de ser autorizada, pulamos a validação do Gateway e prosseguimos
            # if st.session_state.get("risky_authorized_pending_llm"):
            #     st.session_state.risky_authorized_pending_llm = False
            # else:
            try:
                gateway_url = os.environ.get(
                    "GATEWAY_VALIDATE_URL",
                    "https://agentk-gateway:8080/validar"
                )
                if gateway_url.startswith("http://"):
                    gateway_url = gateway_url.replace("http://", "https://")

                # ---- Step 1: submit assíncrono à fila do Gateway ----
                t_submit_start = time.monotonic()
                submit_response = requests.post(
                    gateway_url,
                    json={"prompt": ultimo_prompt},
                    headers={"X-Test-Flow": "true"},
                    timeout=30,
                    verify=False
                )
                t_submit_elapsed = (time.monotonic() - t_submit_start) * 1000
                self.logger.info(format_audit_log(
                    actor=ctx["user"],
                    action="GATEWAY_SUBMIT",
                    resource="prompt",
                    outcome=str(submit_response.status_code),
                    source_ip=ctx["ip"],
                    context_data=f"elapsed_ms={t_submit_elapsed:.0f}"
                ))

                if submit_response.status_code == 202:
                    submit_data = submit_response.json()
                    job_id = submit_data.get("job_id")

                        # if not job_id:
                        #     raise ValueError("Gateway não retornou um job_id válido.")

                        # Derivar URL do endpoint de resultado a partir da URL de validação
                    parsed_url = urllib.parse.urlparse(gateway_url)
                    result_url = urllib.parse.urlunparse(
                        parsed_url._replace(path=f"/resultado/{job_id}")
                    )

                    # ---- Step 2: long-poll ----
                    t_poll_start = time.monotonic()
                    self.logger.info(format_audit_log(
                        actor=ctx["user"],
                        action="GATEWAY_POLL_START",
                        resource=job_id,
                        outcome="WAITING",
                        source_ip=ctx["ip"],
                        context_data=f"timeout_s=130"
                    ))
                    result_response = requests.get(
                        result_url,
                        headers={"X-Test-Flow": "true"},
                        timeout=130,
                        verify=False
                    )
                    t_poll_elapsed = (time.monotonic() - t_poll_start) * 1000
                    self.logger.info(format_audit_log(
                        actor=ctx["user"],
                        action="GATEWAY_POLL_END",
                        resource=job_id,
                        outcome=str(result_response.status_code),
                        source_ip=ctx["ip"],
                        context_data=f"elapsed_ms={t_poll_elapsed:.0f}"
                    ))
                    dados_gateway = result_response.json()

                        # Tratar caso em que o servidor ainda está processando (timeout do servidor)
                        # if result_response.status_code == 202:
                        #     st.error("⚠️ O Gateway não concluiu o processamento a tempo. Tente novamente.")
                        #     st.session_state.is_processing = False
                        #     st.components.v1.html("<script>window.parent.document.body.setAttribute('data-agentk-ready', 'true');</script>", height=0)
                        #     st.stop()
                else:
                    dados_gateway = submit_response.json()

                veredito = dados_gateway.get("veredito", "").upper()
                prompt_retornado = dados_gateway.get("prompt", "")

                # Verificação de Integridade
                if prompt_retornado != ultimo_prompt:
                    st.error("🚨 Erro de Integridade: O prompt validado divergiu do original.")
                    # st.session_state.is_processing = False
                    # st.components.v1.html("<script>window.parent.document.body.setAttribute('data-agentk-ready', 'true');</script>", height=0)
                    # st.stop()

                ctx = self._get_user_context()
                self.logger.info(format_audit_log(
                    actor=ctx["user"],
                    action="GATEWAY_VALIDATION",
                    resource="prompt",
                    outcome=veredito,
                    source_ip=ctx["ip"],
                    context_data=f"test_mode=true, verdict={veredito}"
                ))

                mensagens_gateway = {
                    "SAFE": "✅ Veredito SAFE recebido. Requisição retida para teste e próximo prompt liberado.",
                    "SUSPECT": "⚠️ Prompt SUSPEITO detectado. Requisição retida para teste e próximo prompt liberado.",
                    "UNCERTAIN": "🔍 Veredito INCERTO. Requisição retida para teste e próximo prompt liberado.",
                    "UNSAFE": "🛑 Veredito UNSAFE detectado. Requisição retida para teste e próximo prompt liberado.",
                    "RISKY": "⚠️ Veredito RISKY recebido. Requisição retida para teste e próximo prompt liberado."
                }
                texto_alerta = mensagens_gateway.get(veredito, f"Veredito {veredito}. Requisição retida para teste e próximo prompt liberado.")

                self.logger.info(format_audit_log(
                    actor=ctx["user"],
                    action="TEST_FLOW_CONTINUE",
                    resource="prompt",
                    outcome="DROPPED_AFTER_GATEWAY",
                    source_ip=ctx["ip"],
                    context_data=f"verdict={veredito}"
                ))

                self._trigger_test_refresh()
                return self._create_mock_response(texto_alerta)

            except requests.exceptions.RequestException as e:
                st.warning(f"⚠️ Falha de comunicação com o Gateway: {e}. Prosseguindo para o próximo prompt de teste.")
                self._trigger_test_refresh()
                return self._create_mock_response("GATEWAY_REQUEST_ERROR")
            except json.JSONDecodeError:
                st.warning("❌ O Gateway não retornou JSON válido. Prosseguindo para o próximo prompt de teste.")
                self._trigger_test_refresh()
                return self._create_mock_response("GATEWAY_JSON_ERROR")

        # Fluxo Normal (OpenAI) - COMENTADO PARA TESTES
        """
        request_start = self.export_service.record_request_start()
        response = self.llm_client.complete_chat(tools)
        self.export_service.record_request_end(request_start, response)
        
        assistant_reply = response.choices[0].message.content
        ctx = self._get_user_context()
        self.logger.info(format_audit_log(
            actor=ctx["user"],
            action="LLM_RESPONSE",
            resource="assistant_message",
            outcome="SUCCESS",
            source_ip=ctx["ip"],
            context_data=f"content_snippet={assistant_reply[:50] if assistant_reply else ''}..."
        ))
        
        return response
        """

        # Chamada para a nova função que dropa a requisição
        return self.process_test_drop_request(tools)

    def process_test_drop_request(self, tools=[]):
        """
        [TEMPORÁRIO] Dropa a requisição para OpenAI e sinaliza prontidão para captura.
        """
        with st.chat_message("assistant"):
            st.info("✅ **[TEST_MODE] Veredito: SAFE. Requisição retida (Bypass OpenAI).**")
        
        self._trigger_test_refresh()
        return self._create_mock_response("SAFE_DROPPED")

    def _trigger_test_refresh(self):
        """Sinaliza para o crawler que o processamento foi concluído.

        Mecanismo: grava '_signal_ready=True' no session_state e chama st.rerun().
        No início do próximo run (contexto raso), main.py lê o flag, emite o JS
        e o limpa. Isso é mais robusto do que emitir st.components.v1.html de
        dentro de contextos aninhados (spinner → process_llm_request → aqui),
        onde o delta pode não ser flushed antes do st.stop() encerrar o run.
        """
        self.logger.info(format_audit_log(
            actor="Gateway-System",
            action="TRIGGER_REFRESH",
            resource="data-agentk-ready",
            outcome="STAGE_1_SET_SIGNAL_READY",
            source_ip="internal",
            context_data="signal_ready=True, will_rerun=True"
        ))
        st.session_state.llm_client.history = []
        st.session_state.is_processing = False
        st.session_state['_signal_ready'] = True
        self.logger.info(format_audit_log(
            actor="Gateway-System",
            action="TRIGGER_REFRESH",
            resource="data-agentk-ready",
            outcome="STAGE_2_CALLING_RERUN",
            source_ip="internal",
            context_data="signal_ready=True"
        ))
        st.rerun()

    def _create_mock_response(self, content):
        """Helper para criar a estrutura que o resolve_chat espera."""
        class MockObj:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
        
        return MockObj(choices=[
            MockObj(
                message=MockObj(content=content, role="assistant"),
                finish_reason="stop"
            )
        ])
        
    def export_conversation_history(self, include_tools: bool = True) -> tuple[str, str]:
        """
        Exporta o histórico da conversa em formato Markdown.
        
        Args:
            include_tools: Se deve incluir as chamadas de ferramentas no export
            
        Returns:
            Tuple contendo (conteúdo_markdown, nome_do_arquivo)
        """
        markdown_content = self.export_service.generate_markdown_export(
            self.llm_client.history, 
            include_tools
        )
        filename = self.export_service.get_filename()
        return markdown_content, filename