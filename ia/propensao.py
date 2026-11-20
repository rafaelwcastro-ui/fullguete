"""Propensão de conversão (aprendizado supervisionado).

Compara regressão logística e árvore de decisão no histórico de leads ganhos e perdidos,
registra as duas, ativa a de maior AUC e expõe as variáveis que mais pesam.
O histórico começa sintético (base fictícia) e cresce com os resultados reais do funil.
"""

from __future__ import annotations

import json
import threading

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

import catalogo
from banco import repositorio
from banco.conexao import conectar
from dados.features import FEATURES_CATEGORICAS, FEATURES_NUMERICAS
from dados.ingestao import ORIGENS_ROTULO
from nucleo import config, tempo

NOME = "propensao"
SEMENTE = 42
_trava = threading.Lock()
_cache: dict[str, Pipeline] = {}

ROTULOS = {
    "porte_ordem": "Porte",
    "log_funcionarios": "Funcionários",
    "n_sinais": "Quantidade de sinais",
    "forca_segmento": "Força do sinal no segmento",
    "interesse_declarado": "Declarou interesse",
    "interesse_alinhado": "Interesse alinhado à solução",
    "empresa_ativa": "Empresa ativa",
    "tem_site": "Tem site",
}


def rotulo_variavel(nome: str) -> str:
    if nome in ROTULOS:
        return ROTULOS[nome]
    for prefixo, mapa in (("segmento_", None), ("origem_", ORIGENS_ROTULO)):
        if nome.startswith(prefixo):
            valor = nome[len(prefixo) :]
            if mapa is None:
                segs = {s["id"]: s["nome"] for s in catalogo.carregar_regras()["segmentos"]}
                return f"Segmento: {segs.get(valor, valor)}"
            return f"Origem: {mapa.get(valor, valor)}"
    return nome


def carregar_rotulos() -> pd.DataFrame:
    with conectar() as con:
        linhas = con.execute("SELECT features, resultado, fonte FROM rotulos_treino").fetchall()
    registros = [{**json.loads(r["features"]), "resultado": r["resultado"], "fonte": r["fonte"]} for r in linhas]
    return pd.DataFrame(registros)


def _pipeline(algoritmo: str) -> Pipeline:
    prep = ColumnTransformer([
        ("num", StandardScaler(), FEATURES_NUMERICAS),
        ("cat", OneHotEncoder(handle_unknown="ignore"), FEATURES_CATEGORICAS),
    ])  # fmt: skip
    if algoritmo == "regressao_logistica":
        estimador = LogisticRegression(max_iter=1000, C=1.0, class_weight="balanced")
    else:
        estimador = DecisionTreeClassifier(max_depth=4, min_samples_leaf=15, class_weight="balanced",
                                           random_state=SEMENTE)  # fmt: skip
    return Pipeline([("prep", prep), ("modelo", estimador)])


def _importancias(pipe: Pipeline) -> list[dict]:
    nomes = [n.split("__", 1)[1] for n in pipe.named_steps["prep"].get_feature_names_out()]
    modelo = pipe.named_steps["modelo"]
    if hasattr(modelo, "coef_"):
        valores = modelo.coef_[0]
        itens = [{"variavel": rotulo_variavel(n), "peso": float(v), "efeito": "aumenta" if v > 0 else "reduz"}
                 for n, v in zip(nomes, valores, strict=True)]  # fmt: skip
    else:
        itens = [{"variavel": rotulo_variavel(n), "peso": float(v), "efeito": "importância"}
                 for n, v in zip(nomes, modelo.feature_importances_, strict=True)]  # fmt: skip
    itens.sort(key=lambda i: abs(i["peso"]), reverse=True)
    return itens[:12]


def _metricas(pipe: Pipeline, x_teste: pd.DataFrame, y_teste: pd.Series) -> dict:
    proba = pipe.predict_proba(x_teste)[:, 1]
    pred = (proba >= 0.5).astype(int)
    return {
        "auc": round(float(roc_auc_score(y_teste, proba)), 4),
        "precisao": round(float(precision_score(y_teste, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_teste, pred, zero_division=0)), 4),
        "acuracia": round(float(accuracy_score(y_teste, pred)), 4),
        "matriz_confusao": confusion_matrix(y_teste, pred, labels=[0, 1]).tolist(),
    }


def treinar(ator: str = "sistema") -> dict:
    """Treina as duas abordagens, registra as duas versões e ativa a melhor. Retorna o resumo."""
    with _trava:
        dados = carregar_rotulos()
        if len(dados) < 40 or dados["resultado"].nunique() < 2:
            raise ValueError("Histórico insuficiente para treinar: são precisos ganhos e perdas.")
        x, y = dados[FEATURES_NUMERICAS + FEATURES_CATEGORICAS], dados["resultado"].astype(int)
        x_treino, x_teste, y_treino, y_teste = train_test_split(x, y, test_size=0.25, stratify=y,
                                                                random_state=SEMENTE)  # fmt: skip
        with conectar() as con:
            n = con.execute(
                "SELECT COUNT(*) FROM modelos_registro WHERE nome=? AND algoritmo='regressao_logistica'", (NOME,)
            ).fetchone()[0]
        versao = f"v{n + 1}"
        resultados = {}
        for algoritmo in ("regressao_logistica", "arvore_decisao"):
            pipe = _pipeline(algoritmo).fit(x_treino, y_treino)
            resultados[algoritmo] = {
                "pipe": pipe,
                "metricas": _metricas(pipe, x_teste, y_teste),
                "importancias": _importancias(pipe),
            }
        vencedor = max(resultados, key=lambda a: resultados[a]["metricas"]["auc"])
        momento = tempo.iso()
        fontes = dados["fonte"].value_counts().to_dict()
        with conectar() as con:
            con.execute("UPDATE modelos_registro SET ativo=0 WHERE nome=?", (NOME,))
            for algoritmo, r in resultados.items():
                caminho = config.pasta_modelos() / f"{NOME}_{config.sufixo_banco()}_{versao}_{algoritmo}.joblib"
                joblib.dump(r["pipe"], caminho)
                metricas = {**r["metricas"], "importancias": r["importancias"], "fontes": fontes,
                            "taxa_ganho": round(float(y.mean()), 4)}  # fmt: skip
                con.execute(
                    """INSERT INTO modelos_registro (nome, versao, algoritmo, treinado_em, metricas, variaveis, n_treino,
                           n_teste, caminho, ativo) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (NOME, f"{versao}-{algoritmo}", algoritmo, momento, json.dumps(metricas, ensure_ascii=False),
                     json.dumps(FEATURES_NUMERICAS + FEATURES_CATEGORICAS), len(x_treino), len(x_teste),
                     caminho.name, int(algoritmo == vencedor)),
                )  # fmt: skip
            repositorio.auditar(con, ator, "modelo_treinado", "modelos_registro", versao,
                                {"vencedor": vencedor, "auc": resultados[vencedor]["metricas"]["auc"],
                                 "linhas": len(dados)})  # fmt: skip
        resumo = {
            "versao": f"{versao}-{vencedor}",
            "vencedor": vencedor,
            "linhas": len(dados),
            "fontes": fontes,
            "comparacao": {a: r["metricas"] for a, r in resultados.items()},
        }
        (config.pasta_modelos() / "metricas.json").write_text(
            json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _cache.clear()
        return resumo


def registro_ativo() -> dict | None:
    with conectar() as con:
        linha = con.execute(
            "SELECT * FROM modelos_registro WHERE nome=? AND ativo=1 ORDER BY id DESC LIMIT 1", (NOME,)
        ).fetchone()
    if not linha:
        return None
    r = dict(linha)
    r["metricas"] = json.loads(r["metricas"])
    return r


def _modelo_ativo() -> tuple[Pipeline, str]:
    registro = registro_ativo()
    if registro is None or not (config.pasta_modelos() / registro["caminho"]).exists():
        treinar("sistema")
        registro = registro_ativo()
    versao = registro["versao"]
    if versao not in _cache:
        _cache.clear()
        _cache[versao] = joblib.load(config.pasta_modelos() / registro["caminho"])
    return _cache[versao], versao


def prever(lista_features: list[dict]) -> tuple[list[float], str]:
    """Probabilidade de ganho (0 a 1) para cada lead e a versão do modelo usada."""
    if not lista_features:
        return [], ""
    modelo, versao = _modelo_ativo()
    x = pd.DataFrame(lista_features)[FEATURES_NUMERICAS + FEATURES_CATEGORICAS]
    return [float(p) for p in modelo.predict_proba(x)[:, 1]], versao


def historico_versoes() -> list[dict]:
    with conectar() as con:
        linhas = con.execute(
            "SELECT versao, algoritmo, treinado_em, metricas, n_treino, n_teste, ativo FROM modelos_registro "
            "WHERE nome=? ORDER BY id DESC", (NOME,)
        ).fetchall()  # fmt: skip
    return [{**dict(r), "metricas": json.loads(r["metricas"])} for r in linhas]
