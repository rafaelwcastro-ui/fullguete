"""Fullguete v2: da captura do lead ao fechamento, com IA explicável e o BDR no controle.

Este arquivo cuida só do que é comum a todas as páginas: tema, carga inicial, login e menu.
Cada item do menu vive em paginas/.
"""

from __future__ import annotations

import json

import streamlit as st

from banco import repositorio, semente
from nucleo import auth, config, ui

st.set_page_config(
    page_title="Fullguete",
    page_icon=str(config.RAIZ / "assets" / "icone.png"),
    layout="wide",
)
ui.aplicar_css()


@st.cache_resource(show_spinner="Preparando a base de demonstração...")
def _preparar_base(modo: str, logins_demo: bool, assinatura_usuarios: str) -> dict:
    # assinatura_usuarios entra só na chave do cache: se os Secrets mudarem, os usuários são sincronizados de novo.
    resumo = semente.garantir_base(modo == "simulado", config.usuarios_secrets(), config.logins_demo())
    if modo == "simulado" and config.cenario_demo_automatico() and repositorio.contar("leads") == 0:
        from dados import cenario_demo

        resumo["cenario"] = cenario_demo.montar()
    return resumo


_preparar_base(config.modo(), config.logins_demo(), json.dumps(config.usuarios_secrets(), sort_keys=True, default=str))

usuario = auth.exigir_login(
    repositorio.usuarios_para_login(),
    semente.usuarios_demonstracao() if config.logins_demo() else [],
    logo=str(config.RAIZ / "assets" / "logo.png"),
)

P = "paginas"
paginas = {
    "VISÃO GERAL": [
        st.Page(f"{P}/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
    ],
    "PROSPECÇÃO": [
        st.Page(f"{P}/captura.py", title="Captura de leads", icon=":material/input:"),
        st.Page(f"{P}/tratamento.py", title="Tratamento IA", icon=":material/psychology:"),
        st.Page(f"{P}/fila_bdr.py", title="Fila do BDR", icon=":material/format_list_numbered:"),
        st.Page(f"{P}/carteira.py", title="Carteira", icon=":material/work:"),
    ],
    "RELACIONAMENTO": [
        st.Page(f"{P}/crm_funil.py", title="CRM & funil", icon=":material/filter_alt:"),
    ],
    "INTELIGÊNCIA": [
        st.Page(f"{P}/assistente.py", title="Assistente IA", icon=":material/smart_toy:"),
        st.Page(f"{P}/catalogo.py", title="Catálogo de ofertas", icon=":material/inventory_2:"),
        st.Page(f"{P}/indicadores.py", title="Indicadores", icon=":material/monitoring:"),
    ],
    "CONTROLES": [
        st.Page(f"{P}/governanca.py", title="Governança & LGPD", icon=":material/verified_user:"),
    ],
}
navegacao = st.navigation(paginas)

with st.sidebar:
    st.image(str(config.RAIZ / "assets" / "logo.png"), width="stretch")
    ui.rotulo("Sessão")
    st.markdown(f"**{usuario['nome']}**  \n{auth.PAPEIS[usuario['papel']]}")
    motor = "Gemini" if config.chave_gemini() else "Análise local"
    st.html(ui.selo_simulado("Modo simulado") if config.simulado() else ui.selo_html("Modo real", "info"))
    st.caption(f"Motor de IA: {motor}")
    if st.button("Sair", icon=":material/logout:", width="stretch"):
        auth.sair()
        st.rerun()

navegacao.run()
ui.rodape()
