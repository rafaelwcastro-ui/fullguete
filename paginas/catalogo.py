"""Catálogo de ofertas: soluções Equifax, sinais de cada uma e o grafo."""

from __future__ import annotations

import html

import streamlit as st

import catalogo
from nucleo import ui

ui.cabecalho(
    "Catálogo de ofertas",
    "Soluções B2B da Equifax Brasil que o time comercial oferece. Só o nome dos produtos é usado.",
    secao="Inteligência",
)

regras = catalogo.carregar_regras()
nome_sinal = {s["id"]: s["nome"] for s in regras["sinais"]}
linhas = catalogo.linhas()

filtro = st.segmented_control("Linha", ["Todas", *linhas.values()], default="Todas")
busca = st.text_input("Buscar solução", placeholder="Nome, problema ou sinal", max_chars=80)

for linha_id, linha_nome in linhas.items():
    if filtro not in (None, "Todas", linha_nome):
        continue
    itens = [s for s in catalogo.solucoes() if s["linha"] == linha_id]
    if busca:
        termo = busca.casefold()
        itens = [
            s
            for s in itens
            if termo
            in f"{s['nome']} {s['o_que_resolve']} {' '.join(nome_sinal.get(x, x) for x in s['sinais'])}".casefold()
        ]
    if not itens:
        continue
    ui.rotulo(linha_nome)
    colunas = st.columns(3)
    for i, s in enumerate(itens):
        sinais = " ".join(ui.selo_html(nome_sinal.get(x, x)) for x in s["sinais"])
        with colunas[i % 3]:
            ui.cartao(
                f"<b>{html.escape(s['nome'])}</b>"
                f'<p style="margin:6px 0">{html.escape(s["o_que_resolve"])}</p>'
                f'<p style="color:var(--fg-texto-2);font-size:.85rem;margin:0 0 8px 0">'
                f"Perfil típico: {html.escape(s['perfil_tipico'])}</p>{sinais}"
            )

st.caption(catalogo.carregar()["aviso"])
ui.em_construcao(
    6,
    [
        "Quantas vezes a IA recomendou cada solução e quantas foram vendidas",
        "Visualização do grafo segmento, sinal e solução",
        "Edição das regras do grafo pelo gestor",
    ],
)
