"""Gera o snapshot embarcado a partir de uma base descartável de exemplos."""

import json
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from export_dashboard import STAGES, export_snapshot

END = date(2026, 11, 27)
SAMPLE = (
    (1, 24, 19, 8, 3),
    (5, 38, 29, 12, 5),
    (9, 29, 24, 10, 4),
    (13, 46, 39, 17, 7),
    (17, 36, 30, 13, 5),
    (21, 52, 43, 19, 8),
    (24, 41, 34, 15, 6),
    (27, 57, 48, 22, 9),
)


def main() -> None:
    with TemporaryDirectory() as directory:
        database = Path(directory) / "demo.db"
        with closing(sqlite3.connect(database)) as connection, connection:
            connection.executescript("""
                CREATE TABLE leads(id INTEGER PRIMARY KEY, criado_em TEXT, base_ficticia INTEGER);
                CREATE TABLE etapas_historico(lead_id INTEGER, para TEXT, registrado_em TEXT);
            """)
            lead_id = 0
            for day, captured, *totals in SAMPLE:
                timestamp = END.replace(day=day).isoformat()
                for index in range(captured):
                    lead_id += 1
                    connection.execute("INSERT INTO leads VALUES (?, ?, 1)", (lead_id, timestamp))
                    connection.executemany(
                        "INSERT INTO etapas_historico VALUES (?, ?, ?)",
                        (
                            (lead_id, stage, timestamp)
                            for stage, total in zip(STAGES, totals, strict=True)
                            if index < total
                        ),
                    )
        snapshot = export_snapshot(database, END)
    output = Path(__file__).resolve().parents[1] / "lib" / "demo-dashboard.json"
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
