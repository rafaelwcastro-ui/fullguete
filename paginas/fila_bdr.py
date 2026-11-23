"""Fila do BDR: o painel de trabalho. Quem abordar agora, por quê, com qual oferta e como."""

from __future__ import annotations

import html
from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

import catalogo
from banco import consultas, repositorio
from ia import nota
from nucleo import auth, campanhas_ui, comercial, componentes, estados, lgpd, tempo, ui

usuario = st.session_state["usuario"]

ui.cabecalho(
    "Fila do BDR",
    "A fila já vem priorizada pela nota e pelo SLA. A IA sugere a oferta e o roteiro; o BDR decide e registra.",
    secao="Prospecção",
)

if msg := st.session_state.pop("fila_msg", None):
    st.success(msg)

bdrs = repositorio.usuarios("bdr")
if usuario["papel"] == "bdr":
    dono = usuario
else:
    if not bdrs:
        st.info("Nenhum BDR cadastrado.")
        st.stop()
    por_id = {b["id"]: b for b in bdrs}
    escolhido = st.selectbox("Ver a fila de", list(por_id), format_func=lambda i: por_id[i]["nome"])
    dono = por_id[escolhido]
    st.caption(
        f"Você está vendo a fila como {auth.PAPEIS[usuario['papel']].lower()}. As ações ficam registradas no seu nome."
    )

# ---------- metas do dia ----------
hoje = tempo.hoje_local()
inicio_dia = tempo.iso(datetime.combine(hoje, time.min, tzinfo=tempo.FUSO))
inicio_semana = tempo.iso(datetime.combine(hoje - timedelta(days=hoje.weekday()), time.min, tzinfo=tempo.FUSO))
metas = consultas.metas_do_dia(dono["id"], inicio_dia, inicio_semana, tempo.iso(), hoje.isoformat())
a, b, c, d = st.columns(4)
a.metric("Contatos hoje", f"{metas['contatos']} / {metas['meta']}")
b.metric("Retornos de hoje", metas["retornos"])
c.metric("Atrasados", metas["atrasados"])
d.metric("Reuniões na semana", metas["reunioes_semana"])

# ---------- fila priorizada ----------
carteira = consultas.carteira(dono["id"])
fila = carteira[carteira["etapa"].isin(comercial.ETAPAS_ATIVAS_BDR) & (carteira["opt_out"] == 0)].copy()
if fila.empty:
    st.info(
        "Fila vazia. Os leads importados podem estar em Capturado, Retido LGPD, "
        "Revisão ou Nutrição. Confira a aba Todos os leads no Tratamento IA."
    )
    st.stop()

fila = campanhas_ui.aplicar(fila, "id", "bdr_campanha")
if fila.empty:
    st.info("Esta campanha não possui leads liberados para este BDR.")
    st.stop()

agora = tempo.iso()
hoje_txt = hoje.isoformat()
fila["sla_vencido"] = (
    (fila["etapa"] == estados.FILA_BDR)
    & fila["primeiro_contato_em"].isna()
    & (fila["sla_limite"].fillna("9999") < agora)
)
fila["retorno_vencido"] = fila["retorno_em"].fillna("9999").str[:10] < hoje_txt
fila["atrasado"] = fila["sla_vencido"] | fila["retorno_vencido"]
fila["retorno_hoje"] = fila["retorno_em"].fillna("").str[:10] == hoje_txt
fila["urgencia"] = fila["atrasado"].astype(int) * 2 + fila["retorno_hoje"].astype(int)
fila = fila.sort_values(["urgencia", "nota_final"], ascending=[False, False])
fila["empresa"] = fila["nome_fantasia"].fillna(fila["razao_social"])
fila["solucao"] = fila["solucao_principal"].map(catalogo.nome)


def _sla(r) -> str:
    if r.sla_vencido:
        return "SLA vencido"
    if r.retorno_vencido:
        return "Retorno atrasado"
    if r.retorno_hoje:
        return "Retorno hoje"
    if r.etapa == estados.FILA_BDR and isinstance(r.sla_limite, str):
        horas = tempo.horas_entre(agora, r.sla_limite) or 0
        return f"SLA em {horas:.0f} h"
    return ""


fila["prazo"] = [_sla(r) for r in fila.itertuples()]

f1, f2, f3 = st.columns([2, 1.3, 1])
filtro = f1.segmented_control("Filtro", ["Todos", "Quentes", "Retorno hoje", "Atrasados"], default="Todos")
solucao = f2.selectbox("Solução", ["Todas", *sorted(fila["solucao"].dropna().unique())])
ufs = f3.multiselect("UF (filtro)", sorted(fila["uf"].dropna().unique()), placeholder="Todas")
vis = fila
if filtro == "Quentes":
    vis = vis[vis["classificacao"] == "Quente"]
elif filtro == "Retorno hoje":
    vis = vis[vis["retorno_hoje"]]
elif filtro == "Atrasados":
    vis = vis[vis["atrasado"]]
if solucao != "Todas":
    vis = vis[vis["solucao"] == solucao]
if ufs:
    vis = vis[vis["uf"].isin(ufs)]

lista, ficha = st.columns([1, 1.6], gap="large")
with lista:
    ui.rotulo(f"Fila priorizada · {len(vis)} lead(s)")
    if vis.empty:
        st.caption("Nenhum lead com esse filtro.")
        st.stop()
    tabela = vis[["empresa", "tags", "nota_final", "classificacao", "etapa", "prazo"]].reset_index(drop=True)
    evento = st.dataframe(
        tabela, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="fila_tabela",
        column_config={
            "empresa": st.column_config.TextColumn("Empresa", width="medium"),
            "tags": st.column_config.TextColumn("Campanhas", width="medium"),
            "nota_final": st.column_config.ProgressColumn("Nota", min_value=0, max_value=100, format="%.0f"),
            "classificacao": "Classe", "etapa": "Etapa", "prazo": "Prazo",
        },
    )  # fmt: skip
    linhas = evento.selection.rows if evento and evento.selection else []
    indice = linhas[0] if linhas else 0
    lead_id = int(vis.iloc[indice]["id"])
    st.caption("Clique numa linha para abrir a ficha. A primeira é a mais urgente.")

lead = consultas.lead(lead_id)
status_contato = lgpd.status_contato(lead_id)
trat = consultas.ultimo_tratamento(lead_id) or {}
res = trat.get("resultado") or {}
contato = consultas.contato(lead_id) or {}
linha_fila = vis.iloc[indice]

with ficha:
    nome = lead["nome_fantasia"] or lead["razao_social"]
    prazo = linha_fila["prazo"]
    tipo_prazo = "erro" if linha_fila["atrasado"] else "alerta" if linha_fila["retorno_hoje"] else ""
    st.html(
        f"<h3 style='margin:0 0 6px 0'>{html.escape(nome)}</h3>"
        f"{componentes.selo_nota(lead['nota_final'], lead['classificacao'])} {ui.selo_html(lead['etapa'], 'info')} "
        + (ui.selo_html(prazo, tipo_prazo) if prazo else "")
        + (f" {ui.selo_simulado('Base fictícia')}" if lead["base_ficticia"] else "")
    )
    st.caption(
        f"{lead['setor'] or 'Setor não informado'} · {lead['porte'] or 'porte não informado'} · "
        f"{lead['cidade'] or ''}{'/' + lead['uf'] if lead['uf'] else ''}"
    )
    if status_contato == "pendente":
        st.warning(
            "Lead liberado para análise e priorização. Contato ainda pendente de base legal "
            "documentada em Governança & LGPD. Você pode registrar notas internas e qualificar a oportunidade."
        )
    if contato:
        st.caption(
            f"Contato: {contato.get('nome') or 'sem nome'}"
            f"{' · ' + contato['cargo'] if contato.get('cargo') else ''} · {contato.get('email') or 'sem e-mail'} · "
            f"{contato.get('telefone') or 'sem telefone'}"
        )

    abas = st.tabs(["Por que este lead", "Oferta", "Roteiro", "Cadência e atividade", "BANT", "Corrigir a IA", "Ações"])

    with abas[0]:
        if res:
            st.markdown(res["justificativa"])
        componentes.decomposicao(trat)
        if res.get("dores_provaveis"):
            st.markdown("**Dores prováveis:** " + "; ".join(res["dores_provaveis"]))

    with abas[1]:
        recs = trat.get("recomendacoes", [])
        principal = next((r for r in recs if r["tipo"] == "principal"), None)
        comp = [r for r in recs if r["tipo"] == "complementar"]
        componentes.oferta(lead["solucao_principal"], comp, principal["motivo"] if principal else "")
        sol = catalogo.por_id().get(lead["solucao_principal"] or "")
        perguntas = res.get("perguntas_descoberta") or (sol["perguntas_descoberta"] if sol else [])
        if perguntas:
            ui.rotulo("Perguntas de descoberta")
            for p in perguntas:
                st.markdown(f"- {p}")
        if principal:
            with st.expander("Caminho no grafo que justificou a oferta"):
                componentes.caminho_grafo(principal)

    with abas[2]:
        if res:
            componentes.roteiro(res)
        else:
            st.caption("Sem roteiro gerado.")

    with abas[3]:
        passos = consultas.cadencia(lead_id)
        if passos:
            ui.rotulo("Cadência sugerida")
            for p in passos:
                previsto = tempo.fmt(p["previsto_para"], com_hora=False)
                feito = st.checkbox(f"D{p['dia']} · {p['canal']} · {p['descricao']} (até {previsto})",
                                    value=bool(p["feito_em"]), key=f"passo_{p['id']}")  # fmt: skip
                if feito != bool(p["feito_em"]):
                    comercial.marcar_passo(p["id"], feito, usuario)
                    st.rerun()
        ui.rotulo("Registrar atividade")
        with st.form(f"atividade_{lead_id}", clear_on_submit=True):
            a, b = st.columns(2)
            tipo = a.selectbox(
                "Tipo", comercial.TIPOS_ATIVIDADE if status_contato == "liberado" else ["Nota"]
            )
            resultado = b.selectbox("Resultado", comercial.RESULTADOS)
            anotacao = st.text_area("Anotação", max_chars=1000, placeholder="O que foi conversado.")
            a, b = st.columns([2, 1])
            proxima = a.text_input("Próxima ação", max_chars=180)
            retorno = b.date_input("Retorno em", value=None, format="DD/MM/YYYY")
            salvar = st.form_submit_button("Registrar", type="primary")
        if salvar:
            try:
                retorno_iso = tempo.iso(datetime.combine(retorno, time(9, 0), tzinfo=tempo.FUSO)) if retorno else None
                etapa = comercial.registrar_atividade(lead_id, usuario, tipo, resultado, anotacao, proxima, retorno_iso)
            except (ValueError, estados.TransicaoInvalida) as erro:
                st.error(str(erro))
            else:
                st.session_state["fila_msg"] = f"Atividade registrada. Etapa: {etapa}."
                st.rerun()
        historico = consultas.atividades(lead_id)
        if historico:
            ui.rotulo("Histórico")
            for at in historico[:8]:
                st.caption(
                    f"{tempo.fmt(at['registrada_em'])} · {at['tipo']} · {at['resultado'] or ''} · {at['usuario'] or ''}"
                )
                if at["anotacao"]:
                    st.text(at["anotacao"])

    with abas[4]:
        atual = consultas.bant(lead_id) or {}
        with st.form(f"bant_{lead_id}"):
            valores = {
                k: st.text_input(rotulo, value=atual.get(k) or "", max_chars=200)
                for k, rotulo in comercial.BANT_CAMPOS.items()
            }
            if st.form_submit_button("Salvar BANT", type="primary"):
                comercial.salvar_bant(lead_id, usuario, valores)
                st.session_state["fila_msg"] = "BANT salvo."
                st.rerun()
        st.caption("Orçamento, autoridade, necessidade e prazo. A Necessidade é obrigatória para qualificar.")

    with abas[5]:
        st.caption("Discordou da IA? Escolha o certo e diga por quê. Concordar também conta: mede a qualidade da IA.")
        with st.form(f"corrigir_{lead_id}"):
            campo = st.radio("O que avaliar", ["solucao", "classificacao"], horizontal=True,
                             format_func={"solucao": "Solução sugerida", "classificacao": "Classificação"}.get)  # fmt: skip
            ids_sol = [s["id"] for s in catalogo.solucoes()]
            a, b = st.columns(2)
            nova_sol = a.selectbox("Solução correta", ids_sol, format_func=catalogo.nome,
                                   index=ids_sol.index(lead["solucao_principal"]) if lead["solucao_principal"] in ids_sol else 0)  # fmt: skip
            nova_classe = b.selectbox("Classificação correta", nota.CLASSES,
                                      index=nota.CLASSES.index(lead["classificacao"]) if lead["classificacao"] in nota.CLASSES else 0)  # fmt: skip
            motivo = st.text_input("Motivo (obrigatório)", max_chars=300)
            if st.form_submit_button("Registrar avaliação", type="primary"):
                try:
                    comercial.corrigir_ia(
                        lead_id, usuario, campo, nova_sol if campo == "solucao" else nova_classe, motivo
                    )
                except ValueError as erro:
                    st.error(str(erro))
                else:
                    st.session_state["fila_msg"] = "Avaliação registrada e enviada para o aprendizado."
                    st.rerun()

    with abas[6]:
        execs = repositorio.usuarios("executivo")
        ui.rotulo("Qualificar e agendar reunião")
        with st.form(f"qualificar_{lead_id}"):
            a, b = st.columns(2)
            dia = a.date_input("Data da reunião", value=hoje + timedelta(days=2), format="DD/MM/YYYY")
            hora = b.time_input("Hora", value=time(10, 0))
            executivo = st.selectbox("Executivo de contas", [e["id"] for e in execs],
                                     format_func={e["id"]: e["nome"] for e in execs}.get)  # fmt: skip
            sugeridas = [lead["solucao_principal"]] + [r["solucao_id"] for r in trat.get("recomendacoes", [])
                                                       if r["tipo"] == "complementar"]  # fmt: skip
            solucoes = st.multiselect("Soluções para a proposta", [s["id"] for s in catalogo.solucoes()],
                                      default=[s for s in sugeridas if s], format_func=catalogo.nome, placeholder="Selecione")  # fmt: skip
            obs = st.text_input("Observação para o executivo", max_chars=300)
            qualificar = st.form_submit_button(
                "Qualificar e agendar",
                type="primary",
                icon=":material/event:",
                disabled=status_contato != "liberado",
            )
        if qualificar:
            try:
                quando = tempo.iso(datetime.combine(dia, hora, tzinfo=tempo.FUSO))
                with st.spinner("Gerando o resumo de passagem..."):
                    comercial.qualificar_e_agendar(lead_id, usuario, quando, executivo, solucoes, obs)
            except (ValueError, estados.TransicaoInvalida) as erro:
                st.error(str(erro))
            else:
                st.session_state["fila_msg"] = "Reunião marcada e lead passado ao executivo, com resumo automático."
                st.rerun()

        a, b = st.columns(2)
        with a, st.form(f"nutricao_{lead_id}"):
            ui.rotulo("Mover para nutrição")
            motivo_n = st.text_input("Motivo", max_chars=200, key=f"mn_{lead_id}")
            if st.form_submit_button("Mover para nutrição"):
                try:
                    comercial.mover_nutricao(lead_id, usuario, motivo_n)
                except (ValueError, estados.TransicaoInvalida) as erro:
                    st.error(str(erro))
                else:
                    st.session_state["fila_msg"] = "Lead movido para nutrição."
                    st.rerun()
        with b, st.form(f"perdido_{lead_id}"):
            ui.rotulo("Marcar como perdido")
            motivo_p = st.selectbox("Motivo", estados.MOTIVOS, key=f"mp_{lead_id}")
            detalhe_p = st.text_input("Detalhe (obrigatório se Outro)", max_chars=200, key=f"dp_{lead_id}")
            if st.form_submit_button("Marcar como perdido"):
                try:
                    comercial.fechar(lead_id, usuario, ganho=False, motivo=motivo_p, detalhe=detalhe_p)
                except (ValueError, estados.TransicaoInvalida) as erro:
                    st.error(str(erro))
                else:
                    st.session_state["fila_msg"] = "Lead perdido. Resultado enviado para o aprendizado do modelo."
                    st.rerun()

with st.expander("Ver fila completa em tabela"):
    st.dataframe(pd.DataFrame(vis[["id", "empresa", "nota_final", "classificacao", "solucao", "etapa", "prazo", "uf"]]),
                 hide_index=True, width="stretch")  # fmt: skip
