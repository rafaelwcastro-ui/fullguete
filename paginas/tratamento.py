"""Tratamento IA: ICP, execução do lote pelos agentes, fichas e revisão humana."""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

import catalogo
import prompts
from banco import consultas, repositorio
from dados.features import PORTES
from ia import nota, orquestrador, provedor
from nucleo import componentes, estados, revisao, ui

usuario = st.session_state["usuario"]

ui.cabecalho(
    "Tratamento IA",
    "Sete agentes higienizam, enriquecem, checam a LGPD, qualificam, recomendam a solução Equifax, escrevem o "
    "roteiro e decidem o destino de cada lead.",
    secao="Prospecção",
)

aba_lote, aba_lista, aba_revisao, aba_icp = st.tabs(["Tratar leads", "Leads tratados", "Revisão humana", "ICP"])

# ---------- ICP ----------
with aba_icp:
    icp = repositorio.icp_ativo()
    st.caption("O perfil de cliente ideal orienta a nota de aderência. Cada mudança gera uma versão nova.")
    with st.form("icp"):
        nome = st.text_input("Nome da versão", value=icp["nome"] if icp else "ICP")
        descricao = st.text_area("Descrição livre do cliente ideal", value=icp["descricao"] if icp else "", height=110)
        a, b = st.columns(2)
        setores = a.text_input("Setores alvo (separe por vírgula)", value=", ".join(icp["setores"]) if icp else "")
        portes = b.multiselect("Portes alvo", PORTES, default=icp["portes"] if icp else [], placeholder="Selecione")
        palavras = st.text_input("Palavras chave (separe por vírgula)",
                                 value=", ".join(icp["palavras_chave"]) if icp else "")  # fmt: skip
        st.caption("Localização não faz parte do ICP: região não entra na nota.")
        salvar = st.form_submit_button("Salvar nova versão do ICP", type="primary")
    if salvar:
        if not descricao.strip():
            st.error("Descreva o cliente ideal.")
        else:
            novo = repositorio.salvar_icp({
                "nome": nome.strip() or "ICP", "descricao": descricao.strip(), "portes": portes,
                "setores": [s.strip() for s in setores.split(",") if s.strip()],
                "palavras_chave": [p.strip() for p in palavras.split(",") if p.strip()],
            }, usuario["login"])  # fmt: skip
            st.success(f"Versão {novo} salva e ativada. Reprocesse os leads para aplicar.")
    versoes = consultas.icp_versoes()
    if not versoes.empty:
        ui.rotulo("Versões salvas")
        versoes["ativa"] = versoes["ativa"].map({1: "Ativa", 0: ""})
        st.dataframe(versoes[["id", "criada_em", "criada_por", "nome", "ativa"]], hide_index=True, width="stretch",
                     column_config={"id": "Versão", "criada_em": "Criada em", "criada_por": "Por", "nome": "Nome",
                                    "ativa": "Status"})  # fmt: skip

# ---------- tratar leads ----------
with aba_lote:
    capturados = consultas.leads([estados.CAPTURADO])
    reprocessaveis = consultas.leads(sorted(orquestrador.TRATAVEIS - {estados.CAPTURADO}))
    tem_llm = provedor.disponivel()
    a, b, c = st.columns(3)
    a.metric("Aguardando tratamento", len(capturados))
    b.metric("Podem ser reprocessados", len(reprocessaveis))
    c.metric("Motor", f"Gemini ({provedor.modelo()})" if tem_llm else "Análise local")
    if not tem_llm:
        st.info("Sem chave de IA: o tratamento usa a análise local (TF-IDF, regras e grafo), com o mesmo formato.")

    with st.form("tratar"):
        alvo = st.radio("O que tratar", ["Todos os capturados", "Escolher leads", "Reprocessar leads já tratados"],
                        horizontal=True)  # fmt: skip
        opcoes = pd.concat([capturados, reprocessaveis]) if not capturados.empty or not reprocessaveis.empty else None
        escolhidos = []
        if opcoes is not None and not opcoes.empty:
            rotulos = {int(r.id): f"#{r.id} {r.razao_social} · {r.etapa}" for r in opcoes.itertuples()}
            escolhidos = st.multiselect(
                "Leads (para escolher ou reprocessar)", list(rotulos), format_func=rotulos.get, placeholder="Selecione"
            )
        usar_llm = st.toggle("Usar IA generativa (Gemini)", value=tem_llm, disabled=not tem_llm)
        executar = st.form_submit_button("Executar agentes", type="primary", icon=":material/play_arrow:")
    if executar:
        ids = capturados["id"].tolist() if alvo == "Todos os capturados" else [int(i) for i in escolhidos]
        if not ids:
            st.warning("Nenhum lead para tratar.")
        else:
            barra = st.progress(0.0, text="Começando...")
            resumo = orquestrador.tratar(ids, usuario["login"], usar_llm=usar_llm,
                                         progresso=lambda etapa, p: barra.progress(min(p, 1.0), text=etapa))  # fmt: skip
            barra.empty()
            st.session_state["ultimo_lote"] = resumo["lote"]
            destinos = ", ".join(f"{n} em {d}" for d, n in resumo["destinos"].items())
            st.success(f"{resumo['total']} lead(s) tratados em {resumo['tempo_s']} s: {destinos}.")
            if resumo.get("planos_b"):
                st.warning(f"{resumo['planos_b']} lead(s) caíram no plano B local (falha ou JSON inválido do LLM).")

    lotes = consultas.lotes_recentes()
    if lotes:
        ui.rotulo("Linha de etapas do lote")
        rotulos_lote = {
            x["lote"]: f"{componentes.quando(x['inicio'])} · {x['n']} lead(s) · {x['motor']}" for x in lotes
        }
        padrao = st.session_state.get("ultimo_lote")
        indice = list(rotulos_lote).index(padrao) if padrao in rotulos_lote else 0
        lote = st.selectbox("Lote", list(rotulos_lote), index=indice, format_func=rotulos_lote.get)
        componentes.linha_etapas(orquestrador.etapas_do_lote(lote))

# ---------- leads tratados ----------
with aba_lista:
    tratados = consultas.tratados()
    if tratados.empty:
        st.info("Nenhum lead tratado ainda.")
    else:
        nomes = catalogo.por_id()
        tratados["solucao"] = tratados["solucao_principal"].map(lambda s: nomes.get(s, {}).get("nome", ""))
        tratados["empresa"] = tratados["nome_fantasia"].fillna(tratados["razao_social"])
        a, b, c = st.columns(3)
        filtro_destino = a.multiselect("Etapa atual", sorted(tratados["etapa"].unique()), placeholder="Todas")
        filtro_classe = b.multiselect("Classificação", nota.CLASSES, placeholder="Todas")
        filtro_uf = c.multiselect(
            "UF (filtro de região)", sorted(tratados["uf"].dropna().unique()), placeholder="Todas"
        )
        vis = tratados
        if filtro_destino:
            vis = vis[vis["etapa"].isin(filtro_destino)]
        if filtro_classe:
            vis = vis[vis["classificacao"].isin(filtro_classe)]
        if filtro_uf:
            vis = vis[vis["uf"].isin(filtro_uf)]
        colunas = ["lead_id", "empresa", "nota_final", "classificacao", "solucao", "etapa", "motor", "uf"]
        st.dataframe(vis[colunas], hide_index=True, width="stretch", column_config={
            "lead_id": st.column_config.NumberColumn("#", width="small"), "empresa": "Empresa",
            "nota_final": st.column_config.ProgressColumn("Nota", min_value=0, max_value=100, format="%.0f"),
            "classificacao": "Classe", "solucao": "Solução principal", "etapa": "Etapa", "motor": "Motor", "uf": "UF",
        })  # fmt: skip

        exportar = vis[colunas + ["nota_aderencia", "propensao", "confianca", "versao_prompt", "modelo"]].copy()
        for col in exportar.select_dtypes(include=["object", "string"]):
            exportar[col] = exportar[col].map(
                lambda v: "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@") else v)  # fmt: skip
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            exportar.to_excel(w, index=False, sheet_name="Ranking")
        d1, d2, _ = st.columns([1, 1, 3])
        d1.download_button("Exportar CSV", exportar.to_csv(index=False).encode("utf-8-sig"), "ranking_fullguete.csv",
                           "text/csv", on_click="ignore")  # fmt: skip
        d2.download_button("Exportar Excel", buf.getvalue(), "ranking_fullguete.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", on_click="ignore")  # fmt: skip

        st.divider()
        ui.rotulo("Ficha de tratamento")
        opcoes_ficha = {int(r.lead_id): f"#{r.lead_id} {r.empresa} · {r.classificacao or 'sem nota'}"
                        for r in vis.itertuples()}  # fmt: skip
        if opcoes_ficha:
            escolhido = st.selectbox("Lead", list(opcoes_ficha), format_func=opcoes_ficha.get, key="ficha_trat")
            lead = consultas.lead(escolhido)
            trat = consultas.ultimo_tratamento(escolhido)
            res = trat.get("resultado") or {}
            st.html(f"<h3 style='margin:0'>{lead['nome_fantasia'] or lead['razao_social']}</h3>"
                    f"{componentes.selo_nota(lead['nota_final'], lead['classificacao'])} "
                    f"{ui.selo_html(lead['etapa'], 'info')}"
                    + (f" {ui.selo_simulado('Base fictícia')}" if lead["base_ficticia"] else ""))  # fmt: skip
            st.caption(
                f"Motor: {trat['motor']} · modelo {trat['modelo'] or 'local'} · prompt {trat['versao_prompt'] or '-'} · "
                f"propensão {trat['modelo_propensao'] or '-'} · custo US$ {trat['custo_estimado']:.4f}"
                + (" · plano B" if trat["plano_b"] else "")
            )
            esq, dir_ = st.columns([1.2, 1], gap="large")
            with esq:
                ui.rotulo("Por que esta nota")
                componentes.decomposicao(trat)
                if res:
                    st.markdown(f"**Justificativa.** {res['justificativa']}")
                    st.markdown("**Dores prováveis.** " + "; ".join(res["dores_provaveis"]))
                    if res.get("sinais_risco"):
                        st.warning("Sinais de risco: " + "; ".join(res["sinais_risco"]))
            with dir_:
                ui.rotulo("Solução Equifax recomendada")
                recs = trat.get("recomendacoes", [])
                principal = next((r for r in recs if r["tipo"] == "principal"), None)
                comp = [r for r in recs if r["tipo"] == "complementar"]
                if lead["solucao_principal"] and principal and lead["solucao_principal"] != principal["solucao_id"]:
                    st.caption(f"Ajustada por uma pessoa. A IA sugeriu {catalogo.nome(principal['solucao_id'])}.")
                componentes.oferta(lead["solucao_principal"], comp, principal["motivo"] if principal else "")
                ui.rotulo("Caminho no grafo")
                if principal:
                    componentes.caminho_grafo(principal)
            with st.expander("Dados enriquecidos"):
                componentes.dados_enriquecidos(lead)
            with st.expander("Etapas dos agentes para este lead"):
                componentes.detalhes_etapas(trat["etapas"])
            if res:
                with st.expander("Rascunhos do Redator"):
                    st.markdown("**Perguntas de descoberta**")
                    for p in res["perguntas_descoberta"]:
                        st.markdown(f"- {p}")
                    componentes.roteiro(res)

# ---------- revisão humana ----------
with aba_revisao:
    if msg := st.session_state.pop("revisao_msg", None):
        st.success(msg)
    fila = consultas.leads([estados.REVISAO])
    st.caption("Casos de baixa confiança ou com risco. Toda decisão exige motivo e fica na trilha de auditoria.")
    if fila.empty:
        st.success("Nenhum caso aguardando revisão.")
    else:
        rotulos_rev = {int(r.id): f"#{r.id} {r.nome_fantasia or r.razao_social} · nota {r.nota_final or 0:.0f}"
                       for r in fila.itertuples()}  # fmt: skip
        escolhido = st.selectbox("Caso", list(rotulos_rev), format_func=rotulos_rev.get, key="rev_lead")
        lead = consultas.lead(escolhido)
        trat = consultas.ultimo_tratamento(escolhido) or {}
        d = trat.get("decomposicao") or {}
        res = trat.get("resultado") or {}
        st.html(componentes.selo_nota(lead["nota_final"], lead["classificacao"]))
        motivo_ia = res.get("motivo_revisao") or d.get("explicacao_destino", "")
        st.markdown(f"**Por que veio para revisão:** {motivo_ia}")
        if d.get("riscos"):
            st.warning("Riscos: " + "; ".join(d["riscos"]))
        componentes.oferta(lead["solucao_principal"], motivo=res.get("solucao_principal", {}).get("motivo", ""))
        with st.form(f"revisao_{escolhido}"):
            decisao = st.radio("Decisão", ["aprovar", "ajustar", "descartar"], horizontal=True, format_func={
                "aprovar": "Aprovar como está", "ajustar": "Ajustar solução ou classificação", "descartar": "Descartar"}.get)  # fmt: skip
            ids_sol = [s["id"] for s in catalogo.solucoes()]
            a, b = st.columns(2)
            nova_sol = a.selectbox("Solução (se ajustar)", ids_sol, format_func=catalogo.nome,
                                   index=ids_sol.index(lead["solucao_principal"]) if lead["solucao_principal"] in ids_sol else 0)  # fmt: skip
            nova_classe = b.selectbox("Classificação (se ajustar)", nota.CLASSES,
                                      index=nota.CLASSES.index(lead["classificacao"]) if lead["classificacao"] in nota.CLASSES else 1)  # fmt: skip
            motivo_desc = st.selectbox("Motivo do descarte (se descartar)", estados.MOTIVOS)
            motivo = st.text_area("Motivo da decisão (obrigatório)", max_chars=500)
            enviar = st.form_submit_button("Registrar decisão", type="primary")
        if enviar:
            try:
                final = revisao.resolver(
                    escolhido, usuario, decisao, motivo,
                    solucao_id=nova_sol if decisao == "ajustar" else None,
                    classificacao=nova_classe if decisao == "ajustar" else None,
                    motivo_descarte=motivo_desc,
                )  # fmt: skip
            except (ValueError, estados.TransicaoInvalida) as erro:
                st.error(str(erro))
            else:
                st.session_state["revisao_msg"] = f"Decisão registrada. O lead foi para {final}."
                st.rerun()

with st.expander("Como a nota é calculada"):
    pesos = repositorio.config("pesos_nota")
    limites = repositorio.config("limites_classificacao")
    st.markdown(
        f"- **Nota final** = {pesos['aderencia']:.0%} aderência + {pesos['propensao']:.0%} propensão + "
        f"{pesos['confianca']:.0%} confiança × 100.\n"
        f"- **Quente** ≥ {limites['quente']}, **Morno** {limites['morno']} a {limites['quente'] - 1}, "
        f"**Frio** {limites['frio']} a {limites['morno'] - 1}, **Descartar** abaixo de {limites['frio']}.\n"
        f"- Quente e Morno com confiança ≥ {repositorio.config('confianca_minima_fila')} vão para o BDR; "
        "com confiança baixa, para revisão humana. Frio vai para nutrição.\n"
        "- Nome, e-mail e telefone do contato nunca vão para a IA. A localização não entra na nota.\n"
        "- Pesos e limites são ajustados em Governança & LGPD."
    )
    st.caption(f"Prompt {prompts.VERSAO_ATIVA}, temperatura {prompts.TEMPERATURA}.")
