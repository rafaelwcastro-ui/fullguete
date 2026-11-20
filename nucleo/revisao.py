"""Human in the loop: revisão humana e correções da IA, sempre com motivo registrado."""

from __future__ import annotations

import sqlite3

from banco import repositorio
from banco.conexao import conectar
from ia import nota

from . import comercial, estados, tempo


def registrar_correcao(con: sqlite3.Connection, lead_id: int, usuario_id: int | None, campo: str,
                       valor_ia: str | None, valor_correto: str | None, motivo: str) -> None:  # fmt: skip
    if not motivo.strip():
        raise ValueError("Registre o motivo da correção.")
    trat = con.execute(
        "SELECT id FROM tratamentos WHERE lead_id=? AND concluido_em IS NOT NULL ORDER BY id DESC LIMIT 1", (lead_id,)
    ).fetchone()
    con.execute(
        "INSERT INTO correcoes_ia (lead_id, tratamento_id, usuario_id, campo, valor_ia, valor_correto, concorda, motivo,"
        " registrada_em) VALUES (?,?,?,?,?,?,?,?,?)",
        (lead_id, trat["id"] if trat else None, usuario_id, campo, valor_ia, valor_correto,
         int(valor_ia == valor_correto), motivo.strip(), tempo.iso()),
    )  # fmt: skip
    repositorio.auditar(con, f"usuario:{usuario_id}", "correcao_ia", "leads", lead_id,
                        {"campo": campo, "valor_ia": valor_ia, "valor_correto": valor_correto, "motivo": motivo})  # fmt: skip


def _trocar_solucao(con: sqlite3.Connection, lead_id: int, solucao_id: str) -> None:
    con.execute("UPDATE leads SET solucao_principal=? WHERE id=?", (solucao_id, lead_id))


def resolver(lead_id: int, usuario: dict, decisao: str, motivo: str, *, solucao_id: str | None = None,
             classificacao: str | None = None, motivo_descarte: str | None = None) -> str:  # fmt: skip
    """Resolve um caso da fila de revisão humana. decisao: aprovar, ajustar ou descartar.

    Retorna a etapa final do lead.
    """
    if not motivo.strip():
        raise ValueError("Escreva o motivo da decisão.")
    ator = usuario["login"]
    with conectar() as con:
        lead = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if lead is None or lead["etapa"] != estados.REVISAO:
            raise ValueError("Este lead não está mais na revisão humana.")
        classe = lead["classificacao"]
        if solucao_id and solucao_id != lead["solucao_principal"]:
            registrar_correcao(con, lead_id, usuario["id"], "solucao", lead["solucao_principal"], solucao_id, motivo)
            _trocar_solucao(con, lead_id, solucao_id)
        if classificacao and classificacao != classe:
            registrar_correcao(con, lead_id, usuario["id"], "classificacao", classe, classificacao, motivo)
            con.execute("UPDATE leads SET classificacao=? WHERE id=?", (classificacao, lead_id))
            classe = classificacao
        if decisao == "aprovar" and not (solucao_id or classificacao):
            registrar_correcao(con, lead_id, usuario["id"], "classificacao", classe, classe, motivo)

        if decisao == "descartar" or classe == "Descartar":
            estados.mudar(con, lead_id, estados.DESCARTADO, ator, motivo=motivo_descarte or "Sem fit", detalhe=motivo)
            return estados.DESCARTADO
        if classe == "Frio":
            estados.mudar(con, lead_id, estados.NUTRICAO, ator, detalhe=f"Revisão humana: {motivo}")
            return estados.NUTRICAO
        estados.mudar(con, lead_id, estados.FILA_BDR, ator, detalhe=f"Revisão humana: {motivo}")
        sla = repositorio.config("sla_horas") or {}
        con.execute("UPDATE leads SET sla_limite=? WHERE id=?", (tempo.daqui(horas=sla.get(classe, 24)), lead_id))
        bdr = lead["responsavel_id"] or comercial.escolher_bdr(con)
        if bdr:
            comercial.atribuir(con, lead_id, bdr, ator, "Aprovado na revisão humana")
            comercial.criar_cadencia(con, lead_id)
        return estados.FILA_BDR


CLASSES_REVISAO = [c for c in nota.CLASSES]
