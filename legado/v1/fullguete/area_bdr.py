"""Interface da carteira e do pipeline de pré-vendas."""

from __future__ import annotations

import html
import sqlite3
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from . import carteira

FUSO = ZoneInfo("America/Sao_Paulo")
LIMIAR_PRIORITARIO = 80


def enviar_ranking(ranking: pd.DataFrame, responsavel: str, analise_id: int, origem: str, metodo: str, chave: str) -> None:
    with st.container(border=True):
        st.markdown("#### Enviar leads para minha carteira BDR")
        posicoes = {int(lead.posicao): lead for lead in ranking.itertuples(index=False)}
        with st.form(f"carteira_envio_{chave}"):
            selecionadas = st.multiselect(
                "Empresas para trabalhar",
                options=list(posicoes),
                format_func=lambda pos: f"{pos}. {posicoes[pos].empresa} · {posicoes[pos].score}/100",
                placeholder="Selecione empresas do ranking",
            )
            enviar = st.form_submit_button("Adicionar à carteira", type="primary")
        if enviar and not selecionadas:
            st.warning("Selecione pelo menos uma empresa.")
        elif enviar:
            try:
                novos, atualizados = carteira.adicionar(
                    responsavel, ranking[ranking["posicao"].isin(selecionadas)], analise_id, origem, metodo,
                )
            except sqlite3.Error:
                st.error("Não foi possível salvar esses leads na carteira. Tente novamente.")
            else:
                existentes = len(selecionadas) - novos - atualizados
                st.success(f"{novos} adicionados · {atualizados} atualizados · {existentes} já estavam na carteira.")


def _pipeline(leads: list[dict], hoje: str) -> None:
    for coluna, etapa in zip(st.columns(len(carteira.ETAPAS)), carteira.ETAPAS, strict=True):
        grupo = [lead for lead in leads if lead["etapa"] == etapa]
        with coluna, st.container(border=True):
            st.markdown(f"**{etapa}** · {len(grupo)}")
            if not grupo:
                st.caption("Sem leads")
            for lead in grupo[:6]:
                acao = html.escape(lead["proxima_acao"] or "")
                nome = html.escape(lead["empresa"])
                prazo = ""
                if lead["retorno_em"]:
                    retorno = date.fromisoformat(lead["retorno_em"]).strftime("%d/%m")
                    cor = "#FFC29B" if lead["retorno_em"] < hoje and etapa != "Encerrado" else "#B8C1E0"
                    prazo = f'<br><small style="color:{cor}">Retorno em {retorno}</small>'
                st.html(
                    f'<div class="fg-card"><b>{nome}</b><br><span class="fg-badge">Fit {lead["score"]}</span>'
                    f'<br><small>{acao}</small>{prazo}</div>'
                )
            if len(grupo) > 6:
                st.caption(f"Mais {len(grupo) - 6} na fila.")


def _fila(leads: list[dict], hoje: str) -> None:
    tabela = pd.DataFrame([{
        "empresa": lead["empresa"],
        "score": lead["score"],
        "etapa": lead["etapa"],
        "proxima_acao": lead["proxima_acao"],
        "retorno_em": date.fromisoformat(lead["retorno_em"]) if lead["retorno_em"] else None,
        "pendencia": "Atrasado" if lead["retorno_em"] and lead["retorno_em"] < hoje and lead["etapa"] != "Encerrado" else "",
    } for lead in leads])
    st.dataframe(tabela, hide_index=True, width="stretch", column_config={
        "empresa": st.column_config.TextColumn("Empresa", width="medium"),
        "score": st.column_config.ProgressColumn("Fit", min_value=0, max_value=100, format="%d"),
        "etapa": "Etapa", "proxima_acao": "Próxima ação",
        "retorno_em": st.column_config.DateColumn("Retorno", format="DD/MM/YYYY"), "pendencia": "Prazo",
    })


def _ficha(lead: dict, responsavel: str) -> None:
    codigo = lead["id"]
    st.subheader("Ficha do lead")
    contato, formulario = st.columns([1, 1.5], gap="large")
    with contato, st.container(border=True):
        st.text(lead["empresa"])
        st.caption(f'Fit {lead["score"]}/100 · {lead["metodo"]} · Ranking #{lead["analise_id"]}')
        if lead["justificativa"]:
            st.text(lead["justificativa"])
        st.caption("Contato e origem")
        for campo, rotulo in (
            ("cnpj", "CNPJ"), ("setor", "Setor"), ("cidade", "Cidade"), ("uf", "UF"),
            ("telefone", "Telefone"), ("email", "E-mail"), ("site", "Site"), ("origem", "Fonte"),
        ):
            if lead[campo]:
                st.text(f'{rotulo}  {lead[campo]}')
        if lead["descricao"]:
            with st.expander("Descrição do cadastro"):
                st.text(lead["descricao"])

    with formulario, st.container(border=True):
        versao = st.session_state.get("bdr_ficha_versao")
        if not versao or versao[0] != codigo:
            versao = (codigo, lead["versao"])
            st.session_state["bdr_ficha_versao"] = versao
        if versao[1] != lead["versao"]:
            st.warning("Esta ficha foi atualizada em outra sessão.")
            if st.button("Recarregar ficha"):
                st.session_state.pop("bdr_ficha_versao", None)
                st.rerun()
        else:
            _editar_ficha(lead, responsavel, versao[1])

    st.markdown("#### Histórico de atividades")
    for evento in carteira.atividades(responsavel, codigo):
        horario = datetime.fromisoformat(evento["registrada_em"]).astimezone(FUSO)
        st.caption(f'{horario:%d/%m/%Y às %H:%M} · {evento["tipo"]}')
        st.text(evento["descricao"])


def _editar_ficha(lead: dict, responsavel: str, versao: int) -> None:
    codigo = lead["id"]
    with st.form(f"bdr_editar_{codigo}_{versao}", border=False):
        c1, c2 = st.columns(2)
        etapa = c1.selectbox("Etapa", carteira.ETAPAS, index=carteira.ETAPAS.index(lead["etapa"]))
        retorno = c2.date_input(
            "Data de retorno", date.fromisoformat(lead["retorno_em"]) if lead["retorno_em"] else None,
            format="DD/MM/YYYY",
        )
        proxima = st.text_input("Próxima ação", value=lead["proxima_acao"], max_chars=180)
        tipo = st.selectbox("Tipo de atividade", carteira.TIPOS_ATIVIDADE)
        nota = st.text_area("Nota da atividade", max_chars=2000, placeholder="Registre a conversa ou o resultado do contato.")
        salvar = st.form_submit_button("Salvar acompanhamento", type="primary")
    if salvar:
        try:
            carteira.registrar(
                responsavel, codigo, versao=versao, etapa=etapa, proxima_acao=proxima,
                retorno=retorno, tipo=tipo, nota=nota,
            )
        except (ValueError, carteira.ConflitoCarteira) as erro:
            st.warning(str(erro))
        except sqlite3.Error:
            st.error("Não foi possível salvar o acompanhamento.")
        else:
            st.session_state.pop("bdr_ficha_versao", None)
            st.session_state["bdr_salvo"] = True
            st.rerun()


def exibir(responsavel: str) -> None:
    st.markdown("### Minha carteira")
    if st.session_state.pop("bdr_salvo", False):
        st.success("Acompanhamento salvo.")
    try:
        leads = carteira.listar(responsavel)
    except sqlite3.Error:
        st.error("Não foi possível carregar sua carteira.")
        return
    if not leads:
        st.info("Gere um ranking em **Nova análise** e use **Enviar leads para minha carteira BDR**.")
        return

    hoje = datetime.now(FUSO).date().isoformat()
    pendentes = [l for l in leads if l["etapa"] != "Encerrado"]
    retornos = [l for l in pendentes if l["retorno_em"] and l["retorno_em"] <= hoje]
    a, b, c, d = st.columns(4)
    a.metric("Na carteira", len(leads))
    b.metric("Prioritários", sum(l["score"] >= LIMIAR_PRIORITARIO for l in pendentes))
    c.metric("Retornos até hoje", len(retornos))
    d.metric("Reuniões marcadas", sum(l["etapa"] == "Reunião marcada" for l in pendentes))

    e, f, g = st.columns([1.25, 1, 1])
    busca = e.text_input("Buscar na carteira", placeholder="Empresa, CNPJ ou setor", max_chars=100)
    etapa = f.selectbox("Filtrar etapa", ["Todas", *carteira.ETAPAS])
    prazo = g.selectbox("Filtrar retorno", ["Todos", "Até hoje", "Futuros", "Sem data"])
    if busca:
        termo = busca.strip().casefold()
        leads = [l for l in leads if termo in f'{l["empresa"]} {l["cnpj"]} {l["setor"]}'.casefold()]
    if etapa != "Todas":
        leads = [l for l in leads if l["etapa"] == etapa]
    if prazo == "Até hoje":
        leads = [l for l in leads if l["retorno_em"] and l["retorno_em"] <= hoje and l["etapa"] != "Encerrado"]
    elif prazo == "Futuros":
        leads = [l for l in leads if l["retorno_em"] and l["retorno_em"] > hoje and l["etapa"] != "Encerrado"]
    elif prazo == "Sem data":
        leads = [l for l in leads if not l["retorno_em"]]
    if not leads:
        st.info("Nenhum lead corresponde aos filtros.")
        return

    leads.sort(key=lambda l: (
        l["etapa"] == "Encerrado", not (l["retorno_em"] and l["retorno_em"] <= hoje), -l["score"],
    ))
    visao = st.segmented_control("Exibição da carteira", ["Fila de trabalho", "Pipeline"], default="Fila de trabalho")
    if visao == "Pipeline":
        _pipeline(leads, hoje)
    else:
        _fila(leads, hoje)
    por_id = {lead["id"]: lead for lead in leads}
    selecionado = st.selectbox(
        "Empresa para trabalhar", list(por_id),
        format_func=lambda id_: f'{por_id[id_]["empresa"]} · {por_id[id_]["score"]}/100',
    )
    try:
        _ficha(por_id[selecionado], responsavel)
    except sqlite3.Error:
        st.error("Não foi possível carregar o histórico de atividades.")
