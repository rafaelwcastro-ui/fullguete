"""Filtro de campanhas: mantém o escopo de acesso já aplicado à tela."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from banco import prospeccao


def aplicar(df: pd.DataFrame, coluna: str, chave: str) -> pd.DataFrame:
    """Permite navegar por tag sem expor leads fora do dataframe autorizado."""
    df = prospeccao.com_tags(df, coluna)
    if df.empty:
        return df
    autorizados = {int(i) for i in df[coluna].tolist()}
    disponiveis = [
        b for b in prospeccao.listar()
        if autorizados.intersection(prospeccao.ids_leads(b["id"]))
    ]
    if not disponiveis:
        st.caption("Nenhuma campanha vinculada aos leads deste painel.")
        return df
    rotulos = {None: "Todas as campanhas"}
    rotulos.update({b["id"]: b["tag"] for b in disponiveis})
    selecionada = st.selectbox(
        "Campanha / tag de origem", list(rotulos),
        format_func=rotulos.get, key=chave,
    )
    if selecionada is not None:
        return prospeccao.filtrar_dataframe(df, selecionada, coluna)
    return df
