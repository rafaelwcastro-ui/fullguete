from __future__ import annotations

import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from fastapi.testclient import TestClient

from dados import cnpja
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
            CREATE TABLE bant(lead_id INT,orcamento TEXT,autoridade TEXT,necessidade TEXT,prazo TEXT);
            CREATE TABLE bant_validacoes(lead_id INT,campo TEXT,confirmado INT);
            CREATE TABLE cadencia_passos(id INT,lead_id INT,dia INT,canal TEXT,previsto_para TEXT,feito_em TEXT);
            INSERT INTO bant VALUES(10,'Não deve ser exposto',NULL,NULL,NULL);
            INSERT INTO bant_validacoes VALUES(10,'orcamento',1);
            INSERT INTO cadencia_passos VALUES(1,10,1,'Ligação','2026-11-27',NULL);
            INSERT INTO cadencia_passos VALUES(2,11,1,'Ligação','2026-11-27',NULL);
            INSERT INTO buscas_prospeccao VALUES(1,'#teste','Varejo','Brasília','DF',2026,11);
            """)
            for ident, login, role in [
                (1, "gestor", "gestor"),
                (2, "bdr1", "bdr"),
                (3, "bdr2", "bdr"),
                (4, "exec", "executivo"),
            ]:
                con.execute(
                    "INSERT INTO usuarios VALUES(?,?,?,?,?,1,1)",
                    (ident, login, login, role, auth.gerar_hash("senha-teste", 1000)),
                )
            for ident, owner, executive, fake, opt in [
                (10, 2, 4, 1, 0),
                (11, 3, None, 1, 0),
                (12, 2, 4, 1, 1),
                (13, 2, 4, 0, 0),
                (14, None, None, 1, 0),
            ]:
                con.execute(
                    "INSERT INTO leads VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        ident,
                        f"Empresa {ident}",
                        None,
                        None,
                        None,
                        None,
                        "Varejo",
                        "Na fila do BDR",
                        "Quente",
                        90,
                        None,
                        None,
                        None,
                        owner,
                        executive,
                        fake,
                        opt,
                    ),
                )
                con.execute("INSERT INTO buscas_leads VALUES(1,?)", (ident,))
            con.execute("INSERT INTO consentimentos VALUES(1,10,'consentimento',NULL)")
            con.execute("INSERT INTO consentimentos VALUES(2,12,'consentimento',NULL)")
            con.commit()
        self.before = self.path.read_bytes()
        self.client = TestClient(create_app(self.path))
        self.addCleanup(self.client.close)

    def headers(self, login):
        response = self.client.post("/v1/session", json={"login": login, "senha": "senha-teste"})
        self.assertEqual(response.status_code, 200)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def ids(self, headers, path="/v1/leads"):
        response = self.client.get(path, headers=headers)
        self.assertEqual(response.status_code, 200)
        return {item["id"] for item in response.json()["items"]}

    def test_local_health_exposes_only_service_identity(self):
        for host in ("127.0.0.1:8001", "127.0.0.2:8001"):
            result = self.client.get("/v1/health", headers={"Host": host})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json(), {"servico": "fullguete", "status": "ok"})
        self.assertEqual(self.client.get("/v1/health", headers={"Host": "example.com"}).status_code, 400)

    def test_auth_required(self):
        for path in ["/v1/leads", "/v1/leads/10", "/v1/campaigns", "/v1/me"]:
            self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.post("/v1/session", json={"login": "bdr1", "senha": "errada"}).status_code, 401)

    def test_role_scope_and_opt_out(self):
        manager, bdr, executive = (self.headers(x) for x in ("gestor", "bdr1", "exec"))
        self.assertEqual(self.ids(manager), {10, 11, 14})
        self.assertEqual(self.ids(bdr), {10})
        self.assertEqual(self.ids(executive), {10})
        self.assertEqual(self.ids(bdr, "/v1/leads?view=queue&campaign_id=1"), {10})
        for hidden in (11, 12, 13, 14):
            self.assertEqual(self.client.get(f"/v1/leads/{hidden}", headers=bdr).status_code, 404)
        self.assertEqual(self.client.get("/v1/leads/12", headers=manager).status_code, 404)
        self.assertEqual(self.client.get("/v1/leads?view=triage", headers=bdr).status_code, 403)

    def test_campaign_counts_and_legal_basis(self):
        bdr = self.headers("bdr1")
        self.assertEqual(self.client.get("/v1/campaigns", headers=bdr).json()["items"][0]["importados_visiveis"], 1)
        allowed = self.client.get("/v1/leads/10", headers=bdr).json()
        self.assertTrue(allowed["contato_autorizado"])
        other = self.client.get("/v1/leads/11", headers=self.headers("gestor")).json()
        self.assertFalse(other["contato_autorizado"])
        self.assertEqual(other["base_contato"], "pendente")
        self.assertNotIn("email", allowed)
        self.assertNotIn("telefone", allowed)
        self.assertNotIn("senha_hash", allowed)
        self.assertEqual(self.client.get("/v1/leads", headers=bdr).headers["Cache-Control"], "no-store")

    def test_logout_and_no_write(self):
        bdr = self.headers("bdr1")
        self.assertEqual(self.client.patch("/v1/leads/10", headers=bdr, json={"etapa": "Ganho"}).status_code, 405)
        self.assertEqual(self.client.delete("/v1/session", headers=bdr).status_code, 204)
        self.assertEqual(self.client.get("/v1/me", headers=bdr).status_code, 401)
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_revoked_user_and_no_cross_scope(self):
        bdr = self.headers("bdr1")
        with closing(sqlite3.connect(self.path)) as con:
            con.execute("UPDATE usuarios SET ativo=0 WHERE id=2")
            con.commit()
        self.assertEqual(self.client.get("/v1/leads", headers=bdr).status_code, 401)

    def test_real_copy_requires_non_demo_account(self):
        with TestClient(create_app(self.path, allow_real_copy=True)) as client:
            self.assertEqual(
                client.post("/v1/session", json={"login": "gestor", "senha": "senha-teste"}).status_code, 401
            )

    def test_validation_does_not_echo_credentials(self):
        input_secret = "senha-de-teste-" * 60
        response = self.client.post("/v1/session", json={"login": "bdr1", "senha": input_secret})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(input_secret, response.text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_bdr_progress_read_scope_and_legal_basis(self):
        allowed = self.client.get("/v1/leads/10", headers=self.headers("bdr1")).json()
        self.assertEqual(allowed["bant"]["orcamento"], {"preenchido": True, "confirmado": True})
        self.assertEqual(allowed["bant"]["prazo"], {"preenchido": False, "confirmado": False})
        self.assertNotIn("Não deve ser exposto", str(allowed))
        self.assertEqual(allowed["cadencia"][0]["canal"], "Ligação")
        blocked = self.client.get("/v1/leads/11", headers=self.headers("bdr2")).json()
        self.assertEqual(blocked["cadencia"], [])
        executive = self.headers("exec")
        detail = self.client.get("/v1/leads/10", headers=executive).json()
        self.assertNotIn("bant", detail)
        self.assertNotIn("cadencia", detail)
        self.assertEqual(self.client.get("/v1/leads?view=queue", headers=executive).status_code, 403)

    def test_company_search_scope_projection_and_throttling(self):
        manager = self.headers("gestor")
        bdr = self.headers("bdr1")
        path = "/v1/company-search"
        body = {"uf": "DF", "municipio_ibge": 5300108, "ano": 2026, "mes": 11, "cnae": "4711302"}
        company = dict(
            cnpj="00000000000000",
            razao_social="Exemplo sintético",
            cidade="Brasília",
            uf="DF",
            cnae="4711302",
            data_abertura="01/11/2026",
            email="privado",
            base_legal="sem_base",
        )
        provider = cnpja.Resultado([company], 1, 0, 1, None)
        with (
            patch.dict("os.environ", {"FULLGUETE_API_CNPJA_KEY": ""}),
            patch.object(cnpja, "pesquisar", return_value=provider) as search,
        ):
            self.assertEqual(self.client.post(path, json=body).status_code, 401)
            self.assertEqual(self.client.post(path, headers=bdr, json=body).status_code, 403)
            self.assertEqual(self.client.post(path, headers=manager, json=body).status_code, 503)
            search.assert_not_called()
            with patch.dict("os.environ", {"FULLGUETE_API_CNPJA_KEY": "somente-teste"}):
                result = self.client.post(path, headers=manager, json=body)
                self.assertEqual(result.status_code, 200)
                self.assertNotIn("email", result.json()["items"][0])
                self.assertEqual(search.call_args.args[1]["limit"], 10)
                self.assertEqual(self.client.post(path, headers=manager, json=body).status_code, 429)
                search.assert_called_once()
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_rejects_the_configured_operational_database(self):
        alias = self.path.with_name("alias.db")
        alias.hardlink_to(self.path)
        with patch.dict("os.environ", {"FULLGUETE_DB_PATH": str(self.path)}):
            for path in (self.path, alias):
                with self.subTest(path=path), self.assertRaisesRegex(RuntimeError, "cópia separada"):
                    create_app(path)
