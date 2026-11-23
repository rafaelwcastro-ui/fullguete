"""Dados e filtros seguros para as páginas Carteira e CRM.

As tabelas de leads combinam empresas novas sem recomendação, dados fictícios e
cadastros incompletos. Campos opcionais podem vir como None ou NaN.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

import pandas as pd

import catalogo


def texto_valido(valor: object) -> str:
    """Evita que NaN, None e objetos inesperados quebrem menus e cartões."""
    if not isinstance(valor, str):
        return ""
    return valor.strip()


def nome_solucao(identificador: object) -> str:
    chave = texto_valido(identificador)
    if not chave:
        return ""
    encontrado = catalogo.nome(chave)
    return texto_valido(encontrado) or chave


def opcoes_solucoes(valores: Iterable[object]) -> list[str]:
    return sorted({v for valor in valores if (v := texto_valido(valor))}, key=lambda s: (s.casefold(), s))


def valor_seguro(valor: object) -> float:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return numero if math.isfinite(numero) and numero >= 0 else 0.0


def filtrar_crm(
    df: pd.DataFrame,
    termo: str = "",
    etapas: list[str] | None = None,
    responsavel: str = "",
    somente_reais: bool = False,
) -> pd.DataFrame:
    """Filtra o universo autorizado antes de montar o Kanban ou abrir fichas."""
    if df.empty:
        return df.copy()
    saida = df.copy()
    if termo.strip():
        termo_limpo = termo.strip().casefold()
        nome = saida["empresa"].fillna("").astype(str).str.casefold()
        razao = saida["razao_social"].fillna("").astype(str).str.casefold()
        cnpj = saida["cnpj"].fillna("").astype(str)
        saida = saida[
            nome.str.contains(termo_limpo, regex=False)
            | razao.str.contains(termo_limpo, regex=False)
            | cnpj.str.contains(termo_limpo, regex=False)
        ]
    if etapas:
        saida = saida[saida["etapa"].isin(etapas)]
    if responsavel:
        saida = saida[saida["responsavel"].fillna("") == responsavel]
    if somente_reais:
        saida = saida[saida["base_ficticia"] == 0]
    return saida.copy()


def resumo_crm(df: pd.DataFrame) -> dict:
    """KPIs a partir dos mesmos leads exibidos no Kanban, sem dados duplicados."""
    if df.empty:
        return {"leads": 0, "reais": 0, "ficticios": 0, "valor_mensal": 0.0}
    return {
        "leads": len(df),
        "reais": int((df["base_ficticia"] == 0).sum()),
        "ficticios": int((df["base_ficticia"] == 1).sum()),
        "valor_mensal": sum(valor_seguro(v) for v in df["valor"]),
    }
