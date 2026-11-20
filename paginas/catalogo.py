"""Catálogo de ofertas: soluções Equifax, sinais, uso pela IA, grafo e regras editáveis."""

from __future__ import annotations

import html
import json

import plotly.graph_objects as go
import streamlit as st

import catalogo
from banco import metricas, repositorio
from ia import grafo
from nucleo import componentes, ui

usuario = st.session_state["usuario"]

ui.cabecalho(
    "Catálogo de ofertas",
    "Soluções B2B da Equifax Brasil que o time comercial oferece. Só o nome dos produtos é usado.",
    secao="Inteligência",
)

regras = catalogo.carregar_regras()
nome_sinal = {s["id"]: s["nome"] for s in regras["sinais"]}
linhas = catalogo.linhas()
uso = metricas.recomendadas_e_vendidas().set_index("solucao_id")

aba_cards, aba_grafo, aba_regras = st.tabs(["Soluções", "Knowledge graph", "Regras do grafo"])

with aba_cards:
    a, b = st.columns([2, 1])
    filtro = a.segmented_control("Linha", ["Todas", *linhas.values()], default="Todas")
    busca = b.text_input("Buscar solução", placeholder="Nome, problema ou sinal", max_chars=80)
    for linha_id, linha_nome in linhas.items():
        if filtro not in (None, "Todas", linha_nome):
            continue
        itens = [s for s in catalogo.solucoes() if s["linha"] == linha_id]
        if busca:
            termo = busca.casefold()
            itens = [s for s in itens if termo in
                     f"{s['nome']} {s['o_que_resolve']} {' '.join(nome_sinal.get(x, x) for x in s['sinais'])}".casefold()]  # fmt: skip
        if not itens:
            continue
        ui.rotulo(linha_nome)
        colunas = st.columns(3)
        for i, s in enumerate(itens):
            rec = int(uso.loc[s["id"], "recomendadas"]) if s["id"] in uso.index else 0
            ven = int(uso.loc[s["id"], "vendidas"]) if s["id"] in uso.index else 0
            sinais = " ".join(ui.selo_html(nome_sinal.get(x, x)) for x in s["sinais"])
            with colunas[i % 3]:
                ui.cartao(
                    f"<b>{html.escape(s['nome'])}</b>"
                    f'<p style="margin:6px 0">{html.escape(s["o_que_resolve"])}</p>'
                    f'<p style="color:var(--fg-texto-2);margin:0 0 8px 0">Perfil típico: {html.escape(s["perfil_tipico"])}</p>'
                    f"{sinais}"
                    f'<p style="margin:10px 0 0 0">{ui.selo_html(f"{rec} recomendações", "destaque")} '
                    f"{ui.selo_html(f'{ven} vendidas', 'info')}</p>"
                )
    st.caption(catalogo.carregar()["aviso"])

with aba_grafo:
    st.caption(
        "Segmento de empresa → sinal ou dor → solução Equifax → linha. O Recomendador percorre este grafo para escolher "
        "as candidatas de cada lead e guarda o caminho que justificou a escolha."
    )
    segs = {s["id"]: s["nome"] for s in regras["segmentos"]}
    foco = st.selectbox("Destacar um segmento", ["Todos", *segs], format_func=lambda s: segs.get(s, "Todos"))
    g = grafo.grafo_atual()
    if foco != "Todos":
        no_seg = f"seg:{foco}"
        sinais_nos = list(g.successors(no_seg))
        sol_nos = {s for n in sinais_nos for s in g.successors(n)}
        linha_nos = {s for n in sol_nos for s in g.successors(n)}
        nos = {no_seg, *sinais_nos, *sol_nos, *linha_nos}
        g = g.subgraph(nos)
    camada = {"segmento": 0, "sinal": 1, "solucao": 2, "linha": 3}
    cores = {"segmento": "#60A5FA", "sinal": "#F5C778", "solucao": "#2DD4BF", "linha": "#A78BFA"}
    por_camada: dict[str, list[str]] = {}
    for no, d in g.nodes(data=True):
        if d["tipo"] in camada:
            por_camada.setdefault(d["tipo"], []).append(no)
    pos = {}
    for tipo, nos in por_camada.items():
        nos.sort(key=lambda n: g.nodes[n]["nome"])
        for i, n in enumerate(nos):
            pos[n] = (camada[tipo], 1 - (i + 0.5) / len(nos))
    fig = go.Figure()
    xs, ys = [], []
    for a_, b_ in g.edges():
        if a_ in pos and b_ in pos:
            xs += [pos[a_][0], pos[b_][0], None]
            ys += [pos[a_][1], pos[b_][1], None]
    fig.add_scatter(x=xs, y=ys, mode="lines", line=dict(color="rgba(143,163,188,.25)", width=1), hoverinfo="skip",
                    showlegend=False)  # fmt: skip
    rotulos = {"segmento": "Segmentos", "sinal": "Sinais e dores", "solucao": "Soluções", "linha": "Linhas"}
    for tipo, nos in por_camada.items():
        fig.add_scatter(
            x=[pos[n][0] for n in nos], y=[pos[n][1] for n in nos], mode="markers+text", name=rotulos[tipo],
            marker=dict(size=10, color=cores[tipo]), text=[g.nodes[n]["nome"] for n in nos],
            textposition="middle right" if tipo != "linha" else "middle left", textfont=dict(size=10),
            hovertext=[g.nodes[n].get("dor", g.nodes[n]["nome"]) for n in nos], hoverinfo="text",
        )  # fmt: skip
    fig.update_xaxes(visible=False, range=[-0.1, 3.6])
    fig.update_yaxes(visible=False)
    st.plotly_chart(componentes.layout_grafico(fig, 900 if foco == "Todos" else 520), width="stretch",
                    config={"displayModeBar": False})  # fmt: skip
    st.caption(f"{g.number_of_nodes()} nós e {g.number_of_edges()} arestas.")

with aba_regras:
    st.caption(
        "As regras ficam em catalogo/regras_grafo.json. Pesos de 0 a 1. Toda mudança é validada antes de salvar."
    )
    texto = st.text_area("Regras (JSON)", json.dumps(regras, ensure_ascii=False, indent=2), height=420,
                         disabled=usuario["papel"] != "gestor")  # fmt: skip
    if usuario["papel"] != "gestor":
        st.caption("Só o gestor edita as regras do grafo.")
    elif st.button("Validar e salvar regras", type="primary"):
        try:
            novas = json.loads(texto)
            problemas = catalogo.validar(regras=novas)
            pesos = [a["peso"] for a in novas["segmento_sinal"] + novas["sinal_solucao"]]
            if any(not 0 <= p <= 1 for p in pesos):
                problemas.append("Todos os pesos precisam estar entre 0 e 1.")
        except (json.JSONDecodeError, KeyError, TypeError) as erro:
            st.error(f"JSON inválido: {erro}")
        else:
            if problemas:
                st.error("Não salvei. Problemas: " + " ".join(problemas))
            else:
                novas["versao"] = int(regras.get("versao", 1)) + 1
                catalogo.ARQ_REGRAS.write_text(json.dumps(novas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                from banco.conexao import conectar

                with conectar() as con:
                    repositorio.auditar(con, usuario["login"], "regras_grafo_editadas", "catalogo", novas["versao"],
                                        {"arestas": len(pesos)})  # fmt: skip
                st.success(f"Regras salvas (versão {novas['versao']}). Reprocesse os leads para aplicar.")
