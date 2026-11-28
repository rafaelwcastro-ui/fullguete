from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest import TestCase

from fastapi.testclient import TestClient

from nucleo import auth
from portal_api.app import create_app


class ReadOnlyAPI(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "copy.db"
        with closing(sqlite3.connect(self.path)) as con:
            con.executescript("""
            CREATE TABLE usuarios(id INTEGER,login TEXT,nome TEXT,papel TEXT,senha_hash TEXT,demonstracao INT,ativo INT);
            CREATE TABLE leads(id INTEGER,razao_social TEXT,nome_fantasia TEXT,cnpj TEXT,cidade TEXT,uf TEXT,
            segmento TEXT,etapa TEXT,classificacao TEXT,nota_final REAL,solucao_principal TEXT,sla_limite TEXT,
            retorno_em TEXT,responsavel_id INT,executivo_id INT,base_ficticia INT,opt_out INT);
            CREATE TABLE consentimentos(id INTEGER,lead_id INT,base_legal TEXT,opt_out_em TEXT);
            CREATE TABLE buscas_prospeccao(id INTEGER,tag TEXT,segmento TEXT,cidade TEXT,uf TEXT,ano INT,mes INT);
            CREATE TABLE buscas_leads(busca_id INT,lead_id INT);
            INSERT INTO buscas_prospeccao VALUES(1,'#teste','Varejo','Brasília','DF',2026,11);
            """)
            for ident, login, role in [(1,"gestor","gestor"),(2,"bdr1","bdr"),(3,"bdr2","bdr"),(4,"exec","executivo")]:
                con.execute("INSERT INTO usuarios VALUES(?,?,?,?,?,1,1)",
                            (ident,login,login,role,auth.gerar_hash("senha-teste",1000)))
            for ident, owner, executive, fake, opt in [(10,2,4,1,0),(11,3,None,1,0),
                                                         (12,2,4,1,1),(13,2,4,0,0),(14,None,None,1,0)]:
                con.execute("INSERT INTO leads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (ident,f"Empresa {ident}",None,None,None,None,"Varejo","Na fila do BDR",
                             "Quente",90,None,None,None,owner,executive,fake,opt))
                con.execute("INSERT INTO buscas_leads VALUES(1,?)",(ident,))
            con.execute("INSERT INTO consentimentos VALUES(1,10,'consentimento',NULL)")
            con.execute("INSERT INTO consentimentos VALUES(2,12,'consentimento',NULL)")
            con.commit()
        self.before = self.path.read_bytes()
        self.client = TestClient(create_app(self.path))
        self.addCleanup(self.client.close)

    def headers(self, login):
        response = self.client.post("/v1/session",json={"login":login,"senha":"senha-teste"})
        self.assertEqual(response.status_code,200)
        return {"Authorization":"Bearer "+response.json()["access_token"]}

    def ids(self, headers, path="/v1/leads"):
        response = self.client.get(path,headers=headers)
        self.assertEqual(response.status_code,200)
        return {item["id"] for item in response.json()["items"]}

    def test_auth_required(self):
        for path in ["/v1/leads","/v1/leads/10","/v1/campaigns","/v1/me"]:
            self.assertEqual(self.client.get(path).status_code,401)
        self.assertEqual(self.client.post("/v1/session",json={"login":"bdr1","senha":"errada"}).status_code,401)

    def test_role_scope_and_opt_out(self):
        manager,bdr,executive = (self.headers(x) for x in ("gestor","bdr1","exec"))
        self.assertEqual(self.ids(manager),{10,11,14})
        self.assertEqual(self.ids(bdr),{10})
        self.assertEqual(self.ids(executive),{10})
        self.assertEqual(self.ids(bdr,"/v1/leads?view=queue&campaign_id=1"),{10})
        for hidden in (11,12,13,14):
            self.assertEqual(self.client.get(f"/v1/leads/{hidden}",headers=bdr).status_code,404)
        self.assertEqual(self.client.get("/v1/leads/12",headers=manager).status_code,404)
        self.assertEqual(self.client.get("/v1/leads?view=triage",headers=bdr).status_code,403)

    def test_campaign_counts_and_legal_basis(self):
        bdr = self.headers("bdr1")
        self.assertEqual(self.client.get("/v1/campaigns",headers=bdr).json()["items"][0]["importados_visiveis"],1)
        allowed = self.client.get("/v1/leads/10",headers=bdr).json()
        self.assertTrue(allowed["contato_autorizado"])
        other = self.client.get("/v1/leads/11",headers=self.headers("gestor")).json()
        self.assertFalse(other["contato_autorizado"])
        self.assertEqual(other["base_contato"],"pendente")
        self.assertNotIn("email",allowed)
        self.assertNotIn("telefone",allowed)
        self.assertNotIn("senha_hash",allowed)
        self.assertEqual(self.client.get("/v1/leads",headers=bdr).headers["Cache-Control"],"no-store")

    def test_logout_and_no_write(self):
        bdr = self.headers("bdr1")
        self.assertEqual(self.client.patch("/v1/leads/10",headers=bdr,json={"etapa":"Ganho"}).status_code,405)
        self.assertEqual(self.client.delete("/v1/session",headers=bdr).status_code,204)
        self.assertEqual(self.client.get("/v1/me",headers=bdr).status_code,401)
        self.assertEqual(self.path.read_bytes(),self.before)

    def test_revoked_user_and_no_cross_scope(self):
        bdr = self.headers("bdr1")
        with closing(sqlite3.connect(self.path)) as con:
            con.execute("UPDATE usuarios SET ativo=0 WHERE id=2")
            con.commit()
        self.assertEqual(self.client.get("/v1/leads",headers=bdr).status_code,401)

    def test_real_copy_requires_non_demo_account(self):
        with TestClient(create_app(self.path,allow_real_copy=True)) as client:
            self.assertEqual(client.post("/v1/session",json={"login":"gestor","senha":"senha-teste"}).status_code,401)
