"""Indicadores: negócio (funil, SLA, receita, segmentos) e técnica (MLOps e observabilidade)."""

from __future__ import annotations

import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import catalogo
from banco import metricas
from banco.conexao import conectar
from dados.ingestao import ORIGENS_ROTULO
from ia import drift, observabilidade, propensao, segmentos
from nucleo import componentes, tempo, ui

usuario = st.session_state["usuario"]
CORES = ["#2DD4BF", "#60A5FA", "#F5C778", "#A78BFA", "#FCA5A5", "#8FA3BC"]

ui.cabecalho(
    "Indicadores",
    "Métricas operacionais ligadas às de negócio, e a saúde técnica dos modelos e das chamadas de IA.",
    secao="Inteligência",
)
if msg := st.session_state.pop("ind_msg", None):
    st.success(msg)
periodo = st.segmented_control("Período", ["7 dias", "30 dias", "tudo"], default="30 dias")
desde = tempo.inicio_periodo(periodo or "tudo")
negocio, tecnica = st.tabs(["Negócio", "Técnica (MLOps e observabilidade)"])


def grafico(fig, altura=300):
    st.plotly_chart(componentes.layout_grafico(fig, altura), width="stretch", config={"displayModeBar": False})


# ================= NEGÓCIO =================
with negocio:
    df = metricas.leads_tempo(desde)
    funil = metricas.funil(desde)
    if df.empty:
        st.info("Sem leads no período.")
    else:
        t = metricas.tempos_e_sla(df, tempo.iso())
        rec = metricas.receita(df)
        a, b, c, d = st.columns(4)
        a.metric("Tempo até o primeiro contato", f"{t['mediana_h']:.1f} h" if t["mediana_h"] is not None else "sem dados",
                 "mediana", delta_color="off", delta_arrow="off")  # fmt: skip
        b.metric("SLA cumprido", f"{t['sla_pct']:.0%}" if t["sla_pct"] is not None else "sem dados",
                 f"{t['vencidos_sem_contato']} vencidos sem contato", delta_color="off", delta_arrow="off")  # fmt: skip
        c.metric("Receita prevista (mês)", ui.reais(rec["prevista"]),
                 "pipeline " + ui.reais(rec["pipeline"]), delta_color="off", delta_arrow="off")  # fmt: skip
        d.metric("Receita ganha (mês)", ui.reais(rec["ganha"]), "valores fictícios",
                 delta_color="off", delta_arrow="off")  # fmt: skip
        st.caption(
            "Receita prevista = valor mensal × probabilidade da etapa (Qualificado 15%, Reunião 30%, Proposta 60%)."
        )

        e, f = st.columns(2)
        with e:
            ui.rotulo("Conversão por etapa")
            dados_funil = pd.DataFrame(funil)
            fig = go.Figure(go.Funnel(y=dados_funil["etapa"], x=dados_funil["leads"], textinfo="value+percent previous",
                                      marker=dict(color="#2DD4BF")))  # fmt: skip
            grafico(fig, 360)
        with f:
            ui.rotulo("Reuniões e ganhos por BDR")
            por_bdr = df[df["responsavel"].notna()].groupby("responsavel").agg(
                Leads=("id", "count"), Reuniões=("reuniao_em", "count"), Ganhos=("ganho_em", "count")).reset_index()  # fmt: skip
            fig = px.bar(por_bdr.melt(id_vars="responsavel", value_vars=["Leads", "Reuniões", "Ganhos"]),
                         x="responsavel", y="value", color="variable", barmode="group", color_discrete_sequence=CORES,
                         labels={"responsavel": "", "value": "", "variable": ""})  # fmt: skip
            grafico(fig, 360)

        g, h = st.columns(2)
        with g:
            ui.rotulo("Por origem")
            por_origem = df.groupby("origem").agg(leads=("id", "count"), ganhos=("ganho_em", "count")).reset_index()
            por_origem["origem"] = por_origem["origem"].map(lambda o: ORIGENS_ROTULO.get(o, o))
            por_origem["conversao"] = por_origem["ganhos"] / por_origem["leads"]
            fig = px.bar(por_origem, x="origem", y="leads", text=por_origem["conversao"].map("{:.0%} ganhos".format),
                         color_discrete_sequence=CORES, labels={"origem": "", "leads": "Leads"})  # fmt: skip
            fig.update_traces(textposition="outside", textangle=0, cliponaxis=False)
            grafico(fig)
        with h:
            ui.rotulo("Por solução recomendada")
            por_sol = df[df["solucao_principal"].notna()].groupby("solucao_principal").agg(
                Leads=("id", "count"), Reuniões=("reuniao_em", "count"), Ganhos=("ganho_em", "count")).reset_index()  # fmt: skip
            por_sol["solucao"] = por_sol["solucao_principal"].map(catalogo.nome)
            por_sol = por_sol.sort_values("Leads").tail(10)
            fig = px.bar(por_sol, y="solucao", x=["Leads", "Reuniões", "Ganhos"], orientation="h", barmode="group",
                         color_discrete_sequence=CORES, labels={"solucao": "", "value": "", "variable": ""})  # fmt: skip
            grafico(fig, 380)

        ui.rotulo("Segmentos de clientes (K-Means)")
        perfis = segmentos.perfis()
        with conectar() as con:
            feats = [(json.loads(r["features"]), r["cluster"]) for r in con.execute(
                "SELECT features, cluster FROM leads_features WHERE cluster IS NOT NULL")]  # fmt: skip
        if feats:
            pts = pd.DataFrame([{**f, "perfil": perfis.get(c, {}).get("nome", f"Perfil {c + 1}").split(":")[0]}
                                for f, c in feats])  # fmt: skip
            i, j = st.columns([1.3, 1])
            with i:
                fig = px.scatter(pts, x="log_funcionarios", y="n_sinais", color="perfil", color_discrete_sequence=CORES,
                                 labels={"log_funcionarios": "Tamanho (log de funcionários)", "n_sinais": "Sinais", "perfil": ""},
                                 opacity=0.75)  # fmt: skip
                fig.update_traces(marker=dict(size=9), selector=dict(mode="markers"))
                grafico(fig, 340)
            with j:
                for _c, p in sorted(perfis.items()):
                    sols = ", ".join(catalogo.nome(s) for s in p["solucoes_ganhas"]) or "sem ganhos ainda"
                    st.html(f'<div class="fg-cartao"><b>{p["nome"]}</b><br>'
                            f'<span style="color:var(--fg-texto-2)">{p["tamanho"]} no histórico · {p["taxa_ganho"]:.0%} '
                            f"de ganho · mais vendidas: {sols}</span></div>")  # fmt: skip
        st.caption("Os perfis do K-Means também entram como nós no grafo de recomendação.")

# ================= TÉCNICA =================
with tecnica:
    ativo = propensao.registro_ativo()
    versoes = propensao.historico_versoes()
    a, b = st.columns([2.2, 1.3], vertical_alignment="bottom")
    with a:
        ui.rotulo("Modelo de propensão de conversão")
        if ativo:
            st.markdown(f"Versão ativa: **{ativo['versao']}**, treinada em {tempo.fmt(ativo['treinado_em'])} com "
                        f"{ativo['n_treino']} exemplos de treino e {ativo['n_teste']} de teste. "
                        "Fontes: " + ", ".join(f"{n} {'da base fictícia' if f == 'base_ficticia' else 'do funil'}"
                                             for f, n in ativo["metricas"].get("fontes", {}).items()) + ".")  # fmt: skip
    with b:
        if st.button("Retreinar com os resultados do funil", type="primary", icon=":material/model_training:"):
            with st.spinner("Treinando regressão logística e árvore de decisão..."):
                r = propensao.treinar(usuario["login"])
                segmentos.treinar(usuario["login"])
            st.session_state["ind_msg"] = f"Nova versão registrada: {r['versao']} ({r['linhas']} exemplos)."
            st.rerun()
    if ativo:
        versao_base = ativo["versao"].split("-")[0]
        par = [v for v in versoes if v["versao"].startswith(versao_base + "-")]
        comp = pd.DataFrame([{"Algoritmo": "Regressão logística" if v["algoritmo"] == "regressao_logistica" else "Árvore de decisão",
                              "AUC": v["metricas"]["auc"], "Precisão": v["metricas"]["precisao"],
                              "Recall": v["metricas"]["recall"], "Acurácia": v["metricas"]["acuracia"],
                              "Ativo": "sim" if v["ativo"] else ""} for v in par])  # fmt: skip
        st.dataframe(comp, hide_index=True, width="stretch")
        c, d = st.columns(2)
        with c:
            ui.rotulo("Matriz de confusão (modelo ativo, base de teste)")
            mc = ativo["metricas"]["matriz_confusao"]
            fig = px.imshow(mc, text_auto=True, x=["Previu perda", "Previu ganho"], y=["Perdeu", "Ganhou"],
                            color_continuous_scale=[[0, "#111C2E"], [1, "#2DD4BF"]])  # fmt: skip
            fig.update_coloraxes(showscale=False)
            grafico(fig, 280)
        with d:
            ui.rotulo("Variáveis que mais pesam")
            imp = pd.DataFrame(ativo["metricas"]["importancias"][:8])
            imp["sentido"] = (
                imp["efeito"].map({"aumenta": "Aumenta a chance", "reduz": "Reduz a chance"}).fillna("Importância")
            )
            fig = px.bar(imp.iloc[::-1], x="peso", y="variavel", orientation="h", color="sentido",
                         color_discrete_map={"Aumenta a chance": "#2DD4BF", "Reduz a chance": "#FCA5A5", "Importância": "#60A5FA"},
                         labels={"peso": "Peso", "variavel": "", "sentido": ""})  # fmt: skip
            grafico(fig, 280)
        with st.expander("Histórico de versões"):
            st.dataframe(pd.DataFrame([{"versão": v["versao"], "treinado em": tempo.fmt(v["treinado_em"]),
                                        "AUC": v["metricas"]["auc"], "treino": v["n_treino"], "ativo": "sim" if v["ativo"] else ""}
                                       for v in versoes]), hide_index=True, width="stretch")  # fmt: skip
        st.caption("O histórico inicial é sintético (base fictícia). Com uso real, cada Ganho ou Perdido do funil entra como "
                   "exemplo novo no retreino.")  # fmt: skip

    st.divider()
    ui.rotulo("Drift (PSI)")
    dr = drift.calcular()
    tabela = pd.DataFrame(dr["linhas"])
    st.dataframe(tabela, hide_index=True, width="stretch", column_config={
        "variavel": "Variável", "referencia": "Referência", "n_ref": "N ref.", "n_atual": "N atual", "psi": "PSI",
        "situacao": "Situação"})  # fmt: skip
    if dr["alerta"]:
        st.warning(f"Drift acima do limite ({dr['limite']}). Avalie retreinar o modelo e revisar o ICP.")
    else:
        st.caption(f"Limite de alerta: PSI {dr['limite']} (ajustável em Governança).")

    st.divider()
    ui.rotulo("Observabilidade das chamadas de IA")
    obs = observabilidade.resumo(desde)
    conc = metricas.concordancia()
    a, b, c, d, e = st.columns(5)
    a.metric("Latência média do LLM", f"{obs['latencia'] / 1000:.1f} s" if obs["latencia"] else "0 s")
    b.metric("Tokens", f"{obs['t_in'] + obs['t_out']:,}".replace(",", "."))
    c.metric("Custo por 1.000 leads", f"US$ {obs['custo_por_lead'] * 1000:.2f}", f"total US$ {obs['custo']:.4f}",
             delta_color="off", delta_arrow="off")  # fmt: skip
    d.metric("Uso do plano B", f"{obs['taxa_plano_b']:.0%}", f"{obs['caches']} respostas do cache",
             delta_color="off", delta_arrow="off")  # fmt: skip
    e.metric("Concordância BDR x IA", f"{conc['concordancia']:.0%}" if conc["concordancia"] is not None else "sem dados",
             f"{conc['avaliacoes']} avaliações", delta_color="off", delta_arrow="off")  # fmt: skip
    with conectar() as con:
        eventos = pd.read_sql_query(
            "SELECT ocorrido_em, agente, provedor, modelo, versao_prompt, latencia_ms, tokens_entrada, tokens_saida, "
            "custo_estimado, plano_b, cache, erro FROM eventos_ia ORDER BY id DESC LIMIT 200", con)  # fmt: skip
    if not eventos.empty:
        eventos["dia"] = eventos["ocorrido_em"].str[:10]
        por_dia = eventos.groupby(["dia", "provedor"]).size().reset_index(name="chamadas")
        fig = px.bar(por_dia, x="dia", y="chamadas", color="provedor", color_discrete_sequence=CORES,
                     labels={"dia": "", "chamadas": "Chamadas", "provedor": ""})  # fmt: skip
        grafico(fig, 240)
        with st.expander("Últimas chamadas"):
            eventos["ocorrido_em"] = eventos["ocorrido_em"].map(tempo.fmt)
            st.dataframe(eventos.drop(columns="dia"), hide_index=True, width="stretch")
    st.caption("Custo estimado com o preço por milhão de tokens configurado em Governança. Lotes de até 15 leads por "
               "chamada e cache por empresa reduzem o custo de escala.")  # fmt: skip
