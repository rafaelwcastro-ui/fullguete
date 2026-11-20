"""Operações do time comercial: distribuição, cadência, atividades, BANT, correções e oportunidades."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from banco import repositorio

from . import estados, tempo

CADENCIA_PADRAO = [
    (0, "Ligação", "Primeira ligação com o roteiro de abertura"),
    (0, "E-mail", "E-mail de apresentação"),
    (2, "WhatsApp", "Mensagem curta retomando o assunto"),
    (5, "Ligação", "Segunda ligação com as perguntas de descoberta"),
    (8, "E-mail", "E-mail de encerramento da cadência"),
]
ETAPAS_ATIVAS_BDR = (estados.FILA_BDR, estados.EM_CONTATO, estados.QUALIFICADO)


def escolher_bdr(con: sqlite3.Connection) -> int | None:
    """BDR com a menor fila ativa (empate: o de menor id)."""
    linha = con.execute(
        f"""SELECT u.id, COUNT(l.id) fila FROM usuarios u
            LEFT JOIN leads l ON l.responsavel_id = u.id AND l.etapa IN ({",".join("?" * len(ETAPAS_ATIVAS_BDR))})
            WHERE u.papel='bdr' AND u.ativo=1 GROUP BY u.id ORDER BY fila, u.id LIMIT 1""",
        ETAPAS_ATIVAS_BDR,
    ).fetchone()
    return int(linha["id"]) if linha else None


def atribuir(con: sqlite3.Connection, lead_id: int, usuario_id: int, ator: str, motivo: str,
             momento: str | None = None) -> None:  # fmt: skip
    momento = momento or tempo.iso()
    con.execute("UPDATE atribuicoes SET ativa=0 WHERE lead_id=? AND ativa=1", (lead_id,))
    con.execute(
        "INSERT INTO atribuicoes (lead_id, usuario_id, atribuido_em, atribuido_por, motivo) VALUES (?,?,?,?,?)",
        (lead_id, usuario_id, momento, ator, motivo),
    )
    con.execute("UPDATE leads SET responsavel_id=? WHERE id=?", (usuario_id, lead_id))
    repositorio.auditar(con, ator, "atribuicao", "leads", lead_id, {"usuario_id": usuario_id, "motivo": motivo})


def criar_cadencia(con: sqlite3.Connection, lead_id: int, inicio: str | None = None) -> None:
    if con.execute("SELECT 1 FROM cadencia_passos WHERE lead_id=? AND feito_em IS NULL", (lead_id,)).fetchone():
        return
    base = tempo.ler(inicio) or tempo.agora()
    con.executemany(
        "INSERT INTO cadencia_passos (lead_id, dia, canal, descricao, previsto_para) VALUES (?,?,?,?,?)",
        [(lead_id, dia, canal, desc, tempo.iso(base + timedelta(days=dia))) for dia, canal, desc in CADENCIA_PADRAO],
    )
