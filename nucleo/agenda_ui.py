"""Componentes Streamlit compartilhados pela Fila BDR e pelo CRM."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from banco import consultas, repositorio

from . import agenda, tempo


def _formulario(usuario: dict, *, prefixo: str, lead_id: int | None = None) -> None:
    carteira = consultas.leads()
    if usuario["papel"] == "bdr":
        carteira = carteira[carteira["responsavel_id"] == usuario["id"]]
    elif usuario["papel"] == "executivo":
        carteira = carteira[carteira["executivo_id"] == usuario["id"]]
    carteira = carteira[carteira["opt_out"] == 0]
    if lead_id is not None:
        carteira = carteira[carteira["id"] == lead_id]
    if carteira.empty:
        st.info("Nenhum lead elegível para criar compromissos na sua carteira.")
        return
    nomes = {
        int(reg.id): f"{reg.nome_fantasia or reg.razao_social} · #{reg.id}"
        for reg in carteira.itertuples()
    }
    hoje = tempo.hoje_local()
    with st.form(f"{prefixo}_novo_compromisso"):
        if lead_id is None:
            selecionado = st.selectbox("Empresa", list(nomes), format_func=nomes.get)
        else:
            selecionado = lead_id
            st.caption(f"Empresa: {nomes[selecionado]}")
        titulo = st.text_input("Próxima ação", placeholder="Ex.: Revisar perfil e preparar abordagem", max_chars=180)
        tipo = st.selectbox("Tipo de compromisso", agenda.TIPOS)
        a, b = st.columns(2)
        data = a.date_input("Data", value=hoje + timedelta(days=1), format="DD/MM/YYYY")
        hora = b.time_input("Horário", value=time(9, 0))
        observacao = st.text_area("Observações", max_chars=1000)
        responsaveis = repositorio.usuarios("bdr")
        if usuario["papel"] == "gestor" and responsaveis:
            opcoes = [usuario["id"], *[r["id"] for r in responsaveis if r["id"] != usuario["id"]]]
            rotulos = {usuario["id"]: usuario["nome"]}
            rotulos.update({r["id"]: r["nome"] for r in responsaveis})
            atual = consultas.lead(selecionado)
            padrao = atual["responsavel_id"] if atual["responsavel_id"] in opcoes else usuario["id"]
            destino = st.selectbox(
                "Responsável pela tarefa",
                opcoes,
                index=opcoes.index(padrao),
                format_func=rotulos.get,
            )
        else:
            destino = usuario["id"]
        if tipo == "Reunião confirmada":
            st.caption("Exige contato efetivo anterior e base legal de contato documentada.")
        else:
            st.caption("Agendar uma tarefa não envia mensagens nem altera o status comercial do lead.")
        enviar = st.form_submit_button("Agendar compromisso", type="primary")
    if enviar:
        try:
            quando = tempo.iso(datetime.combine(data, hora, tzinfo=tempo.FUSO))
            agenda.agendar(selecionado, usuario, tipo, titulo, quando, observacao, destino)
        except (ValueError, PermissionError) as erro:
            st.error(str(erro))
        else:
            st.session_state[f"{prefixo}_agenda_msg"] = "Compromisso incluído na agenda e no próximo retorno do lead."
            st.rerun()


def ficha(lead_id: int, usuario: dict, *, prefixo: str = "bdr") -> None:
    """Formulário para gerir uma agenda individual, sem depender do funil CRM."""
    if msg := st.session_state.pop(f"{prefixo}_agenda_msg", None):
        st.success(msg)
    with st.expander("Agendar retorno, tarefa ou reunião", expanded=False):
        _formulario(usuario, prefixo=prefixo, lead_id=lead_id)
    compromissos = [
        evento for evento in agenda.listar(usuario, limite=300)
        if evento["lead_id"] == lead_id
    ]
    if compromissos:
        st.caption("Compromissos pendentes desta empresa")
        for evento in compromissos[:5]:
            st.write(f"**{tempo.fmt(evento['inicio_em'])}** · {evento['tipo']} · {evento['titulo']}")


def painel(usuario: dict, *, prefixo: str = "crm") -> None:
    """Miniagenda na parte superior do CRM: visualizar, criar e concluir."""
    if msg := st.session_state.pop(f"{prefixo}_agenda_msg", None):
        st.success(msg)
    eventos = agenda.listar(usuario, limite=300)
    hoje = tempo.hoje_local()
    atrasados = [
        ev for ev in eventos if (tempo.local(ev["inicio_em"]) or tempo.agora()).date() < hoje
    ]
    agenda_hoje = [
        ev for ev in eventos if (tempo.local(ev["inicio_em"]) or tempo.agora()).date() == hoje
    ]
    proximos = [
        ev for ev in eventos
        if hoje <= (tempo.local(ev["inicio_em"]) or tempo.agora()).date() <= hoje + timedelta(days=7)
    ]
    with st.expander("Minha agenda comercial · tarefas e reuniões", expanded=True):
        a, b, c = st.columns(3)
        a.metric("Hoje", len(agenda_hoje))
        b.metric("Próximos 7 dias", len(proximos))
        c.metric("Atrasados", len(atrasados))
        filtro = st.segmented_control(
            "Visualização", ["Hoje", "Próximos 7 dias", "Atrasados", "Todos"],
            default="Próximos 7 dias", key=f"{prefixo}_filtro",
        )
        escolhidos = {
            "Hoje": agenda_hoje,
            "Próximos 7 dias": proximos,
            "Atrasados": atrasados,
            "Todos": eventos,
        }[filtro]
        if not escolhidos:
            st.info("Nenhum compromisso nesse período. Use 'Novo compromisso' para planejar a próxima ação.")
        else:
            quadro = pd.DataFrame(
                [
                    {
                        "id": ev["id"],
                        "quando": tempo.fmt(ev["inicio_em"]),
                        "empresa": ev["nome_fantasia"] or ev["razao_social"],
                        "tipo": ev["tipo"],
                        "ação": ev["titulo"],
                        "responsável": ev["responsavel"],
                    }
                    for ev in escolhidos[:50]
                ]
            )
            st.dataframe(
                quadro,
                hide_index=True,
                width="stretch",
                column_config={
                    "id": st.column_config.NumberColumn("#", width="small"),
                    "quando": "Data e hora",
                    "empresa": "Empresa",
                    "tipo": "Tipo",
                    "ação": "Próxima ação",
                    "responsável": "Responsável",
                },
            )
            nomes = {
                ev["id"]: f"{tempo.fmt(ev['inicio_em'])} · {ev['titulo']} · {ev['razao_social']}"
                for ev in escolhidos
            }
            selecionado = st.selectbox(
                "Gerenciar compromisso",
                list(nomes),
                format_func=nomes.get,
                key=f"{prefixo}_selecionado",
            )
            a, b, c = st.columns([1, 1, 1.5])
            if a.button("Concluir", key=f"{prefixo}_concluir"):
                try:
                    agenda.concluir(selecionado, usuario, "Concluído")
                except (ValueError, PermissionError) as erro:
                    st.error(str(erro))
                else:
                    st.session_state[f"{prefixo}_agenda_msg"] = "Compromisso concluído e histórico atualizado."
                    st.rerun()
            if b.button("Cancelar", key=f"{prefixo}_cancelar"):
                try:
                    agenda.concluir(selecionado, usuario, "Cancelado")
                except (ValueError, PermissionError) as erro:
                    st.error(str(erro))
                else:
                    st.session_state[f"{prefixo}_agenda_msg"] = "Compromisso cancelado."
                    st.rerun()
            evento_selecionado = next(e for e in escolhidos if e["id"] == selecionado)
            if c.button("Abrir empresa na Fila do BDR", key=f"{prefixo}_abrir_lead"):
                st.session_state["fila_abrir_id"] = int(evento_selecionado["lead_id"])
                st.switch_page("paginas/fila_bdr.py")
        with st.expander("Novo compromisso", expanded=False):
            _formulario(usuario, prefixo=prefixo)
