"""Histórico de análises em SQLite."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

CAMINHO = Path(os.environ.get(
    "FULLGUETE_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "fullguete.db",
))

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
    site TEXT, email TEXT, telefone TEXT, descricao TEXT,
    score INTEGER, justificativa TEXT
);
CREATE INDEX IF NOT EXISTS idx_leads_analise ON leads(analise_id);

CREATE TABLE IF NOT EXISTS carteira_bdr (
    id INTEGER PRIMARY KEY,
    responsavel TEXT NOT NULL,
    chave TEXT NOT NULL,
    chave_nome TEXT NOT NULL,
    dados TEXT NOT NULL,
    score INTEGER NOT NULL,
    etapa TEXT NOT NULL,
    proxima_acao TEXT NOT NULL DEFAULT '',
    retorno_em TEXT,
    origem TEXT NOT NULL,
    metodo TEXT NOT NULL,
    analise_id INTEGER NOT NULL,
    versao INTEGER NOT NULL DEFAULT 0,
    atualizada_em TEXT NOT NULL,
    UNIQUE(responsavel, chave)
);
CREATE INDEX IF NOT EXISTS idx_carteira_nome ON carteira_bdr(responsavel, chave_nome);
CREATE TABLE IF NOT EXISTS atividades_bdr (
    id INTEGER PRIMARY KEY,
    carteira_id INTEGER NOT NULL REFERENCES carteira_bdr(id),
    registrada_em TEXT NOT NULL,
    tipo TEXT NOT NULL,
    descricao TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_atividades_carteira ON atividades_bdr(carteira_id, id);
"""
COLUNAS_LEAD = [
    "empresa", "cnpj", "setor", "porte", "cidade", "uf", "site", "email", "telefone",
    "score", "justificativa", "descricao",
]


@contextmanager
def conectar():
    CAMINHO.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(CAMINHO, timeout=10)) as con, con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(_SCHEMA)
        if "descricao" not in {col["name"] for col in con.execute("PRAGMA table_info(leads)")}:
            con.execute("BEGIN IMMEDIATE")
            if "descricao" not in {col["name"] for col in con.execute("PRAGMA table_info(leads)")}:
                con.execute("ALTER TABLE leads ADD COLUMN descricao TEXT")
            con.commit()
        yield con


def salvar(ranking: pd.DataFrame, icp: dict, metodo: str, arquivo: str) -> int:
    with conectar() as con:
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
            (analise_id, pos, *[str(r.get(c, "")) if c != "score" else int(r[c]) for c in COLUNAS_LEAD])
            for pos, (_, r) in enumerate(ranking.iterrows(), start=1)
        ]
        con.executemany(
            f"INSERT INTO leads (analise_id, posicao, {', '.join(COLUNAS_LEAD)}) VALUES ({', '.join('?' * (len(COLUNAS_LEAD) + 2))})",
            linhas,
        )
    return analise_id


def listar_analises() -> pd.DataFrame:
    with conectar() as con:
        return pd.read_sql_query("SELECT * FROM analises ORDER BY id DESC", con)


def carregar_leads(analise_id: int) -> pd.DataFrame:
    with conectar() as con:
        return pd.read_sql_query(
            "SELECT * FROM leads WHERE analise_id = ? ORDER BY posicao", con, params=(analise_id,)
        )


def excluir(analise_id: int) -> None:
    with conectar() as con:
        con.execute("DELETE FROM analises WHERE id = ?", (analise_id,))
