"""Regras do Agente Supervisor (sem LLM): nota final, classificação e destino.

Nota final = peso_aderencia × aderência + peso_propensao × propensão + peso_confianca × (confiança × 100).
Pesos e limites vêm de Governança & LGPD e ficam com histórico de alteração.
"""

from __future__ import annotations

from nucleo import estados

PESOS_PADRAO = {"aderencia": 0.5, "propensao": 0.3, "confianca": 0.2}
LIMITES_PADRAO = {"quente": 80, "morno": 60, "frio": 40}
CLASSES = ["Quente", "Morno", "Frio", "Descartar"]


def combinar(aderencia: float, propensao: float, confianca: float, pesos: dict | None = None) -> tuple[float, dict]:
    """aderencia e propensao em 0 a 100; confianca em 0 a 1. Devolve a nota e quanto veio de cada parte."""
    pesos = pesos or PESOS_PADRAO
    total_pesos = sum(pesos.values()) or 1.0
    partes = {
        "aderencia": pesos["aderencia"] / total_pesos * aderencia,
        "propensao": pesos["propensao"] / total_pesos * propensao,
        "confianca": pesos["confianca"] / total_pesos * confianca * 100,
    }
    partes = {k: round(v, 1) for k, v in partes.items()}
    return round(sum(partes.values()), 1), partes


def classificar(nota: float, limites: dict | None = None) -> str:
    limites = limites or LIMITES_PADRAO
    if nota >= limites["quente"]:
        return "Quente"
    if nota >= limites["morno"]:
        return "Morno"
    if nota >= limites["frio"]:
        return "Frio"
    return "Descartar"


def destino(classificacao: str, confianca: float, confianca_minima: float = 0.6,
            precisa_revisao: bool = False, nota: float | None = None) -> tuple[str, str | None, str]:  # fmt: skip
    """Devolve (etapa, motivo da lista ou None, explicação curta)."""
    if classificacao == "Descartar":
        nota_txt = f" ({nota:.0f})" if nota is not None else ""
        return estados.DESCARTADO, "Sem fit", f"Nota final{nota_txt} abaixo do mínimo para trabalhar."
    if precisa_revisao:
        return estados.REVISAO, None, "A IA ou o agente de risco pediu revisão humana."
    if classificacao in ("Quente", "Morno"):
        if confianca >= confianca_minima:
            return estados.FILA_BDR, None, f"{classificacao} com confiança {confianca:.2f}: vai para o BDR."
        return estados.REVISAO, None, f"{classificacao} com confiança baixa ({confianca:.2f}): revisão humana."
    return estados.NUTRICAO, None, "Frio: entra em nutrição até mostrar mais sinais."
