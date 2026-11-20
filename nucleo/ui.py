"""Componentes visuais reaproveitados pelas páginas."""

from __future__ import annotations

import html

import streamlit as st

from .config import RAIZ

RODAPE = "Projeto acadêmico FGV. Sem vínculo com a Equifax. Dados fictícios e integrações simuladas quando indicado."

# Classificação sempre com cor e texto, nunca só cor.
TIPO_CLASSIFICACAO = {"Quente": "destaque", "Morno": "alerta", "Frio": "info", "Descartar": ""}


def aplicar_css() -> None:
    css = (RAIZ / "estilo" / "tema.css").read_text(encoding="utf-8")
    st.html(f"<style>{css}</style>")


def cabecalho(titulo: str, subtitulo: str = "", secao: str = "") -> None:
    if secao:
        st.html(f'<p class="fg-rotulo">{html.escape(secao)}</p>')
    st.title(titulo)
    if subtitulo:
        st.html(f'<p class="fg-subtitulo">{html.escape(subtitulo)}</p>')


def rotulo(texto: str) -> None:
    st.html(f'<p class="fg-rotulo">{html.escape(texto)}</p>')


def selo_html(texto: str, tipo: str = "") -> str:
    return f'<span class="fg-selo {tipo}">{html.escape(texto)}</span>'


def selo(texto: str, tipo: str = "") -> None:
    st.html(selo_html(texto, tipo))


def selo_classificacao(classificacao: str) -> str:
    return selo_html(classificacao, TIPO_CLASSIFICACAO.get(classificacao, ""))


def selo_simulado(texto: str = "Simulado") -> str:
    return selo_html(texto, "alerta")


def cartao(conteudo_html: str) -> None:
    st.html(f'<div class="fg-cartao">{conteudo_html}</div>')


def em_construcao(fase: int, itens: list[str]) -> None:
    lista = "".join(f"<li>{html.escape(i)}</li>" for i in itens)
    cartao(
        f"{selo_html(f'Chega na fase {fase}', 'info')}"
        f'<p style="margin:10px 0 4px 0">O que esta página vai ter:</p><ul style="margin:0">{lista}</ul>'
    )


def rodape() -> None:
    st.html(f'<div class="fg-rodape">{html.escape(RODAPE)}</div>')
