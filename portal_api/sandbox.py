"""Cria uma base de homologação nova, exclusivamente com dados gerados."""

import argparse
import os
from contextlib import closing
from pathlib import Path

from banco import semente
from banco.conexao import conectar
from dados import cenario_demo

MARKER = "fullguete-homologacao-v1"


def preparar(diretorio: Path) -> Path:
    diretorio.mkdir(mode=0o700)
    banco = diretorio.resolve() / "homologacao.db"
    models = banco.parent / "modelos"
    models.mkdir(mode=0o700)
    # A preparação roda no processo CLI descartável. Depois o portal usa apenas a cópia.
    with closing(banco.open("xb")):
        banco.chmod(0o600)
    os.environ["FULLGUETE_DB_PATH"] = str(banco)
    os.environ["FULLGUETE_MODELOS_DIR"] = str(models)
    os.environ["FULLGUETE_MODO"] = "simulado"
    semente.garantir_base(simulado=True)
    cenario_demo.montar()
    with conectar(banco) as con:
        con.executescript("""
            CREATE TABLE portal_homologacao (marcador TEXT PRIMARY KEY);
            CREATE TABLE portal_comandos (
                usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
                chave TEXT NOT NULL,
                pedido TEXT NOT NULL,
                resposta TEXT NOT NULL,
                PRIMARY KEY (usuario_id, chave)
            );
        """)
        con.execute("INSERT INTO portal_homologacao VALUES (?)", (MARKER,))
    return banco


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diretorio", type=Path, help="Diretório novo para o banco e os modelos")
    print(preparar(parser.parse_args().diretorio))
