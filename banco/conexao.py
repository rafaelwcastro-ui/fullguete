"""Conexão com o SQLite e aplicação das migrações versionadas."""

from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from nucleo import config

PASTA = Path(__file__).resolve().parent
ESQUEMA = PASTA / "esquema.sql"
MIGRACOES = PASTA / "migracoes"

_migrados: set[str] = set()
_trava = threading.Lock()


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
    con.commit()
    return versao


@contextmanager
def conectar(caminho: Path | None = None) -> Iterator[sqlite3.Connection]:
    """Abre uma conexão, garante o esquema e faz commit ao sair (ou rollback em erro)."""
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
