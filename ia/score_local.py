"""Aderência ao ICP sem LLM: TF-IDF + regras.

Pesos sem localização: similaridade textual 45, setor 30, porte 25.
É o motor do modo sem chave e o plano B quando o LLM falha.
"""

from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import catalogo
from dados.features import PORTES, normalizar, texto_empresa

from . import rag

PESOS = {"texto": 45, "setor": 30, "porte": 25}
SIMILARIDADE_TETO = 0.35  # similaridade de cosseno considerada "muito parecida"


def _setor(lead: dict, segmento_nome: str, alvos: list[str]) -> tuple[float, str]:
    if not alvos:
        return 0.5, "ICP sem setor definido"
    texto = normalizar(f"{segmento_nome} {lead.get('setor', '')} {lead.get('descricao', '')}")
    seg = normalizar(segmento_nome)
    for alvo in alvos:
        a = normalizar(alvo)
        if a and (f" {a} " in f" {texto} " or (seg and a == seg)):
            return 1.0, f"setor no alvo ({alvo})"
    for alvo in alvos:
        a = normalizar(alvo)
        if seg and seg in a:
            return 0.5, f"setor próximo do alvo ({alvo})"
    return 0.0, f"setor fora do alvo ({segmento_nome or 'não identificado'})"


def _porte(porte: str, alvos: list[str]) -> tuple[float, str]:
    if not alvos:
        return 0.5, "ICP sem porte definido"
    if porte in alvos:
        return 1.0, f"porte {porte} no alvo"
    if porte in PORTES and any(a in PORTES for a in alvos):
        dist = min(abs(PORTES.index(porte) - PORTES.index(a)) for a in alvos if a in PORTES)
        if dist == 1:
            return 0.5, f"porte {porte} próximo do alvo"
    return 0.0, f"porte fora do alvo ({porte or 'não informado'})"


def aderencia(leads: list[dict], icp: dict) -> list[dict]:
    """Nota de 0 a 100 para cada lead, com a parte de cada critério e as razões."""
    if not leads:
        return []
    regras = catalogo.carregar_regras()
    nome_seg = {s["id"]: s["nome"] for s in regras["segmentos"]}
    texto_icp = normalizar(f"{icp.get('descricao', '')} {' '.join(icp.get('palavras_chave', []))} "
                           f"{' '.join(icp.get('setores', []))}")  # fmt: skip
    textos = [normalizar(texto_empresa(lead)) for lead in leads]
    corpus = [texto_icp, *textos, *(normalizar(rag.documento(s)) for s in catalogo.solucoes())]
    vetorizador = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True).fit(corpus)
    sims = cosine_similarity(vetorizador.transform([texto_icp]), vetorizador.transform(textos)).ravel()
    palavras = {normalizar(p): p for p in icp.get("palavras_chave", []) if p.strip()}

    saida = []
    for lead, texto, sim in zip(leads, textos, sims, strict=True):
        achadas = [original for p, original in palavras.items() if f" {p} " in f" {texto} "]
        parte_texto = 0.5 * min(float(sim) / SIMILARIDADE_TETO, 1.0) + 0.5 * min(len(achadas) / 3, 1.0)
        segmento_nome = nome_seg.get(lead.get("segmento", ""), "")
        parte_setor, razao_setor = _setor(lead, segmento_nome, icp.get("setores", []))
        parte_porte, razao_porte = _porte(lead.get("porte") or "", icp.get("portes", []))
        componentes = {
            "texto": round(PESOS["texto"] * parte_texto, 1),
            "setor": round(PESOS["setor"] * parte_setor, 1),
            "porte": round(PESOS["porte"] * parte_porte, 1),
        }
        razao_texto = f"descrição {parte_texto:.0%} parecida com o ICP"
        if achadas:
            razao_texto += f" (palavras: {', '.join(achadas[:3])})"
        saida.append({
            "nota": int(round(sum(componentes.values()))),
            "componentes": componentes,
            "razoes": [razao_texto, razao_setor, razao_porte],
        })  # fmt: skip
    return saida
