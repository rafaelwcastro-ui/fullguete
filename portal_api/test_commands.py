"""Regressão das gravações usando cópias do esquema e serviços reais."""

import shutil
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from nucleo import estados, tempo
from portal_api.app import create_app


class CommandsTest(TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = TemporaryDirectory()
        cls.addClassCleanup(temporary.cleanup)
        cls.seed = Path(temporary.name) / "seed"
        subprocess.run([sys.executable, "-m", "portal_api.sandbox", str(cls.seed)], check=True, capture_output=True)

    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name) / "copy"
        shutil.copytree(self.seed, directory)
        self.path = directory / "homologacao.db"
        self.client = TestClient(create_app(self.path, write_enabled=True))
        self.addCleanup(self.client.close)
        self.manager = self.login("gestor")

    def login(self, login, client=None):
        response = (client or self.client).post("/v1/session", json={"login": login, "senha": "fullguete-demo"})
        self.assertEqual(response.status_code, 200, response.text)
        return {"Authorization": "Bearer " + response.json()["access_token"]}

    def query(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as con, con:
            con.row_factory = sqlite3.Row
            return [dict(row) for row in con.execute(sql, args)]

    def lead(self, stage=estados.FILA_BDR, *, owner=2, legal=True):
        sql = """SELECT l.id,l.versao FROM leads l WHERE l.etapa=? AND l.responsavel_id=? AND l.opt_out=0
                 AND EXISTS(SELECT 1 FROM consentimentos c WHERE c.lead_id=l.id
                    AND c.id=(SELECT MAX(id) FROM consentimentos WHERE lead_id=l.id)
                    AND c.base_legal IN ('consentimento','legitimo_interesse') AND c.opt_out_em IS NULL)=?
                 ORDER BY l.id LIMIT 1"""
        return self.query(sql, (stage, owner, int(legal)))[0]

    def target(self, lead_id):
        return self.query("SELECT id,versao FROM leads WHERE id=?", (lead_id,))[0]

    def command(self, action, auth=None, nonce=None, client=None, **fields):
        return (client or self.client).post(
            "/v1/commands",
            headers={**(self.manager if auth is None else auth), "Idempotency-Key": str(nonce or uuid4())},
            json={"acao": action, **fields},
        )

    def successful(self, action, **fields):
        response = self.command(action, **fields)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def search(self, **fields):
        return self.successful("buscar", uf="DF", municipio_ibge=5300108, ano=2026, mes=11, cnae="4711302", **fields)

    def test_bootstrap_opt_in_and_real_data_guard(self):
        lead = self.lead()
        with TestClient(create_app(self.path, write_enabled=False)) as readonly:
            manager = self.login("gestor", readonly)
            response = self.command("bant", client=readonly, auth=manager, leads=[lead], valores={"prazo": "3 meses"})
            self.assertEqual(response.status_code, 403)
        self.query("UPDATE leads SET base_ficticia=0 WHERE id=?", (lead["id"],))
        with self.assertRaisesRegex(RuntimeError, "fora do ambiente fictício"):
            create_app(self.path, write_enabled=True)
        with self.assertRaises(RuntimeError):
            create_app(self.path, write_enabled=True, allow_real_copy=True)

    def test_history_selective_dedup_local_ai_and_review(self):
        nonce = uuid4()
        with patch("dados.cnpja.pesquisar") as external:
            history = self.search(nonce=nonce)
            self.assertEqual(self.search(nonce=nonce), history)
            external.assert_not_called()
        self.assertEqual(len(self.client.get("/v1/search-history", headers=self.manager).json()["items"]), 1)
        self.assertEqual(self.client.get(f"/v1/search-history/{history['id']}", headers=self.manager).json(), history)
        cnpj = history["items"][0]["cnpj"]
        second = history["items"][1]["cnpj"]
        self.assertEqual(self.command("importar", campanha=history["id"], cnpjs=[cnpj, "0" * 14]).status_code, 422)
        self.assertFalse(self.query("SELECT id FROM leads WHERE cnpj=?", (cnpj,)))
        self.assertEqual(self.successful("importar", campanha=history["id"], cnpjs=[cnpj])["criados"], 1)
        next_campaign = self.search()["id"]
        self.assertEqual(self.successful("importar", campanha=next_campaign, cnpjs=[cnpj])["duplicados"], 1)
        self.assertFalse(self.query("SELECT id FROM leads WHERE cnpj=?", (second,)))
        imported = self.query("SELECT id,versao,base_ficticia FROM leads WHERE cnpj=?", (cnpj,))
        self.assertEqual(len(imported), 1)
        self.assertEqual(imported[0]["base_ficticia"], 1)
        lead = self.target(imported[0]["id"])
        self.assertEqual(len(self.query("SELECT * FROM buscas_leads WHERE lead_id=?", (lead["id"],))), 2)
        with patch("ia.provedor.chamar") as llm, patch("dados.cnpjws.consultar") as cnpjws:
            self.assertEqual(self.successful("processar", leads=[lead])["total"], 1)
            llm.assert_not_called()
            cnpjws.assert_not_called()
        self.assertTrue(
            self.query("SELECT id FROM tratamentos WHERE lead_id=? AND concluido_em IS NOT NULL", (lead["id"],))
        )
        case = self.query(
            "SELECT id,versao FROM leads WHERE etapa=? AND opt_out=0 AND classificacao IS NOT 'Quente' LIMIT 1",
            (estados.REVISAO,),
        )[0]
        outcome = self.successful(
            "revisar", leads=[case], decisao="ajustar", classificacao="Quente", motivo="Revisão da classificação"
        )
        self.assertEqual(outcome["etapa"], estados.FILA_BDR)
        self.assertTrue(self.query("SELECT id FROM correcoes_ia WHERE lead_id=?", (case["id"],)))

    def test_scope_opt_out_and_legal_basis(self):
        bdr = self.login("bdr.ana")
        executive = self.login("executivo")
        lead = self.lead()
        outside = self.lead(owner=3)
        body = {"valores": {"prazo": "3 meses"}}
        for headers, target, expected in [({}, lead, 401), (bdr, outside, 404), (executive, lead, 403)]:
            response = self.command("bant", auth=headers, leads=[target], **body)
            self.assertEqual(response.status_code, expected, response.text)
        self.assertEqual(self.command("triagem", auth=bdr, leads=[lead], bdr=2, motivo="Motivo teste").status_code, 403)
        self.assertEqual(self.client.get("/v1/search-history", headers=bdr).status_code, 403)
        self.query("UPDATE leads SET opt_out=1 WHERE id=?", (lead["id"],))
        self.assertEqual(self.command("bant", leads=[lead], **body).status_code, 404)
        self.query("UPDATE consentimentos SET base_legal='sem_base' WHERE lead_id=?", (outside["id"],))
        self.assertEqual(
            self.command("atividade", leads=[outside], tipo="Ligação", resultado="Sem resposta").status_code, 422
        )
        self.assertEqual(
            self.command("retorno", leads=[outside], titulo="Retornar ligação", inicio=tempo.daqui(dias=1)).status_code,
            422,
        )
        step = self.query("SELECT id FROM cadencia_passos WHERE lead_id=? LIMIT 1", (outside["id"],))[0]["id"]
        self.assertEqual(self.command("cadencia", leads=[outside], passo=step, feito=True).status_code, 422)
        self.successful("bant", leads=[outside], **body)

    def test_atomic_batch_and_reassignment(self):
        lead = self.lead()
        bad = self.query("SELECT id,versao FROM leads WHERE etapa=? AND opt_out=0 LIMIT 1", (estados.GANHO,))[0]
        before = self.query("SELECT count(*) AS n FROM etapas_historico")[0]
        rejected = self.command("status", leads=[lead, bad], etapa=estados.EM_ANALISE, justificativa="Revisão de lote")
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(self.target(lead["id"]), lead)
        self.assertEqual(self.query("SELECT count(*) AS n FROM etapas_historico")[0], before)
        self.assertFalse(self.query("SELECT * FROM portal_comandos"))
        nonce = uuid4()
        bdr = self.login("bdr.ana")
        self.successful("bant", auth=bdr, nonce=nonce, leads=[lead], valores={"prazo": "3 meses"})
        self.successful("atribuir", leads=[self.target(lead["id"])], bdr=3, motivo="Redistribuição de carteira")
        self.assertEqual(
            self.command("bant", auth=bdr, nonce=nonce, leads=[lead], valores={"prazo": "3 meses"}).status_code, 404
        )
        self.assertEqual(self.client.get(f"/v1/leads/{lead['id']}", headers=self.login("bdr.ana")).status_code, 404)
        self.assertEqual(self.client.get(f"/v1/leads/{lead['id']}", headers=self.login("bdr.bruno")).status_code, 200)
        triage = self.query("SELECT id,versao FROM leads WHERE etapa=? AND opt_out=0 LIMIT 1", (estados.NUTRICAO,))[0]
        self.successful("triagem", leads=[triage], bdr=2, motivo="Triagem de demonstração")
        self.assertEqual(
            self.query("SELECT etapa,responsavel_id FROM leads WHERE id=?", (triage["id"],))[0],
            {"etapa": estados.FILA_BDR, "responsavel_id": 2},
        )

    def test_parallel_revision_and_idempotency_survive_restart(self):
        lead = self.lead()
        nonce = uuid4()
        barrier = Barrier(2)

        def run(key):
            barrier.wait(timeout=5)
            return self.command("bant", leads=[lead], nonce=key, valores={"necessidade": "Avaliar crédito"})

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run, nonce)
            second = pool.submit(run, nonce)
            self.assertEqual([first.result().status_code, second.result().status_code], [200, 200])
        self.assertEqual(self.target(lead["id"])["versao"], lead["versao"] + 1)
        with TestClient(create_app(self.path, write_enabled=True)) as reopened:
            headers = self.login("gestor", reopened)
            self.assertEqual(
                self.command(
                    "bant",
                    client=reopened,
                    auth=headers,
                    leads=[lead],
                    nonce=nonce,
                    valores={"necessidade": "Avaliar crédito"},
                ).status_code,
                200,
            )
            self.assertEqual(
                self.command(
                    "bant",
                    client=reopened,
                    auth=headers,
                    leads=[lead],
                    nonce=nonce,
                    valores={"necessidade": "Outro conteúdo"},
                ).status_code,
                409,
            )
        updated = self.target(lead["id"])
        barrier.reset()
        lead = updated
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run, uuid4())
            second = pool.submit(run, uuid4())
            self.assertEqual(sorted([first.result().status_code, second.result().status_code]), [200, 409])

    def test_bdr_activity_cadence_bant_return_and_discard(self):
        bdr = self.login("bdr.ana")
        lead = self.lead()
        ident = lead["id"]
        self.successful(
            "bant",
            auth=bdr,
            leads=[lead],
            valores={"necessidade": "Necessidade confirmada"},
            confirmacoes={"necessidade": True},
        )
        self.successful("atividade", auth=bdr, leads=[self.target(ident)], tipo="Ligação", resultado="Sem resposta")
        detail = self.client.get(f"/v1/leads/{ident}", headers=bdr).json()
        self.assertTrue(detail["bant"]["necessidade"]["confirmado"])
        self.assertFalse(detail["bant"]["orcamento"]["preenchido"])
        self.assertTrue(detail["atividades"])
        step = next(item["id"] for item in detail["cadencia"] if not item["feito_em"])
        self.successful("cadencia", auth=bdr, leads=[self.target(ident)], passo=step, feito=True)
        event = self.successful(
            "retorno", auth=bdr, leads=[self.target(ident)], titulo="Retornar amanhã", inicio=tempo.daqui(dias=1)
        )
        self.assertTrue(
            self.query("SELECT id FROM agenda_compromissos WHERE lead_id=? AND id=?", (ident, event["compromisso"]))
        )
        scheduled = self.client.get(f"/v1/leads/{ident}", headers=bdr).json()["retorno_em"]
        self.successful("atividade", auth=bdr, leads=[self.target(ident)], tipo="Nota", anotacao="Retorno confirmado")
        self.assertEqual(self.client.get(f"/v1/leads/{ident}", headers=bdr).json()["retorno_em"], scheduled)
        self.successful(
            "status",
            auth=bdr,
            leads=[self.target(ident)],
            etapa=estados.PERDIDO,
            justificativa="Empresa recusou a oferta",
            motivo="Outro",
        )
        self.assertEqual(self.client.get(f"/v1/leads/{ident}", headers=bdr).json()["etapa"], estados.PERDIDO)

    def test_ai_failure_rolls_back_all_service_writes(self):
        search = self.search()
        cnpj = search["items"][0]["cnpj"]
        self.successful("importar", campanha=search["id"], cnpjs=[cnpj])
        lead = self.query("SELECT id,versao FROM leads WHERE cnpj=?", (cnpj,))[0]
        before = self.path.read_bytes()
        with patch("ia.agentes.risco", side_effect=ValueError("Falha de teste após abrir o tratamento")):
            self.assertEqual(self.command("processar", leads=[lead]).status_code, 422)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.target(lead["id"]), lead)
        self.assertFalse(self.query("SELECT * FROM tratamentos WHERE lead_id=?", (lead["id"],)))

    def test_discard_requires_a_reason(self):
        lead = self.lead()
        fields = {"leads": [lead], "etapa": estados.DESCARTADO, "justificativa": "Empresa sem aderência"}
        self.assertEqual(self.command("status", **fields).status_code, 422)
        self.successful("status", **fields, motivo="Sem fit")
        entries = self.query(
            "SELECT para,motivo,detalhe FROM etapas_historico WHERE lead_id=? ORDER BY id DESC LIMIT 1", (lead["id"],)
        )
        self.assertEqual(
            entries, [{"para": estados.DESCARTADO, "motivo": "Sem fit", "detalhe": fields["justificativa"]}]
        )

    def test_capture_to_won_through_executive_and_agenda(self):
        from banco.conexao import reutilizar_transacao
        from nucleo import lgpd

        search = self.search()
        cnpjs = [item["cnpj"] for item in search["items"]]
        self.successful("importar", campanha=search["id"], cnpjs=cnpjs)
        leads = self.query(
            "SELECT id,versao FROM leads WHERE id IN (SELECT lead_id FROM buscas_leads WHERE busca_id=?)",
            (search["id"],),
        )
        self.successful("processar", leads=leads)
        eligible = self.query(
            """SELECT l.id,l.etapa FROM leads l JOIN buscas_leads b ON b.lead_id=l.id WHERE b.busca_id=?
            AND l.etapa IN (?,?,?) ORDER BY l.id""",
            (search["id"], estados.REVISAO, estados.NUTRICAO, estados.FILA_BDR),
        )
        self.assertTrue(eligible, self.query("SELECT etapa, COUNT(*) AS n FROM leads WHERE id > 100 GROUP BY etapa"))
        ident = eligible[0]["id"]
        if eligible[0]["etapa"] == estados.REVISAO:
            self.successful(
                "revisar",
                leads=[self.target(ident)],
                decisao="ajustar",
                classificacao="Quente",
                motivo="Revisão do prospect fictício",
            )
        self.successful("triagem", leads=[self.target(ident)], bdr=2, motivo="Encaminhamento de homologação")
        bdr = self.login("bdr.ana")
        executive = self.login("executivo")
        self.assertEqual(
            self.command(
                "atividade", auth=bdr, leads=[self.target(ident)], tipo="Ligação", resultado="Interessado"
            ).status_code,
            422,
        )
        self.assertEqual(self.client.get(f"/v1/crm/{ident}", headers=executive).status_code, 404)
        blocked = self.client.post(
            "/v1/assistente", headers=bdr, json={"lead_id": ident, "pergunta": "Escreva um WhatsApp"}
        ).json()
        self.assertIn("bloqueado", blocked["texto"])
        # A homologação da base legal usa o serviço existente em SQLite isolado.
        with closing(sqlite3.connect(self.path)) as con, con:
            con.row_factory = sqlite3.Row
            con.execute("BEGIN IMMEDIATE")
            with reutilizar_transacao(con):
                lgpd.regularizar(ident, "gestor", "legitimo_interesse", "Justificativa fictícia documentada")
        self.successful("atividade", auth=bdr, leads=[self.target(ident)], tipo="Ligação", resultado="Interessado")
        self.successful("bant", auth=bdr, leads=[self.target(ident)], valores={"necessidade": "Avaliar fraude"})
        contextual = self.client.post(
            "/v1/assistente",
            headers=bdr,
            json={
                "lead_id": ident,
                "pergunta": "Prepare-me para a reunião",
            },
        )
        self.assertEqual(contextual.status_code, 200, contextual.text)
        self.assertIn("necessidade: preenchido", contextual.json()["texto"])
        self.assertNotIn("necessidade: Avaliar fraude", contextual.json()["texto"])
        solution = "prospeccao_qualificada"
        self.successful("oportunidade", auth=bdr, leads=[self.target(ident)], solucoes=[solution], valor=1500.50)
        with patch("ia.provedor.chamar") as external:
            self.assertEqual(
                self.successful(
                    "passagem",
                    auth=bdr,
                    leads=[self.target(ident)],
                    executivo=5,
                    inicio=tempo.daqui(dias=3),
                    solucoes=[solution],
                )["etapa"],
                estados.REUNIAO,
            )
            external.assert_not_called()
        appointment = next(
            item
            for item in self.client.get(f"/v1/agenda?lead_id={ident}", headers=executive).json()["items"]
            if item["tipo"] == "Reunião confirmada"
        )
        key = appointment["id"]
        self.assertEqual(
            self.command(
                "agenda-resolver", auth=bdr, leads=[self.target(ident)], compromisso=key, status="Concluído"
            ).status_code,
            404,
        )
        new_date = tempo.daqui(dias=4)
        self.successful(
            "agenda-reagendar", auth=executive, leads=[self.target(ident)], compromisso=key, inicio=new_date
        )
        self.assertEqual(
            self.query("SELECT inicio_em FROM agenda_compromissos WHERE id=?", (key,))[0]["inicio_em"], new_date
        )
        self.successful(
            "agenda-resolver", auth=executive, leads=[self.target(ident)], compromisso=key, status="Concluído"
        )
        self.assertEqual(
            self.command(
                "crm-status",
                auth=bdr,
                leads=[self.target(ident)],
                etapa=estados.PROPOSTA,
                justificativa="Proposta registrada pelo executivo",
            ).status_code,
            422,
        )
        self.successful(
            "crm-status",
            auth=executive,
            leads=[self.target(ident)],
            etapa=estados.PROPOSTA,
            justificativa="Proposta enviada",
        )
        self.successful(
            "crm-status",
            auth=executive,
            leads=[self.target(ident)],
            etapa=estados.GANHO,
            justificativa="Aceite registrado",
        )
        with TestClient(create_app(self.path, write_enabled=True)) as reopened:
            headers = self.login("executivo", reopened)
            detail = reopened.get(f"/v1/crm/{ident}", headers=headers)
            self.assertEqual(detail.status_code, 200, detail.text)
            self.assertEqual(detail.json()["oportunidade"]["valor_mensal"], 1500.50)
            self.assertTrue(any(item["fase"] == "Captura" for item in detail.json()["historico"]))
            self.assertTrue(any(item["fase"] == "Aprendizado" for item in detail.json()["historico"]))
            analytics = reopened.get(f"/v1/analytics?dias=0&campaign_id={search['id']}", headers=headers)
            self.assertEqual(analytics.status_code, 200, analytics.text)
            self.assertEqual(analytics.json()["receita"]["ganha"], 1500.50)
            self.assertEqual(analytics.json()["funil"][-1]["leads"], 1)
        self.assertTrue(self.query("SELECT resultado FROM rotulos_treino WHERE lead_id=? AND resultado=1", (ident,)))

    def test_crm_analytics_assistant_and_agenda_stay_inside_scope(self):
        bdr = self.login("bdr.ana")
        context = self.lead(owner=3)
        ident = context["id"]
        for endpoint in ("crm", "analytics", "agenda"):
            self.assertEqual(self.client.get("/v1/" + endpoint).status_code, 401)
            response = self.client.get("/v1/" + endpoint, headers=bdr)
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get(f"/v1/crm/{ident}", headers=bdr).status_code, 404)
        executive = self.login("executivo")
        unassigned = self.query(
            "SELECT id,versao FROM leads WHERE executivo_id IS NULL AND opt_out=0 AND etapa=? LIMIT 1",
            (estados.EM_CONTATO,),
        )[0]
        self.assertEqual(
            self.command(
                "oportunidade", auth=executive, leads=[unassigned], solucoes=["prospeccao_qualificada"]
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/v1/assistente", headers=bdr, json={"lead_id": ident, "pergunta": "Histórico"}
            ).status_code,
            404,
        )
        with patch("ia.provedor.chamar") as external:
            answer = self.client.post("/v1/assistente", headers=bdr, json={"pergunta": "Quais são os gargalos?"})
            self.assertEqual(answer.status_code, 200, answer.text)
            self.assertIn("carteira", answer.json())
            external.assert_not_called()
        before = self.query("SELECT COUNT(*) AS n FROM leads WHERE responsavel_id=2 AND opt_out=0")[0]["n"]
        stats = self.client.get("/v1/analytics?dias=0", headers=bdr).json()
        self.assertEqual(stats["funil"][0]["leads"], before)
        empty = self.client.get("/v1/analytics?campaign_id=99999", headers=bdr).json()
        self.assertEqual(empty["receita"]["prevista"], 0.0)
        self.assertEqual(empty["funil"][0]["leads"], 0)

    def test_agenda_reschedule_conflict_and_crm_loss_reason(self):
        lead = self.query(
            "SELECT id,versao FROM leads WHERE etapa=? AND opt_out=0 AND executivo_id IS NOT NULL LIMIT 1",
            (estados.REUNIAO,),
        )[0]
        ident = lead["id"]
        executive = self.login("executivo")
        first = self.successful(
            "agenda-criar",
            auth=executive,
            leads=[lead],
            tipo="Reunião planejada",
            titulo="Revisar oportunidade",
            inicio=tempo.daqui(dias=5),
        )["compromisso"]
        other_time = tempo.daqui(dias=6)
        self.successful(
            "agenda-criar",
            auth=executive,
            leads=[self.target(ident)],
            tipo="Reunião planejada",
            titulo="Validar proposta mensal",
            inicio=other_time,
        )
        snapshot = self.target(ident)
        self.assertEqual(
            self.command(
                "agenda-reagendar", auth=executive, leads=[snapshot], compromisso=first, inicio=other_time
            ).status_code,
            422,
        )
        self.assertEqual(self.target(ident), snapshot)
        self.assertEqual(
            self.command(
                "crm-status",
                auth=executive,
                leads=[snapshot],
                etapa=estados.PERDIDO,
                justificativa="Encerrando a proposta",
            ).status_code,
            422,
        )
        self.successful(
            "crm-status",
            auth=executive,
            leads=[snapshot],
            etapa=estados.PERDIDO,
            justificativa="Encerrando a proposta",
            motivo="Sem orçamento",
        )
        self.assertEqual(self.query("SELECT etapa FROM leads WHERE id=?", (ident,))[0]["etapa"], estados.PERDIDO)
