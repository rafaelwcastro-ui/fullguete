"""Dashboard: o funil de ponta a ponta e o que pede ação agora."""

from __future__ import annotations

import streamlit as st

import catalogo
from banco import repositorio
from nucleo import config, ui

ui.cabecalho(
    "Dashboard",
    "Objetivo do Fullguete: aumentar a receita com soluções Equifax e a produtividade do BDR, "
    "com a IA priorizando e explicando cada lead.",
    secao="Visão geral",
)
if config.simulado():
    st.html(ui.selo_simulado("Base fictícia"))

ETAPAS_FUNIL = [
    ("Capturados", None),
    ("Tratados", {"Tratado", "Na fila do BDR", "Em nutrição", "Revisão humana", "Descartado", "Retido LGPD"}),
    ("Qualificados", {"Qualificado"}),
    ("Com o BDR", {"Na fila do BDR", "Em contato"}),
    ("Reuniões", {"Reunião marcada"}),
    ("Propostas", {"Proposta"}),
    ("Ganhos", {"Ganho"}),
]
por_etapa = repositorio.leads_por_etapa()
total = sum(por_etapa.values())

ui.rotulo("Funil de ponta a ponta")
colunas = st.columns(len(ETAPAS_FUNIL))
for coluna, (nome, etapas) in zip(colunas, ETAPAS_FUNIL, strict=True):
    valor = total if etapas is None else sum(por_etapa.get(e, 0) for e in etapas)
    coluna.metric(nome, valor)

if total == 0:
    st.info(
        "Ainda não há leads no funil. Comece pela página Captura de leads: cadastre uma empresa "
        "ou simule a chegada de leads do site."
    )

ui.rotulo("Base carregada")
historico = repositorio.resumo_historico()
a, b, c = st.columns(3)
a.metric("Soluções no catálogo", len(catalogo.solucoes()))
b.metric(
    "Leads históricos para treino",
    historico["total"],
    f"{historico['ganhos']} ganhos",
    delta_color="off",
    delta_arrow="off",
)
c.metric("Usuários ativos", len(repositorio.usuarios()))
