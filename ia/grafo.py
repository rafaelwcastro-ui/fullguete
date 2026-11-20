"""Knowledge graph: segmento de empresa -> sinal/dor -> solução Equifax -> linha de solução.

Montado a partir do catálogo e de catalogo/regras_grafo.json (editável pelo gestor).
Para cada lead, o grafo devolve as soluções candidatas e o caminho que justifica cada uma.
Os segmentos do K-Means entram como nós extras (perfil de cliente -> solução mais ganha no histórico).
"""

from __future__ import annotations

from functools import lru_cache

import networkx as nx

import catalogo

PESO_SINAL_FORA_DO_SEGMENTO = 0.55  # sinal achado no texto, mas que o segmento não costuma ter
PESO_SINAL_SO_DO_SEGMENTO = 0.30  # sinal típico do segmento, mas não achado no lead
BONUS_INTERESSE = 1.15
PESO_CLUSTER = 0.25


def _no(tipo: str, ident: str) -> str:
    return f"{tipo}:{ident}"


def construir(regras: dict | None = None, perfis_cluster: dict | None = None) -> nx.DiGraph:
    regras = regras or catalogo.carregar_regras()
    g = nx.DiGraph()
    for linha_id, nome in catalogo.linhas().items():
        g.add_node(_no("linha", linha_id), tipo="linha", nome=nome)
    for sol in catalogo.solucoes():
        g.add_node(_no("sol", sol["id"]), tipo="solucao", nome=sol["nome"], linha=sol["linha"])
        g.add_edge(_no("sol", sol["id"]), _no("linha", sol["linha"]), peso=1.0, frase="pertence à linha")
    for seg in regras["segmentos"]:
        g.add_node(_no("seg", seg["id"]), tipo="segmento", nome=seg["nome"])
    for sinal in regras["sinais"]:
        g.add_node(_no("sinal", sinal["id"]), tipo="sinal", nome=sinal["nome"], dor=sinal["dor"])
    for a in regras["segmento_sinal"]:
        g.add_edge(_no("seg", a["de"]), _no("sinal", a["para"]), peso=float(a["peso"]),
                   frase="costuma ter este sinal")  # fmt: skip
    nomes_sol = catalogo.por_id()
    sinais = {s["id"]: s for s in regras["sinais"]}
    for a in regras["sinal_solucao"]:
        if a["para"] not in nomes_sol:
            continue
        sinal = sinais[a["de"]]
        frase = f"{sinal['nome'].lower()} → {sinal['dor']} → {nomes_sol[a['para']]['nome']}"
        g.add_edge(_no("sinal", a["de"]), _no("sol", a["para"]), peso=float(a["peso"]), frase=frase)
    for cluster, perfil in (perfis_cluster or {}).items():
        no = _no("cluster", str(cluster))
        g.add_node(no, tipo="cluster", nome=perfil.get("nome", f"Perfil {cluster}"))
        for sol_id, share in perfil.get("solucoes_ganhas", {}).items():
            if sol_id in nomes_sol:
                g.add_edge(no, _no("sol", sol_id), peso=float(share),
                           frase=f"{perfil.get('nome', 'perfil')} → ganhos no histórico → {nomes_sol[sol_id]['nome']}")  # fmt: skip
    return g


@lru_cache(maxsize=4)
def _grafo_cache(chave: str) -> nx.DiGraph:  # chave muda quando as regras mudam
    import json

    return construir(json.loads(chave))


def grafo_atual(perfis_cluster: dict | None = None) -> nx.DiGraph:
    import json

    if perfis_cluster:
        return construir(catalogo.carregar_regras(), perfis_cluster)
    return _grafo_cache(json.dumps(catalogo.carregar_regras(), sort_keys=True))


def candidatas(
    segmento: str,
    sinais: list[str],
    interesse: str | None = None,
    cluster: int | None = None,
    k: int = 5,
    g: nx.DiGraph | None = None,
) -> list[dict]:
    """Soluções candidatas para o lead, com pontuação de 0 a 1 e os caminhos que levaram a cada uma."""
    g = g or grafo_atual()
    regras = catalogo.carregar_regras()
    linha_interesse = regras.get("interesse_linha", {}).get(interesse or "")
    no_seg = _no("seg", segmento)
    pesos_seg = {v.split(":", 1)[1]: d["peso"] for _, v, d in g.out_edges(no_seg, data=True)} if no_seg in g else {}

    caminhos: dict[str, list[dict]] = {}

    def adicionar(sol: str, forca: float, caminho: dict) -> None:
        caminhos.setdefault(sol, []).append({**caminho, "forca": round(forca, 3)})

    # 1. Sinais achados no lead.
    for sinal in sinais:
        no_sinal = _no("sinal", sinal)
        if no_sinal not in g:
            continue
        w_seg = pesos_seg.get(sinal, PESO_SINAL_FORA_DO_SEGMENTO)
        for _, no_sol, d in g.out_edges(no_sinal, data=True):
            adicionar(no_sol.split(":", 1)[1], w_seg * d["peso"], {
                "tipo": "sinal_detectado", "segmento": g.nodes[no_seg]["nome"] if no_seg in g else "Outros",
                "sinal": g.nodes[no_sinal]["nome"], "solucao": g.nodes[no_sol]["nome"], "frase": d["frase"],
            })  # fmt: skip
    # 2. Sinais típicos do segmento que não apareceram no lead (peso menor).
    for sinal, w_seg in pesos_seg.items():
        if sinal in sinais:
            continue
        no_sinal = _no("sinal", sinal)
        for _, no_sol, d in g.out_edges(no_sinal, data=True):
            adicionar(no_sol.split(":", 1)[1], PESO_SINAL_SO_DO_SEGMENTO * w_seg * d["peso"], {
                "tipo": "tipico_do_segmento", "segmento": g.nodes[no_seg]["nome"],
                "sinal": g.nodes[no_sinal]["nome"], "solucao": g.nodes[no_sol]["nome"],
                "frase": f"empresas de {g.nodes[no_seg]['nome'].lower()} costumam ter: {d['frase']}",
            })  # fmt: skip
    # 3. Perfil do K-Means.
    no_cluster = _no("cluster", str(cluster)) if cluster is not None else None
    if no_cluster and no_cluster in g:
        for _, no_sol, d in g.out_edges(no_cluster, data=True):
            adicionar(no_sol.split(":", 1)[1], PESO_CLUSTER * d["peso"], {
                "tipo": "perfil_kmeans", "segmento": g.nodes[no_cluster]["nome"], "sinal": "ganhos no histórico",
                "solucao": g.nodes[no_sol]["nome"], "frase": d["frase"],
            })  # fmt: skip

    ranking = []
    por_id = catalogo.por_id()
    for sol, lista in caminhos.items():
        lista.sort(key=lambda c: c["forca"], reverse=True)
        pontos = lista[0]["forca"] + 0.15 * sum(c["forca"] for c in lista[1:4])
        if linha_interesse and por_id[sol]["linha"] == linha_interesse:
            pontos *= BONUS_INTERESSE
        ranking.append({"solucao_id": sol, "pontos": round(min(pontos, 1.0), 3), "caminhos": lista[:3]})
    ranking.sort(key=lambda r: (-r["pontos"], r["solucao_id"]))
    return ranking[:k]


def subgrafo(candidatas_lead: list[dict]) -> dict:
    """Nós e arestas usados na recomendação, para guardar e desenhar na ficha."""
    nos, arestas = set(), []
    for cand in candidatas_lead:
        for c in cand["caminhos"]:
            nos.update({("segmento", c["segmento"]), ("sinal", c["sinal"]), ("solucao", c["solucao"])})
            arestas.append({"de": c["segmento"], "para": c["sinal"], "tipo": c["tipo"]})
            arestas.append({"de": c["sinal"], "para": c["solucao"], "forca": c["forca"]})
    return {"nos": [{"tipo": t, "nome": n} for t, n in sorted(nos)], "arestas": arestas}
