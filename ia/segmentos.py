"""Segmentação de leads com K-Means (aprendizado não supervisionado).

Agrupa os leads em perfis de cliente com base nas variáveis numéricas. Cada perfil ganha um nome
legível e a lista das soluções mais vendidas a ele no histórico; esse perfil vira um nó do grafo.
"""

from __future__ import annotations

import json
import threading
from collections import Counter

import joblib
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import catalogo
from banco import repositorio
from banco.conexao import conectar
from dados.features import FEATURES_NUMERICAS, PORTES
from nucleo import config, tempo

NOME = "segmentos"
K = 4
SEMENTE = 7
_trava = threading.Lock()
_cache: dict[str, tuple[Pipeline, dict]] = {}


def _dados() -> pd.DataFrame:
    with conectar() as con:
        historico = con.execute("SELECT features, resultado, solucao_id FROM rotulos_treino").fetchall()
    return pd.DataFrame([
        {**json.loads(r["features"]), "resultado": r["resultado"], "solucao_id": r["solucao_id"]} for r in historico
    ])  # fmt: skip


def _nomear(grupo: pd.DataFrame) -> str:
    segs = {s["id"]: s["nome"] for s in catalogo.carregar_regras()["segmentos"]}
    principais = [segs.get(s, s) for s, _ in Counter(grupo["segmento"]).most_common(2)]
    porte = PORTES[int(round(grupo["porte_ordem"].mean()))]
    sinais = grupo["n_sinais"].mean()
    intensidade = "muitos sinais" if sinais >= 2.2 else "sinais moderados" if sinais >= 1.2 else "poucos sinais"
    return f"{' e '.join(principais)}, porte {porte}, {intensidade}"


def treinar(ator: str = "sistema") -> dict:
    with _trava:
        dados = _dados()
        if len(dados) < K * 5:
            raise ValueError("Poucos dados para segmentar.")
        pipe = Pipeline(
            [("escala", StandardScaler()), ("kmeans", KMeans(n_clusters=K, n_init=10, random_state=SEMENTE))]
        )
        rotulos = pipe.fit_predict(dados[FEATURES_NUMERICAS])
        silhueta = float(silhouette_score(pipe.named_steps["escala"].transform(dados[FEATURES_NUMERICAS]), rotulos))
        dados["cluster"] = rotulos
        perfis = {}
        for cluster, grupo in dados.groupby("cluster"):
            ganhos = grupo[grupo["resultado"] == 1]
            contagem = Counter(ganhos["solucao_id"].dropna())
            total = sum(contagem.values()) or 1
            perfis[int(cluster)] = {
                "nome": f"Perfil {int(cluster) + 1}: {_nomear(grupo)}",
                "tamanho": int(len(grupo)),
                "taxa_ganho": round(float(grupo["resultado"].mean()), 3),
                "solucoes_ganhas": {s: round(n / total, 3) for s, n in contagem.most_common(3)},
                "medias": {c: round(float(grupo[c].mean()), 3) for c in FEATURES_NUMERICAS},
            }
        with conectar() as con:
            n = con.execute("SELECT COUNT(*) FROM modelos_registro WHERE nome=?", (NOME,)).fetchone()[0]
            versao = f"v{n + 1}"
            caminho = config.pasta_modelos() / f"{NOME}_{config.sufixo_banco()}_{versao}.joblib"
            joblib.dump({"pipe": pipe, "perfis": perfis}, caminho)
            con.execute("UPDATE modelos_registro SET ativo=0 WHERE nome=?", (NOME,))
            con.execute(
                """INSERT INTO modelos_registro (nome, versao, algoritmo, treinado_em, metricas, variaveis, n_treino,
                       n_teste, caminho, ativo) VALUES (?,?,?,?,?,?,?,?,?,1)""",
                (NOME, versao, "kmeans", tempo.iso(),
                 json.dumps({"silhueta": round(silhueta, 4), "k": K, "perfis": perfis}, ensure_ascii=False),
                 json.dumps(FEATURES_NUMERICAS), len(dados), 0, caminho.name),
            )  # fmt: skip
            repositorio.auditar(con, ator, "segmentos_treinados", "modelos_registro", versao, {"silhueta": silhueta})
        _cache.clear()
        return {"versao": versao, "silhueta": silhueta, "perfis": perfis}


def _ativo() -> tuple[Pipeline, dict, str]:
    with conectar() as con:
        linha = con.execute(
            "SELECT versao, caminho FROM modelos_registro WHERE nome=? AND ativo=1 ORDER BY id DESC LIMIT 1", (NOME,)
        ).fetchone()
    if linha is None or not (config.pasta_modelos() / linha["caminho"]).exists():
        treinar()
        return _ativo()
    if linha["versao"] not in _cache:
        _cache.clear()
        salvo = joblib.load(config.pasta_modelos() / linha["caminho"])
        _cache[linha["versao"]] = (salvo["pipe"], salvo["perfis"])
    pipe, perfis = _cache[linha["versao"]]
    return pipe, perfis, linha["versao"]


def perfis() -> dict:
    return _ativo()[1]


def prever(lista_features: list[dict]) -> list[int]:
    if not lista_features:
        return []
    pipe, _, _ = _ativo()
    return [int(c) for c in pipe.predict(pd.DataFrame(lista_features)[FEATURES_NUMERICAS])]
