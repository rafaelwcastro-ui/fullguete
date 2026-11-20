"""Pontuação local (sem IA): similaridade textual TF-IDF + regras de aderência.

Usada quando não há chave da Anthropic configurada ou se a API falhar.
"""
from __future__ import annotations

import unicodedata

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .models import PORTES, PerfilClienteIdeal

PESOS = {"texto": 40, "setor": 25, "porte": 20, "local": 15}


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _setor_bate(setor: str, alvos: list[str]) -> bool:
    s = _sem_acento(setor)
    return any(_sem_acento(a) in s or s in _sem_acento(a) for a in alvos if a.strip()) if s else False


def _porte_score(porte: str, alvos: list[str]) -> float:
    if porte in alvos:
        return 1.0
    if porte in PORTES and any(a in PORTES for a in alvos):
        dist = min(abs(PORTES.index(porte) - PORTES.index(a)) for a in alvos if a in PORTES)
        return 0.5 if dist == 1 else 0.0
    return 0.0


def pontuar(df: pd.DataFrame, icp: PerfilClienteIdeal) -> pd.DataFrame:
    textos_leads = (df["setor"] + " " + df["descricao"] + " " + df["empresa"]).map(_sem_acento)
    texto_icp = _sem_acento(f"{icp.descricao} {' '.join(icp.setores)}")

    if texto_icp.strip() and textos_leads.str.strip().any():
        vetorizador = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        matriz = vetorizador.fit_transform([texto_icp, *textos_leads])
        sim = cosine_similarity(matriz[0:1], matriz[1:]).ravel()
        # Reescala para 0–1 relativo ao melhor da base, mantendo a escala absoluta como teto.
        topo = sim.max() or 1.0
        sim = 0.5 * (sim / topo) + 0.5 * (sim / max(topo, 0.35))
    else:
        sim = [0.0] * len(df)

    ufs = {u.upper() for u in icp.ufs}
    cidades = {_sem_acento(c) for c in icp.cidades}
    notas, motivos = [], []
    for (_, lead), s in zip(df.iterrows(), sim):
        partes, razoes = {}, []
        partes["texto"] = min(float(s), 1.0)
        razoes.append(f"similaridade com o perfil {partes['texto']:.0%}")

        if icp.setores:
            ok = _setor_bate(lead["setor"], icp.setores)
            partes["setor"] = 1.0 if ok else 0.0
            razoes.append("setor aderente" if ok else f"setor fora do alvo ({lead['setor'] or 'não informado'})")
        else:
            partes["setor"] = 0.5

        if icp.portes:
            partes["porte"] = _porte_score(lead["porte"], icp.portes)
            if partes["porte"] == 1:
                razoes.append(f"porte {lead['porte']} no alvo")
            elif partes["porte"] > 0:
                razoes.append(f"porte {lead['porte']} próximo do alvo")
            else:
                razoes.append(f"porte fora do alvo ({lead['porte'] or 'não informado'})")
        else:
            partes["porte"] = 0.5

        if ufs or cidades:
            na_cidade = bool(cidades) and _sem_acento(lead["cidade"]) in cidades
            no_estado = bool(ufs) and lead["uf"] in ufs
            partes["local"] = 1.0 if (na_cidade or (no_estado and not cidades)) else 0.6 if no_estado else 0.0
            razoes.append("localização no alvo" if partes["local"] == 1 else
                          "mesmo estado" if partes["local"] > 0 else "fora da região-alvo")
        else:
            partes["local"] = 0.5

        nota = round(sum(PESOS[k] * v for k, v in partes.items()))
        notas.append(max(0, min(100, nota)))
        motivos.append("Análise local: " + "; ".join(razoes) + ".")

    out = df.copy()
    out["score"] = notas
    out["justificativa"] = motivos
    return out
