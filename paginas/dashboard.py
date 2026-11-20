"""Dashboard: o funil de ponta a ponta e o que pede ação agora."""

from __future__ import annotations

import html

import plotly.express as px
import streamlit as st

import catalogo
from banco import metricas, repositorio
from dados.ingestao import ORIGENS_ROTULO
from ia import drift
from nucleo import componentes, estados, tempo, ui

ui.cabecalho(
    "Dashboard",
    "Objetivo: aumentar a receita com soluções Equifax e a produtividade do BDR. A IA qualifica, recomenda e explica; "
    "o time decide.",
    secao="Visão geral",
)

periodo = st.segmented_control("Período", ["hoje", "7 dias", "30 dias", "tudo"], default="30 dias")
desde = tempo.inicio_periodo(periodo or "tudo")
df = metricas.leads_tempo(desde)
if not df.empty and df["base_ficticia"].any():
    st.html(ui.selo_simulado("Base fictícia"))

# ---------- funil ----------
ui.rotulo("Funil de ponta a ponta")
funil = metricas.funil(desde)
destino = {"Capturados": "paginas/captura.py", "Tratados": "paginas/tratamento.py", "Com o BDR": "paginas/fila_bdr.py",
           "Em contato": "paginas/carteira.py", "Qualificados": "paginas/crm_funil.py",
           "Reuniões": "paginas/crm_funil.py", "Propostas": "paginas/crm_funil.py", "Ganhos": "paginas/crm_funil.py"}  # fmt: skip
colunas = st.columns(len(funil))
for coluna, etapa in zip(colunas, funil, strict=True):
    conv = f"{etapa['conversao']:.0%}" if etapa["conversao"] is not None else None
    coluna.metric(etapa["etapa"], etapa["leads"], conv, delta_color="off", delta_arrow="off")
    coluna.page_link(destino[etapa["etapa"]], label="Abrir", icon=":material/arrow_forward:")

if df.empty:
    st.info("Ainda não há leads no período. Comece pela Captura de leads.")
    st.stop()

# ---------- alertas ----------
agora = tempo.iso()
t = metricas.tempos_e_sla(df, agora)
retidos = int((df["etapa"] == estados.RETIDO).sum())
quentes_vencidos = df[(df["etapa"] == estados.FILA_BDR) & df["primeiro_contato_em"].isna()
                      & (df["sla_limite"].fillna("9999") < agora) & (df["classificacao"] == "Quente")]  # fmt: skip
dr = drift.calcular()
pb_atual, pb_anterior = metricas.planos_b_semanais()
alertas = []
if len(quentes_vencidos):
    alertas.append(("erro", f"{len(quentes_vencidos)} lead(s) Quentes sem contato acima do SLA."))
if retidos:
    alertas.append(("alerta", f"{retidos} lead(s) retidos por LGPD aguardando regularização."))
if dr["alerta"]:
    alertas.append(("alerta", "Drift detectado nas notas ou nas variáveis. Veja Indicadores."))
if pb_atual > pb_anterior + 0.1:
    alertas.append(("alerta", f"Uso do plano B subiu para {pb_atual:.0%} nos últimos 7 dias."))
if alertas:
    ui.rotulo("Alertas")
    for tipo, texto in alertas:
        st.html(f'<div class="fg-cartao">{ui.selo_html("Atenção" if tipo == "alerta" else "Urgente", tipo)} '
                f"{html.escape(texto)}</div>")  # fmt: skip

# ---------- quentes aguardando ação ----------
ui.rotulo("Leads quentes aguardando ação")
aguardando = df[(df["classificacao"] == "Quente") & df["etapa"].isin([estados.FILA_BDR, estados.EM_CONTATO])].copy()
if aguardando.empty:
    st.caption("Nenhum lead quente parado.")
else:
    with metricas.conectar() as con:
        nomes = {r["id"]: r["nome_fantasia"] or r["razao_social"] for r in con.execute(
            "SELECT id, nome_fantasia, razao_social FROM leads")}  # fmt: skip

    def _sla(r) -> str:
        if r.etapa != estados.FILA_BDR or not isinstance(r.sla_limite, str):
            return "Em contato"
        horas = tempo.horas_entre(agora, r.sla_limite) or 0
        return f"Atrasado {abs(horas):.0f} h" if horas < 0 else f"Vence em {horas:.0f} h"

    aguardando["empresa"] = aguardando["id"].map(nomes)
    aguardando["solucao"] = aguardando["solucao_principal"].map(catalogo.nome)
    aguardando["sla"] = [_sla(r) for r in aguardando.itertuples()]
    aguardando = aguardando.sort_values(["sla", "nota_final"], ascending=[True, False])
    st.dataframe(aguardando[["empresa", "nota_final", "solucao", "responsavel", "sla"]].head(12), hide_index=True,
                 width="stretch", column_config={
                     "empresa": "Empresa",
                     "nota_final": st.column_config.ProgressColumn("Nota", min_value=0, max_value=100, format="%.0f"),
                     "solucao": "Solução sugerida", "responsavel": "BDR", "sla": "SLA"})  # fmt: skip

# ---------- soluções e origem ----------
a, b = st.columns(2)
with a:
    ui.rotulo("Soluções Equifax mais recomendadas e mais vendidas")
    uso = metricas.recomendadas_e_vendidas().head(8)
    if not uso.empty:
        uso["solucao"] = uso["solucao_id"].map(catalogo.nome)
        uso = uso.rename(columns={"recomendadas": "Recomendadas", "vendidas": "Vendidas"})
        fig = px.bar(uso.iloc[::-1], y="solucao", x=["Recomendadas", "Vendidas"], orientation="h", barmode="group",
                     color_discrete_sequence=["#2DD4BF", "#60A5FA"], labels={"solucao": "", "value": "", "variable": ""})  # fmt: skip
        st.plotly_chart(componentes.layout_grafico(fig, 340), width="stretch", config={"displayModeBar": False})
with b:
    ui.rotulo("Origem dos leads")
    origem = df.groupby("origem").size().reset_index(name="leads")
    origem["origem"] = origem["origem"].map(lambda o: ORIGENS_ROTULO.get(o, o))
    fig = px.bar(origem.sort_values("leads"), y="origem", x="leads", orientation="h",
                 color_discrete_sequence=["#60A5FA"], labels={"origem": "", "leads": "Leads"})  # fmt: skip
    st.plotly_chart(componentes.layout_grafico(fig, 340), width="stretch", config={"displayModeBar": False})

# ---------- números de negócio ----------
rec = metricas.receita(df)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Receita prevista do funil", ui.reais(rec["prevista"]))
c2.metric("Receita ganha", ui.reais(rec["ganha"]))
c3.metric("Primeiro contato (mediana)", f"{t['mediana_h']:.1f} h" if t["mediana_h"] is not None else "sem dados")
c4.metric("SLA cumprido", f"{t['sla_pct']:.0%}" if t["sla_pct"] is not None else "sem dados")
st.caption(f"Valores fictícios. Usuários ativos: {len(repositorio.usuarios())}. "
           f"Base de treino do modelo: {repositorio.resumo_historico()['total']} resultados.")  # fmt: skip
