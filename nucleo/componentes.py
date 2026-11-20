"""Blocos de tela reaproveitados: nota decomposta, caminho no grafo, oferta e roteiro."""

from __future__ import annotations

import html
import json

import plotly.graph_objects as go
import streamlit as st

import catalogo

from . import tempo, ui

COR = {"aderencia": "#2DD4BF", "propensao": "#60A5FA", "confianca": "#F5C778"}
NOME_PARTE = {"aderencia": "Aderência ao ICP", "propensao": "Propensão de conversão", "confianca": "Confiança"}


def layout_grafico(fig: go.Figure, altura: int = 260) -> go.Figure:
    fig.update_layout(
        height=altura, margin=dict(l=8, r=8, t=30, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#E6EDF5", size=12), legend=dict(orientation="h", y=-0.2),
    )  # fmt: skip
    fig.update_xaxes(gridcolor="#1E2B40", zeroline=False)
    fig.update_yaxes(gridcolor="#1E2B40", zeroline=False)
    return fig


def selo_nota(nota_final: float | None, classificacao: str | None) -> str:
    if nota_final is None:
        return ui.selo_html("Sem nota")
    return f"{ui.selo_classificacao(classificacao or '')} {ui.selo_html(f'Nota {nota_final:.0f}')}"


def decomposicao(trat: dict) -> None:
    """Quanto da nota final veio de cada parte. É o XAI do projeto."""
    d = trat.get("decomposicao") or {}
    if "bloqueio" in d:
        st.warning(d["bloqueio"])
        return
    partes = d.get("partes", {})
    pesos = d.get("pesos", {})
    if not partes:
        st.caption("Sem decomposição registrada.")
        return
    fig = go.Figure()
    for chave, valor in partes.items():
        fig.add_bar(y=["Nota final"], x=[valor], orientation="h", name=f"{NOME_PARTE[chave]} ({valor:.0f})",
                    marker_color=COR[chave], hovertemplate=f"{NOME_PARTE[chave]}: %{{x:.1f}} pontos<extra></extra>")  # fmt: skip
    fig.update_layout(barmode="stack", xaxis=dict(range=[0, 100], title=None), showlegend=True)
    st.plotly_chart(layout_grafico(fig, 150), width="stretch", config={"displayModeBar": False})
    c1, c2, c3 = st.columns(3)
    c1.metric("Aderência ao ICP", f"{d.get('aderencia', 0):.0f}", f"peso {pesos.get('aderencia', 0):.0%}",
              delta_color="off", delta_arrow="off")  # fmt: skip
    c2.metric("Propensão de conversão", f"{d.get('propensao', 0):.0f}%", f"peso {pesos.get('propensao', 0):.0%}",
              delta_color="off", delta_arrow="off")  # fmt: skip
    c3.metric("Confiança da recomendação", f"{d.get('confianca', 0):.2f}", f"peso {pesos.get('confianca', 0):.0%}",
              delta_color="off", delta_arrow="off")  # fmt: skip
    local = d.get("aderencia_local") or {}
    if local.get("componentes"):
        comp = local["componentes"]
        st.caption(
            f"Referência local da aderência: {local['nota']} = texto {comp['texto']:.0f} + setor {comp['setor']:.0f} "
            f"+ porte {comp['porte']:.0f} (pesos 45, 30, 25; localização não entra)."
        )
    st.caption(d.get("explicacao_destino", ""))


def caminho_grafo(recomendacao: dict) -> None:
    caminhos = (recomendacao.get("caminho_grafo") or {}).get("caminhos", [])
    if not caminhos:
        st.caption("Sem caminho registrado no grafo.")
        return
    for c in caminhos[:3]:
        tipo = {"sinal_detectado": "info", "tipico_do_segmento": "", "perfil_kmeans": "alerta"}.get(c["tipo"], "")
        rotulo = {"sinal_detectado": "sinal do lead", "tipico_do_segmento": "típico do segmento",
                  "perfil_kmeans": "perfil K-Means"}.get(c["tipo"], c["tipo"])  # fmt: skip
        forca = f"força {c['forca']:.2f}"
        st.html(
            f'<div class="fg-cartao">{ui.selo_html(rotulo, tipo)} {ui.selo_html(forca)}'
            f'<p style="margin:8px 0 0 0">{html.escape(c["segmento"])} → <b>{html.escape(c["sinal"])}</b> → '
            f"{html.escape(c['solucao'])}</p>"
            f'<p style="color:var(--fg-texto-2);margin:4px 0 0 0">{html.escape(c["frase"])}</p></div>'
        )


def oferta(solucao_id: str | None, complementares: list[dict] | None = None, motivo: str = "") -> None:
    if not solucao_id:
        st.caption("Sem solução recomendada.")
        return
    sol = catalogo.por_id().get(solucao_id)
    if not sol:
        st.error(f"Solução fora do catálogo: {solucao_id}.")
        return
    comps = "".join(
        f"<li><b>{html.escape(catalogo.nome(c['solucao_id'] if 'solucao_id' in c else c['id']))}</b>: "
        f"{html.escape(c.get('motivo') or '')}</li>"
        for c in (complementares or [])
    )
    st.html(
        f'<div class="fg-cartao">{ui.selo_html(catalogo.linhas()[sol["linha"]], "destaque")}'
        f'<p style="margin:8px 0 2px 0"><b>{html.escape(sol["nome"])}</b></p>'
        f"<p>{html.escape(sol['o_que_resolve'])}</p>"
        + (f'<p style="color:var(--fg-texto-2)">Por que: {html.escape(motivo)}</p>' if motivo else "")
        + (f'<p class="fg-rotulo" style="margin-top:10px">Complementares</p><ul>{comps}</ul>' if comps else "")
        + "</div>"
    )


def roteiro(resultado: dict) -> None:
    """Rascunhos com botão de copiar (o ícone no canto do bloco). Nada é enviado pelo sistema."""
    r = resultado.get("roteiro", {})
    st.caption("Rascunhos para o BDR revisar. O Fullguete não envia nenhuma mensagem.")
    aba1, aba2, aba3, aba4 = st.tabs(["Ligação", "E-mail", "WhatsApp", "Objeções"])
    with aba1:
        st.code(r.get("ligacao", ""), language=None, wrap_lines=True)
    with aba2:
        st.code(f"Assunto: {r.get('email_assunto', '')}\n\n{r.get('email_corpo', '')}", language=None, wrap_lines=True)
    with aba3:
        st.code(r.get("whatsapp", ""), language=None, wrap_lines=True)
    with aba4:
        for o in resultado.get("objecoes", []):
            st.markdown(f"**{o['objecao']}**")
            st.code(o["resposta"], language=None, wrap_lines=True)


def dados_enriquecidos(lead: dict) -> None:
    real = json.loads(lead["dados_cnpjws"]) if lead.get("dados_cnpjws") else None
    simulados = json.loads(lead.get("sinais_simulados") or "{}")
    a, b = st.columns(2)
    with a:
        ui.rotulo("Dados reais (CNPJ.ws)")
        if real:
            for k, v in real.items():
                if v and k != "fonte":
                    st.caption(f"{k.replace('_', ' ').capitalize()}: {v}")
        elif lead.get("base_ficticia"):
            st.caption("Base fictícia: o CNPJ não é consultado na API.")
        else:
            st.caption("Sem consulta ao CNPJ.ws para este lead.")
    with b:
        st.html(f'<p class="fg-rotulo">Sinais de mercado {ui.selo_simulado()}</p>')
        itens = {k: v for k, v in simulados.items() if not k.startswith("_")}
        if not itens:
            st.caption("Nenhum sinal simulado.")
        for k, v in itens.items():
            valor = "sim" if v is True else "não" if v is False else f"{v:,}".replace(",", ".")
            st.caption(f"{k.replace('_', ' ').capitalize()}: {valor}")


def linha_etapas(etapas: list[dict]) -> None:
    """Linha de progresso dos agentes (por lote ou por lead)."""
    if not etapas:
        return
    cores = {"ok": "destaque", "alerta": "alerta", "bloqueado": "erro", "erro": "erro"}
    colunas = st.columns(len(etapas))
    for col, e in zip(colunas, etapas, strict=True):
        with col:
            if "total" in e:
                status = " ".join(ui.selo_html(f"{n} {s}", cores.get(s, "")) for s, n in e["status"].items())
                st.html(f'<div class="fg-cartao"><b>{html.escape(e["agente"])}</b><br>{status}'
                        f'<p style="color:var(--fg-texto-2);margin:6px 0 0 0">{e["ms"]:.0f} ms por lead</p></div>')  # fmt: skip
            else:
                from ia.agentes import NOME_AGENTE

                st.html(f'<div class="fg-cartao"><b>{html.escape(NOME_AGENTE.get(e["agente"], e["agente"]))}</b><br>'
                        f'{ui.selo_html(e["status"], cores.get(e["status"], ""))}</div>')  # fmt: skip


def detalhes_etapas(etapas: list[dict]) -> None:
    from ia.agentes import NOME_AGENTE

    for e in etapas:
        st.caption(f"{NOME_AGENTE.get(e['agente'], e['agente'])} · {e['status']} · {e.get('tempo_ms') or 0} ms")
        st.text(e["detalhe"] or "")


def quando(valor: str | None) -> str:
    return tempo.fmt(valor) if valor else ""
