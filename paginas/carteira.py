"""Carteira: todos os leads do BDR, em qualquer etapa. O gestor vê todos e redistribui."""

from __future__ import annotations

import streamlit as st

from banco import consultas, repositorio
from banco.conexao import conectar
from nucleo import campanhas_ui, comercial, crm_operacional, estados, lgpd, tempo, triagem, ui

usuario = st.session_state["usuario"]
gestor = usuario["papel"] in ("gestor", "executivo")
pode_encaminhar = usuario["papel"] == "gestor"

ui.cabecalho(
    "Carteira",
    "Todos os leads em qualquer etapa, com a última atividade e a próxima ação."
    + (" Como gestor, você vê a carteira de todos e pode redistribuir." if gestor else ""),
    secao="Prospecção",
)
if msg := st.session_state.pop("carteira_msg", None):
    st.success(msg)

dados = consultas.carteira(None if gestor else usuario["id"], incluir_sem_responsavel=gestor)
if dados.empty:
    st.info("Nenhum lead disponível nesta carteira.")
    st.stop()

dados = campanhas_ui.aplicar(dados, "id", "carteira_campanha")
if dados.empty:
    st.info("A campanha selecionada ainda não tem leads nesta carteira.")
    st.stop()

hoje = tempo.hoje_local().isoformat()
dados["empresa"] = dados["nome_fantasia"].fillna(dados["razao_social"])
dados["solucao"] = dados["solucao_principal"].map(crm_operacional.nome_solucao)
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
dados["situacao"] = [triagem.situacao_operacional(r.etapa, r.responsavel) for r in dados.itertuples()]

a, b, c = st.columns([1.6, 1.4, 1])
busca = a.text_input("Buscar empresa", placeholder="Nome, razão social ou CNPJ", max_chars=80)
etapas = b.multiselect("Etapa", [e for e in estados.ESTADOS if e in set(dados["etapa"])], placeholder="Todas")
prazo = c.selectbox("Prazo de retorno", ["Todos", "Atrasado", "Hoje", "Próximos", "Sem data"])
a, b, c = st.columns([1.6, 1.4, 1])
solucao = a.selectbox("Solução", ["Todas", *crm_operacional.opcoes_solucoes(dados["solucao"])])
responsaveis = (
    b.multiselect("Responsável", sorted(dados["responsavel"].dropna().unique()), placeholder="Todas") if gestor else []
)
ufs = c.multiselect("UF (filtro)", sorted(dados["uf"].dropna().unique()), placeholder="Todas")

vis = dados
if busca:
    termo = busca.casefold()
    vis = vis[vis["empresa"].fillna("").str.casefold().str.contains(termo, regex=False)
              | vis["razao_social"].fillna("").str.casefold().str.contains(termo, regex=False)
              | vis["cnpj"].fillna("").str.contains(busca, regex=False)]  # fmt: skip
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

if vis.empty:
    st.info("Nenhum lead atende aos filtros. Limpe os filtros para visualizar toda a carteira.")
    st.stop()

colunas = [
    "id",
    "empresa",
    "cnpj",
    "tags",
    "etapa",
    "situacao",
    "classificacao",
    "nota_final",
    "solucao",
    "responsavel",
    "proxima_acao",
    "prazo",
]
ui.rotulo("Leads da carteira · clique numa linha para trabalhar")
selecao = st.dataframe(
    vis[colunas].reset_index(drop=True),
    hide_index=True,
    width="stretch",
    on_select="rerun",
    selection_mode="single-row",
    key="carteira_selecao",
    column_config={
        "id": st.column_config.NumberColumn("#", width="small"),
        "empresa": "Empresa",
        "cnpj": "CNPJ",
        "tags": "Campanhas",
        "etapa": "Etapa",
        "situacao": "Por que está aqui",
        "classificacao": "Classe IA",
        "nota_final": st.column_config.ProgressColumn("Nota", min_value=0, max_value=100, format="%.0f"),
        "solucao": "Solução",
        "responsavel": "BDR",
        "proxima_acao": "Próxima ação",
        "prazo": "Retorno",
    },
)
linhas = selecao.selection.rows if selecao and selecao.selection else []
selecionado_id = int(vis.iloc[linhas[0] if linhas else 0]["id"])
lead = consultas.lead(selecionado_id)
trat = consultas.ultimo_tratamento(selecionado_id)
situacao = triagem.situacao_operacional(lead["etapa"], lead.get("responsavel"))
st.divider()
ui.rotulo("Ficha do lead selecionado")
st.markdown(f"### {lead['nome_fantasia'] or lead['razao_social']}")
a, b, c, d = st.columns(4)
a.caption(f"**CNPJ:** {lead.get('cnpj') or 'Não informado'}")
b.caption(f"**Etapa:** {lead['etapa']}")
c.caption(f"**BDR:** {lead.get('responsavel') or 'Não atribuído'}")
d.caption(f"**Contato:** {lgpd.status_contato(selecionado_id)}")
st.info(situacao)
if trat:
    explicacao = (trat.get("decomposicao") or {}).get("explicacao_destino")
    st.write(f"**Decisão do supervisor IA:** {explicacao or trat.get('destino') or 'Sem justificativa registrada'}")
    st.write(f"**Produto sugerido:** {crm_operacional.nome_solucao(lead['solucao_principal']) or 'Pendente'}")
else:
    st.warning("Ainda não há tratamento IA concluído para este CNPJ.")
    if st.button("Abrir Tratamento IA", key="carteira_ir_tratamento"):
        st.switch_page("paginas/tratamento.py")

if pode_encaminhar:
    bdrs_triagem = repositorio.usuarios("bdr")
    elegivel = lead["etapa"] in triagem.ENCAMINHAVEIS and not lead["opt_out"] and bool(trat)
    st.markdown("**Encaminhamento manual para a fila do BDR**")
    if not elegivel:
        st.caption("Esta etapa não permite envio direto. Finalize a IA ou a revisão aplicável.")
    elif not bdrs_triagem:
        st.warning("Cadastre ao menos um BDR ativo antes de encaminhar.")
    else:
        with st.form(f"carteira_encaminhar_{selecionado_id}"):
            nomes_bdr = {x["id"]: x["nome"] for x in bdrs_triagem}
            destino_fila = st.selectbox(
                "BDR responsável",
                list(nomes_bdr),
                format_func=nomes_bdr.get,
            )
            justificativa = st.text_area(
                "Justificativa da decisão comercial",
                placeholder="Ex.: há aderência comercial apesar da baixa confiança da IA.",
                max_chars=500,
            )
            enviar_fila = st.form_submit_button("Enviar este lead para a fila", type="primary")
        if enviar_fila:
            try:
                total = triagem.encaminhar(
                    [selecionado_id],
                    usuario,
                    destino_fila,
                    justificativa,
                )
            except (ValueError, PermissionError, estados.TransicaoInvalida) as erro:
                st.error(str(erro))
            else:
                st.session_state["carteira_msg"] = f"{total} lead enviado à fila do BDR, com decisão auditada."
                st.rerun()

with st.expander("Registrar nota de acompanhamento", expanded=False):
    if lead["opt_out"]:
        st.warning("Opt-out registrado. Novas atividades estão bloqueadas.")
    else:
        with st.form(f"carteira_nota_{selecionado_id}"):
            anotacao = st.text_area("Nota interna", max_chars=1000)
            proxima = st.text_input("Próxima ação interna", max_chars=180)
            salvar_nota = st.form_submit_button("Registrar nota")
        if salvar_nota:
            try:
                comercial.registrar_atividade(
                    selecionado_id,
                    usuario,
                    "Nota",
                    "",
                    anotacao,
                    proxima,
                )
            except ValueError as erro:
                st.error(str(erro))
            else:
                st.session_state["carteira_msg"] = "Nota salva no histórico deste lead."
                st.rerun()


if gestor:
    st.divider()
    ui.rotulo("Redistribuir leads")
    bdrs = repositorio.usuarios("bdr")
    ativos = vis[vis["etapa"].isin([*comercial.ETAPAS_ATIVAS_BDR, estados.REUNIAO, estados.PROPOSTA, estados.NUTRICAO])]
    if not bdrs:
        st.info("Nenhum BDR ativo cadastrado para redistribuição.")
        st.stop()
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
