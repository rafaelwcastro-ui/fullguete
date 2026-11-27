"""Exporta somente agregados de leads fictícios de uma cópia SQLite, sem modificar o banco."""
from __future__ import annotations

import argparse
import json
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

STAGES = ("Tratado", "Qualificado", "Reunião marcada")


def export_snapshot(path: Path, end: date) -> dict:
    path = path.resolve(strict=True)
    # mode=ro impede criação e alteração do arquivo; nenhuma função de migração é chamada.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as con:
        con.execute("PRAGMA query_only = ON")
        start = end - timedelta(days=29)
        rows = con.execute(
            """SELECT substr(l.criado_em,1,10) AS dia, COUNT(DISTINCT l.id),
               COUNT(DISTINCT CASE WHEN h.para=? THEN l.id END),
               COUNT(DISTINCT CASE WHEN h.para=? THEN l.id END),
               COUNT(DISTINCT CASE WHEN h.para=? THEN l.id END)
               FROM leads l LEFT JOIN etapas_historico h ON h.lead_id=l.id AND substr(h.registrado_em,1,10)<=?
               WHERE l.base_ficticia=1 AND substr(l.criado_em,1,10) BETWEEN ? AND ?
               GROUP BY dia""",
            (*STAGES, end.isoformat(), start.isoformat(), end.isoformat()),
        ).fetchall()
    # Saída somente agregada por coorte de criação, nunca CNPJ, nome ou identificador.
    counts = {row[0]: row[1:] for row in rows}
    series = []
    for i in range(30):
        day = (start + timedelta(days=i)).isoformat()
        values = counts.get(day, (0, 0, 0, 0))
        series.append(dict(zip(("day", "capturados", "tratados", "qualificados", "reunioes"), (day, *values))))
    return {"schema": "fullguete.dashboard.v1", "source": "synthetic-only", "series": series}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo-copy", type=Path, required=True, help="Cópia isolada do SQLite de demonstração")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="Data final da janela UTC")
    args = parser.parse_args()
    print(json.dumps(export_snapshot(args.demo_copy, args.end), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
