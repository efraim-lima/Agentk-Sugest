import os
import sys
import streamlit as st

# Forçar UTF-8 para entrada/saída
sys.stdout.reconfigure(encoding='utf-8')
sys.stdin.reconfigure(encoding='utf-8')

# Adiciona o diretório do cliente ao PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.initialization import initialize_services
from app.config import settings
from app.services.chat_service import ChatService
from app.ui.components.sidebar import Sidebar
from app.core.async_utils import run_task

# Inicializa os serviços necessários
initialize_services()

# Configura serviço de chat
chat_service = ChatService(st.session_state.llm_client)

# Carrega e aplica os estilos CSS
st.markdown(settings.load_css("main.css"), unsafe_allow_html=True)

# Botão de Logout Flutuante
# Fluxo: OAuth2 Proxy Sign-out -> Keycloak Logout -> App Home
logout_url = (
    "/oauth2/sign_out?rd=https://agentk.local/keycloak/realms/agentk/protocol/openid-connect/logout"
    "?post_logout_redirect_uri=https://agentk.local/"
)

st.markdown(
    f'<a href="{logout_url}" class="logout-button" target="_self">'
    '   <span style="margin-right:8px;">🚪</span> Sair'
    '</a>',
    unsafe_allow_html=True
)

# Renderiza sidebar
sidebar = Sidebar("Agent K", settings.LOGO_PATH)
sidebar.render()

# Container principal para o chat
st.markdown('<div class="main-content">', unsafe_allow_html=True)

# Inicializa o estado de processamento se não existir
if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False

# Renderiza histórico do chat
chat_service.render_chat_history()

# Input do usuário (desabilitado durante o processamento)
prompt = chat_service.chat_interface.get_user_input(disabled=st.session_state.is_processing)

resume_risky = st.session_state.get("risky_authorized_pending_llm", False)

if prompt or resume_risky:
    if prompt:
        st.session_state.is_processing = True
        st.session_state.llm_client.add_user_message(prompt)
        
        # Incrementa contador de mensagens do usuário
        if 'message_count' not in st.session_state:
            st.session_state.message_count = 0
        st.session_state.message_count += 1
        
        # Registra timestamp da mensagem do usuário
        chat_service.export_service.record_message_timestamp(st.session_state.message_count)
        
        chat_service.chat_interface.render_message("user", prompt, avatar=":material/person:")

    if resume_risky:
        st.session_state.is_processing = True

    with st.container():
        with st.spinner("Processando sua pergunta..."):
            # Usa o novo método que rastreia tempo e tokens
            response = chat_service.process_llm_request(st.session_state.tools)
            if response is not None:
                chat_service.resolve_chat(response)
    st.session_state.is_processing = False

# Fecha o container principal
st.markdown('</div>', unsafe_allow_html=True)

# Disclaimer fixo na parte inferior
st.markdown(
    '''
    <div class="disclaimer-footer">
        O AgentK pode cometer erros. Sempre revise antes de qualquer implementação
    </div>
    ''', 
    unsafe_allow_html=True
)