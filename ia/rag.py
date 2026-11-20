"""RAG: recupera do catálogo só o que é relevante antes de chamar o LLM.

- Para o tratamento do lead, a recuperação é feita pelo grafo (ia/grafo.py): só as candidatas vão ao LLM.
- Para o Assistente, a recuperação é textual (TF-IDF sobre o catálogo).
"""

from __future__ import annotations

from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

import catalogo
from dados.features import normalizar


def documento(sol: dict, nome_sinal: dict[str, str] | None = None) -> str:
    nome_sinal = nome_sinal or {}
    sinais = ", ".join(nome_sinal.get(s, s) for s in sol["sinais"])
    return (
        f"{sol['nome']}. {sol['o_que_resolve']} Perfil típico: {sol['perfil_tipico']} Sinais: {sinais}. "
        f"Linha: {catalogo.linhas()[sol['linha']]}."
    )


def contexto_candidatas(candidatas: list[dict]) -> list[dict]:
    """Ficha curta de cada candidata, no formato enviado ao LLM."""
    por_id = catalogo.por_id()
    saida = []
    for cand in candidatas:
        sol = por_id[cand["solucao_id"]]
        saida.append({
            "id": sol["id"],
            "nome": sol["nome"],
            "linha": catalogo.linhas()[sol["linha"]],
            "o_que_resolve": sol["o_que_resolve"],
            "perfil_tipico": sol["perfil_tipico"],
            "perguntas_sugeridas": sol["perguntas_descoberta"],
            "por_que_e_candidata": [c["frase"] for c in cand["caminhos"][:2]],
            "aderencia_no_grafo": cand["pontos"],
        })  # fmt: skip
    return saida


@lru_cache(maxsize=1)
def _indice():
    regras = catalogo.carregar_regras()
    nome_sinal = {s["id"]: f"{s['nome']} ({s['dor']})" for s in regras["sinais"]}
    sols = catalogo.solucoes()
    textos = [normalizar(documento(s, nome_sinal)) for s in sols]
    vetorizador = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
    matriz = vetorizador.fit_transform(textos)
    return vetorizador, matriz, sols


def buscar(pergunta: str, k: int = 4) -> list[tuple[dict, float]]:
    """Soluções do catálogo mais parecidas com a pergunta."""
    vetorizador, matriz, sols = _indice()
    sims = cosine_similarity(vetorizador.transform([normalizar(pergunta)]), matriz).ravel()
    ordem = sims.argsort()[::-1][:k]
    return [(sols[i], float(sims[i])) for i in ordem if sims[i] > 0]
