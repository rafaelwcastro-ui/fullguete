"""Drift: compara a distribuição recente com a de referência usando PSI (Population Stability Index).

PSI = soma de (atual − referência) × ln(atual / referência) por faixa. Leitura usual:
abaixo de 0,1 estável; de 0,1 a 0,2 atenção; acima do limite configurado (padrão 0,2) alerta.
"""

from __future__ import annotations

import json

import numpy as np

from banco import repositorio
from banco.conexao import conectar
from nucleo import tempo

ROTULOS = {"n_sinais": "Quantidade de sinais", "porte_ordem": "Porte", "forca_segmento": "Força do sinal no segmento",
           "log_funcionarios": "Funcionários", "interesse_alinhado": "Interesse alinhado"}  # fmt: skip
VARIAVEIS = ["n_sinais", "porte_ordem", "forca_segmento", "log_funcionarios", "interesse_alinhado"]


def psi(referencia: list[float], atual: list[float], faixas: int = 10) -> float:
    ref, cur = np.asarray(referencia, dtype=float), np.asarray(atual, dtype=float)
    if len(ref) < 5 or len(cur) < 5:
        return 0.0
    faixas = min(faixas, max(3, min(len(ref), len(cur)) // 10))  # amostra pequena pede menos faixas
    cortes = np.unique(np.quantile(ref, np.linspace(0, 1, faixas + 1)))
    if len(cortes) < 3:
        cortes = np.unique(np.concatenate([cortes, [ref.min() - 1, ref.max() + 1]]))
    cortes[0], cortes[-1] = -np.inf, np.inf
    # Suavização de Laplace: evita que uma faixa vazia exploda o índice.
    cont_p = np.histogram(ref, cortes)[0] + 0.5
    cont_q = np.histogram(cur, cortes)[0] + 0.5
    p, q = cont_p / cont_p.sum(), cont_q / cont_q.sum()
    return float(np.sum((q - p) * np.log(q / p)))


def calcular(dias_recentes: int = 7) -> dict:
    """Notas: semana atual contra as anteriores. Variáveis: semana atual contra o histórico de treino."""
    limite = float(repositorio.config("psi_limite") or 0.2)
    corte = tempo.daqui(dias=-dias_recentes)
    with conectar() as con:
        notas = con.execute("SELECT nota_final, concluido_em FROM tratamentos WHERE nota_final IS NOT NULL").fetchall()
        recentes_feats = con.execute(
            "SELECT f.features FROM leads_features f JOIN leads l ON l.id=f.lead_id WHERE f.gerado_em >= ?", (corte,)
        ).fetchall()
        treino = con.execute("SELECT features FROM rotulos_treino WHERE fonte='base_ficticia'").fetchall()
    ref_notas = [n["nota_final"] for n in notas if n["concluido_em"] < corte]
    cur_notas = [n["nota_final"] for n in notas if n["concluido_em"] >= corte]
    linhas = [{"variavel": "Nota final", "referencia": "semanas anteriores", "n_ref": len(ref_notas),
               "n_atual": len(cur_notas), "psi": round(psi(ref_notas, cur_notas), 3)}]  # fmt: skip
    ref_f = [json.loads(r["features"]) for r in treino]
    cur_f = [json.loads(r["features"]) for r in recentes_feats]
    for v in VARIAVEIS:
        linhas.append({"variavel": ROTULOS.get(v, v), "referencia": "histórico de treino", "n_ref": len(ref_f), "n_atual": len(cur_f),
                       "psi": round(psi([f[v] for f in ref_f], [f[v] for f in cur_f]), 3)})  # fmt: skip
    for linha in linhas:
        linha["situacao"] = "Alerta" if linha["psi"] > limite else "Atenção" if linha["psi"] > 0.1 else "Estável"
    return {"limite": limite, "linhas": linhas, "alerta": any(x["situacao"] == "Alerta" for x in linhas)}
