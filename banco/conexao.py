"""Conexão com o SQLite e aplicação das migrações versionadas."""

from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing, contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path

from nucleo import config

PASTA = Path(__file__).resolve().parent
ESQUEMA = PASTA / "esquema.sql"
MIGRACOES = PASTA / "migracoes"

_migrados: set[str] = set()
_trava = threading.Lock()
_conexao_transacional: ContextVar[sqlite3.Connection | None] = ContextVar("conexao_transacional", default=None)


@contextmanager
def reutilizar_transacao(con: sqlite3.Connection) -> Iterator[None]:
    """Entrega uma transação já aberta aos serviços durante o comando do portal."""
    if not con.in_transaction or _conexao_transacional.get() is not None:
        raise RuntimeError("É necessária uma transação externa exclusiva.")
    token = _conexao_transacional.set(con)
    try:
        yield
    finally:
        _conexao_transacional.reset(token)


def agora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _migracoes_pendentes(versao_atual: int) -> list[tuple[int, Path]]:
    arquivos = []
    for arq in sorted(MIGRACOES.glob("*.sql")):
        if m := re.match(r"(\d+)_", arq.name):
            numero = int(m.group(1))
            if numero > versao_atual:
                arquivos.append((numero, arq))
    return arquivos


def migrar(con: sqlite3.Connection) -> int:
    """Cria o esquema base e aplica as migrações pendentes. Retorna a versão final."""
    con.execute(
        "CREATE TABLE IF NOT EXISTS esquema_versao "
        "(versao INTEGER PRIMARY KEY, aplicada_em TEXT NOT NULL, arquivo TEXT)"
    )
    versao = con.execute("SELECT COALESCE(MAX(versao), 0) FROM esquema_versao").fetchone()[0]
    if versao == 0:
        con.executescript(ESQUEMA.read_text(encoding="utf-8"))
        con.execute("INSERT INTO esquema_versao VALUES (1, ?, 'esquema.sql')", (agora(),))
        versao = 1
    for numero, arq in _migracoes_pendentes(versao):
        con.executescript(arq.read_text(encoding="utf-8"))
        con.execute("INSERT INTO esquema_versao VALUES (?, ?, ?)", (numero, agora(), arq.name))
        versao = numero
    # Compatibilidade não destrutiva para bases criadas antes do BANT progressivo.
    # A tabela pode não existir mesmo em instalações com esquema_versao preenchida.
    con.execute(
        """CREATE TABLE IF NOT EXISTS bant_validacoes (
            lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
            campo TEXT NOT NULL CHECK (campo IN ('orcamento', 'autoridade', 'necessidade', 'prazo')),
            confirmado INTEGER NOT NULL DEFAULT 0 CHECK (confirmado IN (0, 1)),
            atualizado_em TEXT NOT NULL,
            usuario_id INTEGER REFERENCES usuarios(id),
            PRIMARY KEY (lead_id, campo)
        )"""
    )
    con.commit()
    return versao


@contextmanager
def conectar(caminho: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Abre uma conexão, garante o esquema e faz commit ao sair (ou rollback em erro)."""
    transacao = _conexao_transacional.get()
    if transacao is not None:
        if caminho is not None:
            raise RuntimeError("Um serviço não pode trocar de banco durante uma transação externa.")
        yield transacao
        return
    caminho = Path(caminho or config.caminho_banco())
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(caminho, timeout=15)) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        chave = str(caminho.resolve())
        if chave not in _migrados:
            with _trava:
                if chave not in _migrados:
                    migrar(con)
                    _migrados.add(chave)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
