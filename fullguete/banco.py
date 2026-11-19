"""Histórico de análises em SQLite."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

CAMINHO = Path(__file__).resolve().parent.parent / "data" / "fullguete.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criada_em TEXT NOT NULL,
    arquivo TEXT,
    metodo TEXT NOT NULL,
    icp TEXT NOT NULL,
    total_leads INTEGER NOT NULL,
    score_medio REAL
);
CREATE TABLE IF NOT EXISTS leads (
    analise_id INTEGER NOT NULL REFERENCES analises(id) ON DELETE CASCADE,
    posicao INTEGER NOT NULL,
    empresa TEXT, cnpj TEXT, setor TEXT, porte TEXT, cidade TEXT, uf TEXT,
    site TEXT, email TEXT, telefone TEXT,
    score INTEGER, justificativa TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_analise ON leads(analise_id);
"""
COLUNAS_LEAD = ["empresa", "cnpj", "setor", "porte", "cidade", "uf", "site", "email", "telefone", "score", "justificativa"]


def _conectar() -> sqlite3.Connection:
    CAMINHO.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(CAMINHO)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(_SCHEMA)
    return con


def salvar(ranking: pd.DataFrame, icp: dict, metodo: str, arquivo: str) -> int:
    with _conectar() as con:
        cur = con.execute(
            "INSERT INTO analises (criada_em, arquivo, metodo, icp, total_leads, score_medio) VALUES (?,?,?,?,?,?)",
            (
                datetime.now().isoformat(timespec="seconds"),
                arquivo,
                metodo,
                json.dumps(icp, ensure_ascii=False),
                len(ranking),
                float(ranking["score"].mean()) if len(ranking) else None,
            ),
        )
        analise_id = cur.lastrowid
        linhas = [
            (analise_id, pos, *[str(r[c]) if c != "score" else int(r[c]) for c in COLUNAS_LEAD])
            for pos, (_, r) in enumerate(ranking.iterrows(), start=1)
        ]
        con.executemany(
            f"INSERT INTO leads (analise_id, posicao, {', '.join(COLUNAS_LEAD)}) VALUES ({', '.join('?' * (len(COLUNAS_LEAD) + 2))})",
            linhas,
        )
    return analise_id


def listar_analises() -> pd.DataFrame:
    with _conectar() as con:
        return pd.read_sql_query("SELECT * FROM analises ORDER BY id DESC", con)


def carregar_leads(analise_id: int) -> pd.DataFrame:
    with _conectar() as con:
        return pd.read_sql_query(
            "SELECT * FROM leads WHERE analise_id = ? ORDER BY posicao", con, params=(analise_id,)
        )


def excluir(analise_id: int) -> None:
    with _conectar() as con:
        con.execute("DELETE FROM analises WHERE id = ?", (analise_id,))
