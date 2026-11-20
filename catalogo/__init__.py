"""Catálogo de soluções Equifax e regras do grafo, lidos dos arquivos JSON desta pasta."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PASTA = Path(__file__).resolve().parent
ARQ_CATALOGO = PASTA / "catalogo_equifax.json"
ARQ_REGRAS = PASTA / "regras_grafo.json"


@lru_cache(maxsize=1)
def carregar() -> dict:
    return json.loads(ARQ_CATALOGO.read_text(encoding="utf-8"))


def carregar_regras() -> dict:
    # Sem cache: o gestor pode editar as regras e o grafo precisa refletir na hora.
    return json.loads(ARQ_REGRAS.read_text(encoding="utf-8"))


def solucoes() -> list[dict]:
    return carregar()["solucoes"]


def por_id() -> dict[str, dict]:
    return {s["id"]: s for s in solucoes()}


def ids() -> set[str]:
    return set(por_id())


def nome(solucao_id: str) -> str:
    return por_id().get(solucao_id, {}).get("nome", solucao_id)


def linhas() -> dict[str, str]:
    return {linha["id"]: linha["nome"] for linha in carregar()["linhas"]}


def validar(catalogo: dict | None = None, regras: dict | None = None) -> list[str]:
    """Lista inconsistências entre catálogo e regras. Vazio quando está tudo certo."""
    catalogo = catalogo or carregar()
    regras = regras or carregar_regras()
    problemas = []
    ids_sol = {s["id"] for s in catalogo["solucoes"]}
    ids_linha = {linha["id"] for linha in catalogo["linhas"]}
    ids_sinal = {s["id"] for s in regras["sinais"]}
    ids_seg = {s["id"] for s in regras["segmentos"]}
    if len(ids_sol) != len(catalogo["solucoes"]):
        problemas.append("Há ids de solução repetidos no catálogo.")
    for s in catalogo["solucoes"]:
        if s["linha"] not in ids_linha:
            problemas.append(f"{s['id']}: linha desconhecida {s['linha']}.")
        if len(s["perguntas_descoberta"]) != 3:
            problemas.append(f"{s['id']}: precisa de 3 perguntas de descoberta.")
        problemas += [f"{s['id']}: sinal desconhecido {x}." for x in s["sinais"] if x not in ids_sinal]
        problemas += [f"{s['id']}: complementar desconhecido {x}." for x in s["complementares"] if x not in ids_sol]
    for aresta in regras["segmento_sinal"]:
        if aresta["de"] not in ids_seg or aresta["para"] not in ids_sinal:
            problemas.append(f"Aresta segmento para sinal inválida: {aresta}.")
    for aresta in regras["sinal_solucao"]:
        if aresta["de"] not in ids_sinal or aresta["para"] not in ids_sol:
            problemas.append(f"Aresta sinal para solução inválida: {aresta}.")
    return problemas
