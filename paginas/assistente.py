"""Assistente IA: chat com o catálogo (RAG) e o lead selecionado como contexto. Não executa ações."""

from __future__ import annotations

import streamlit as st

from banco import consultas
from ia import assistente, provedor
from nucleo import estados, ui

usuario = st.session_state["usuario"]

ui.cabecalho(
    "Assistente IA",
    "Pergunte sobre o catálogo ou peça ajuda com um lead. O assistente responde, mas não executa nenhuma ação.",
    secao="Inteligência",
)
if not provedor.disponivel():
    st.info("Sem chave de IA: as respostas usam modelos de texto locais e a busca no catálogo.")

ativos = consultas.leads([estados.FILA_BDR, estados.EM_CONTATO, estados.QUALIFICADO, estados.REUNIAO, estados.PROPOSTA])
if usuario["papel"] == "bdr":
    ativos = ativos[ativos["responsavel_id"] == usuario["id"]]
opcoes = {0: "Nenhum lead"} | {int(r.id): f"#{r.id} {r.nome_fantasia or r.razao_social} · {r.etapa}"
                               for r in ativos.itertuples()}  # fmt: skip
lead_id = st.selectbox("Lead em contexto", list(opcoes), format_func=opcoes.get)
empresa = opcoes[lead_id].split(" · ")[0].split(" ", 1)[1] if lead_id else "[empresa]"

# O histórico do lead não pode aparecer nem ser reutilizado no chat de outro lead/usuário.
chave_historico = assistente.chave_conversa(usuario["id"], lead_id)
historico = st.session_state.setdefault(chave_historico, [])

ui.rotulo("Exemplos")
cols = st.columns(len(assistente.EXEMPLOS))
pergunta_pronta = None
for col, exemplo in zip(cols, assistente.EXEMPLOS, strict=True):
    texto = exemplo.format(empresa=empresa)
    if col.button(texto, width="stretch"):
        pergunta_pronta = texto

for msg in historico:
    with st.chat_message("user" if msg["papel"] == "usuario" else "assistant"):
        st.markdown(msg["texto"])
        if msg.get("rodape"):
            st.caption(msg["rodape"])

pergunta = st.chat_input("Escreva sua pergunta") or pergunta_pronta
if pergunta:
    historico.append({"papel": "usuario", "texto": pergunta})
    with st.chat_message("user"):
        st.markdown(pergunta)
    with st.chat_message("assistant"), st.spinner("Pensando..."):
        r = assistente.responder(pergunta, lead_id or None, historico[:-1], usuario=usuario)
        if r.get("aviso"):
            st.caption(r["aviso"])
        st.markdown(r["texto"])
        rodape = f"Motor: {r['motor']}. Fontes do catálogo: {', '.join(r['fontes']) or 'nenhuma'}."
        st.caption(rodape)
    historico.append({"papel": "assistente", "texto": r["texto"], "rodape": rodape})

if historico and st.button("Limpar conversa"):
    st.session_state[chave_historico] = []
    st.rerun()
