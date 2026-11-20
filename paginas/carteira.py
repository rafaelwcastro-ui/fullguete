"""Carteira: todos os leads do BDR, em qualquer etapa. O gestor vê todos e redistribui."""

from __future__ import annotations

import streamlit as st

import catalogo
from banco import consultas, repositorio
from banco.conexao import conectar
from nucleo import comercial, estados, tempo, ui

usuario = st.session_state["usuario"]
gestor = usuario["papel"] in ("gestor", "executivo")

ui.cabecalho(
    "Carteira",
    "Todos os leads em qualquer etapa, com a última atividade e a próxima ação."
    + (" Como gestor, você vê a carteira de todos e pode redistribuir." if gestor else ""),
    secao="Prospecção",
)
if msg := st.session_state.pop("carteira_msg", None):
    st.success(msg)

dados = consultas.carteira(None if gestor else usuario["id"])
if dados.empty:
    st.info("Nenhum lead atribuído ainda.")
    st.stop()

hoje = tempo.hoje_local().isoformat()
dados["empresa"] = dados["nome_fantasia"].fillna(dados["razao_social"])
dados["solucao"] = dados["solucao_principal"].map(lambda s: catalogo.nome(s) if s else "")
dados["ultima_atividade"] = [
    f"{tempo.fmt(q, com_hora=False)} · {t} · {r or ''}" if isinstance(q, str) else ""
    for q, t, r in zip(dados["ultima_atividade_em"], dados["ultima_atividade_tipo"], dados["ultima_atividade_resultado"],
                       strict=True)
]  # fmt: skip
dados["retorno"] = dados["retorno_em"].map(lambda v: tempo.fmt(v, com_hora=False) if isinstance(v, str) else "")


def _prazo(v) -> str:
    if not isinstance(v, str):
        return "Sem data"
    d = v[:10]
    return "Atrasado" if d < hoje else "Hoje" if d == hoje else "Próximos"


dados["prazo"] = dados["retorno_em"].map(_prazo)

a, b, c = st.columns([1.6, 1.4, 1])
busca = a.text_input("Buscar empresa", placeholder="Nome ou razão social", max_chars=80)
etapas = b.multiselect("Etapa", [e for e in estados.ESTADOS if e in set(dados["etapa"])], placeholder="Todas")
prazo = c.selectbox("Prazo de retorno", ["Todos", "Atrasado", "Hoje", "Próximos", "Sem data"])
a, b, c = st.columns([1.6, 1.4, 1])
solucao = a.selectbox("Solução", ["Todas", *sorted(s for s in dados["solucao"].unique() if s)])
responsaveis = (
    b.multiselect("Responsável", sorted(dados["responsavel"].dropna().unique()), placeholder="Todas") if gestor else []
)
ufs = c.multiselect("UF (filtro)", sorted(dados["uf"].dropna().unique()), placeholder="Todas")

vis = dados
if busca:
    termo = busca.casefold()
    vis = vis[vis["empresa"].str.casefold().str.contains(termo, regex=False)
              | vis["razao_social"].str.casefold().str.contains(termo, regex=False)]  # fmt: skip
if etapas:
    vis = vis[vis["etapa"].isin(etapas)]
if prazo != "Todos":
    vis = vis[vis["prazo"] == prazo]
if solucao != "Todas":
    vis = vis[vis["solucao"] == solucao]
if responsaveis:
    vis = vis[vis["responsavel"].isin(responsaveis)]
if ufs:
    vis = vis[vis["uf"].isin(ufs)]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Leads", len(vis))
m2.metric(
    "Em andamento", int(vis["etapa"].isin([*comercial.ETAPAS_ATIVAS_BDR, estados.REUNIAO, estados.PROPOSTA]).sum())
)
m3.metric("Retornos atrasados", int((vis["prazo"] == "Atrasado").sum()))
m4.metric("Ganhos", int((vis["etapa"] == estados.GANHO).sum()))

colunas = ["id", "empresa", "etapa", "classificacao", "nota_final", "solucao", "ultima_atividade", "proxima_acao",
           "retorno", "prazo"] + (["responsavel"] if gestor else [])  # fmt: skip
st.dataframe(vis[colunas], hide_index=True, width="stretch", column_config={
    "id": st.column_config.NumberColumn("#", width="small"), "empresa": "Empresa", "etapa": "Etapa",
    "classificacao": "Classe", "nota_final": st.column_config.ProgressColumn("Nota", min_value=0, max_value=100, format="%.0f"),
    "solucao": "Solução", "ultima_atividade": "Última atividade", "proxima_acao": "Próxima ação", "retorno": "Retorno",
    "prazo": "Prazo", "responsavel": "Responsável",
})  # fmt: skip

if gestor:
    st.divider()
    ui.rotulo("Redistribuir leads")
    bdrs = repositorio.usuarios("bdr")
    ativos = vis[vis["etapa"].isin([*comercial.ETAPAS_ATIVAS_BDR, estados.REUNIAO, estados.PROPOSTA, estados.NUTRICAO])]
    with st.form("redistribuir"):
        opcoes = {int(r.id): f"#{r.id} {r.empresa} · {r.responsavel}" for r in ativos.itertuples()}
        escolhidos = st.multiselect("Leads", list(opcoes), format_func=opcoes.get, placeholder="Selecione")
        a, b = st.columns(2)
        destino = a.selectbox(
            "Novo responsável", [x["id"] for x in bdrs], format_func={x["id"]: x["nome"] for x in bdrs}.get
        )
        motivo = b.text_input("Motivo (obrigatório)", max_chars=200)
        enviar = st.form_submit_button("Redistribuir", type="primary")
    if enviar:
        if not escolhidos or not motivo.strip():
            st.error("Escolha os leads e escreva o motivo.")
        else:
            with conectar() as con:
                for lead_id in escolhidos:
                    comercial.atribuir(con, lead_id, destino, usuario["login"], motivo.strip())
            st.session_state["carteira_msg"] = f"{len(escolhidos)} lead(s) redistribuídos."
            st.rerun()
