import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from export_dashboard import export_snapshot


class DashboardSnapshotTest(unittest.TestCase):
    def test_excludes_real_leads_and_future_history_and_preserves_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "demo.db"
            with sqlite3.connect(path) as con:
                con.executescript("""
                CREATE TABLE leads(id INTEGER, criado_em TEXT, base_ficticia INTEGER);
                CREATE TABLE etapas_historico(lead_id INTEGER, para TEXT, registrado_em TEXT);
                INSERT INTO leads VALUES (1,'2026-11-26',1),(2,'2026-11-26',0),(3,'2026-11-26',1);
                INSERT INTO etapas_historico VALUES
                  (1,'Tratado','2026-11-26'),(1,'Tratado','2026-11-26'),
                  (2,'Tratado','2026-11-26'),(3,'Qualificado','2026-11-28');
                """)
            before = path.read_bytes()
            output = export_snapshot(path, date(2026, 11, 27))
            self.assertEqual(len(output["series"]), 30)
            self.assertEqual(
                output["series"][-2],
                {"day": "2026-11-26", "capturados": 2, "tratados": 1, "qualificados": 0, "reunioes": 0},
            )
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
