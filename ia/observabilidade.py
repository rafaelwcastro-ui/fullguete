"""Observabilidade: toda chamada de IA (ou plano B) vira uma linha em eventos_ia."""

from __future__ import annotations

from banco import repositorio
from banco.conexao import conectar
from nucleo import tempo


def custo_estimado(tokens_entrada: int, tokens_saida: int) -> float:
    preco = repositorio.config("preco_tokens_usd_milhao") or {"entrada": 0.0, "saida": 0.0}
    return round(tokens_entrada / 1e6 * preco["entrada"] + tokens_saida / 1e6 * preco["saida"], 6)


def registrar(
    agente: str,
    provedor: str,
    *,
    modelo: str | None = None,
    versao_prompt: str | None = None,
    latencia_ms: int | None = None,
    tokens_entrada: int = 0,
    tokens_saida: int = 0,
    plano_b: bool = False,
    cache: bool = False,
    erro: str | None = None,
    lote: str | None = None,
    lead_id: int | None = None,
) -> float:
    custo = 0.0 if cache else custo_estimado(tokens_entrada, tokens_saida)
    with conectar() as con:
        con.execute(
            """INSERT INTO eventos_ia (ocorrido_em, lote, lead_id, agente, provedor, modelo, versao_prompt, latencia_ms,
                   tokens_entrada, tokens_saida, custo_estimado, plano_b, cache, erro)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tempo.iso(), lote, lead_id, agente, provedor, modelo, versao_prompt, latencia_ms, tokens_entrada,
             tokens_saida, custo, int(plano_b), int(cache), (erro or None) and erro[:500]),
        )  # fmt: skip
    return custo


def resumo(desde: str | None = None) -> dict:
    filtro, params = ("WHERE ocorrido_em >= ?", [desde]) if desde else ("", [])
    with conectar() as con:
        linha = con.execute(
            f"""SELECT COUNT(*) chamadas,
                       AVG(CASE WHEN provedor != 'local' AND cache=0 THEN latencia_ms END) latencia,
                       COALESCE(SUM(tokens_entrada),0) t_in, COALESCE(SUM(tokens_saida),0) t_out,
                       COALESCE(SUM(custo_estimado),0) custo,
                       COALESCE(SUM(plano_b),0) planos_b, COALESCE(SUM(cache),0) caches,
                       COALESCE(SUM(CASE WHEN erro IS NOT NULL THEN 1 ELSE 0 END),0) erros
                FROM eventos_ia {filtro}""",
            params,
        ).fetchone()
        leads = con.execute(
            f"SELECT COUNT(*) FROM tratamentos {filtro.replace('ocorrido_em', 'iniciado_em')}", params
        ).fetchone()[0]
    r = dict(linha)
    r["leads_tratados"] = int(leads)
    r["custo_por_lead"] = (r["custo"] / leads) if leads else 0.0
    r["taxa_plano_b"] = (r["planos_b"] / r["chamadas"]) if r["chamadas"] else 0.0
    return r
