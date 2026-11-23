"""Regressões: 50 CNPJs reais, falha Gemini, descarte indevido e pré-funil."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from banco import consultas, repositorio
from banco.conexao import conectar
from dados import ingestao, limpeza
from ia import nota, observabilidade, orquestrador, provedor
from nucleo import estados

ROOT = Path(__file__).resolve().parent.parent


def _real(nome="SUPERMERCADO TESTE LTDA", cnpj="11222333000181") -> int:
    return ingestao.receber(
        [
            {
                "cnpj": cnpj,
                "razao_social": nome,
                "cidade": "Campinas",
                "uf": "SP",
                "cnae": "4712100",
                "setor": "Comércio varejista",
                "data_abertura": "14/04/2026",
                "origem": "cnpja",
                "base_legal": "sem_base",
            }
        ],
        "cnpja",
        "teste",
    ).criados[0]


def test_politica_conserva_nota_e_revisa_cnpj_real():
    etapa, motivo, explicacao = nota.preservar_cnpj_publico(
        estados.DESCARTADO,
        "Sem fit",
        "Nota baixa",
        origem="cnpja",
        base_ficticia=False,
        opt_out=False,
        nota_final=21.0,
        motor="local",
    )
    assert etapa == estados.REVISAO and motivo is None
    assert "nota 21" in explicacao
    assert "revisão" in explicacao.lower()
    etapa_ficticia = nota.preservar_cnpj_publico(
        estados.DESCARTADO,
        "Sem fit",
        "Nota baixa",
        origem="base_ficticia",
        base_ficticia=True,
        opt_out=False,
        nota_final=21,
        motor="local",
    )
    assert etapa_ficticia[0] == estados.DESCARTADO
    etapa_opt_out = nota.preservar_cnpj_publico(
        estados.DESCARTADO,
        "Sem fit",
        "Nota baixa",
        origem="cnpja",
        base_ficticia=False,
        opt_out=True,
        nota_final=21,
        motor="local",
    )
    assert etapa_opt_out[0] == estados.DESCARTADO


def test_sem_evidencia_real_resulta_revisao_sem_apagar_score(base_carregada):
    lead_id = _real()
    resumo = orquestrador.tratar([lead_id], "gestor", usar_llm=False)
    assert resumo["total"] == 1
    lead = consultas.lead(lead_id)
    assert lead["etapa"] != estados.DESCARTADO
    assert lead["nota_final"] is not None
    trat = consultas.ultimo_tratamento(lead_id)
    assert trat is not None
    assert trat["nota_final"] == lead["nota_final"]
    assert trat["destino"] == lead["etapa"]


def test_erro_sistemico_gemini_nao_repete_chamadas_e_conserva_leads(base_carregada, monkeypatch):
    ids = [
        _real(f"MERCADO TESTE {i} LTDA", "") for i in range(6)
    ]
    chamadas = []
    monkeypatch.setattr(provedor, "disponivel", lambda: True)

    def falhar(*args, **kwargs):
        chamadas.append(1)
        raise provedor.ErroIA("Limite de uso do Gemini atingido.")

    monkeypatch.setattr(provedor, "chamar", falhar)
    resumo = orquestrador.tratar(ids, "gestor", usar_llm=True)
    assert len(chamadas) == 1
    assert resumo["total"] == len(ids)
    assert resumo["planos_b"] == len(ids)
    assert resumo["usados_gemini"] == 0
    assert "Limite" in resumo["falha_gemini"]
    for lead_id in ids:
        lead = consultas.lead(lead_id)
        assert lead["etapa"] != estados.DESCARTADO
        assert consultas.ultimo_tratamento(lead_id)["plano_b"] == 1
    falhas = observabilidade.falhas_lote(resumo["lote"])
    assert len(falhas) == 1
    assert "Limite de uso" in falhas[0]["erro"]


def test_migracao_resgata_so_descartes_plano_b_automaticos(base_carregada):
    principal = _real()
    manual = _real("MERCADO DE TESTE HUMANO LTDA", "66285492000117")
    opt_out = _real("MERCADO OPT OUT LTDA", "")
    orquestrador.tratar([principal, manual, opt_out], "gestor", usar_llm=False)

    with conectar() as con:
        for lead_id, ator, opt in [
            (principal, "agente_supervisor", 0),
            (manual, "gestor", 0),
            (opt_out, "agente_supervisor", 1),
        ]:
            con.execute(
                "UPDATE leads SET etapa=?,opt_out=? WHERE id=?",
                (estados.DESCARTADO, opt, lead_id),
            )
            con.execute(
                "UPDATE tratamentos SET plano_b=1,destino=? WHERE lead_id=?",
                (estados.DESCARTADO, lead_id),
            )
            con.execute(
                "INSERT INTO etapas_historico (lead_id,de,para,ator,registrado_em) VALUES (?,?,?,?,?)",
                (lead_id, estados.REVISAO, estados.DESCARTADO, ator, "2026-11-23T12:00:00Z"),
            )

    arquivo = ROOT / "banco" / "migracoes" / "005_recuperar_descartes_plano_b.sql"
    with conectar() as con:
        con.executescript(arquivo.read_text(encoding="utf-8"))
    assert consultas.lead(principal)["etapa"] == estados.REVISAO
    assert consultas.lead(manual)["etapa"] == estados.DESCARTADO
    assert consultas.lead(opt_out)["etapa"] == estados.DESCARTADO
    assert "migracao_plano_b_005" in [
        h["ator"] for h in consultas.historico_etapas(principal)
    ]


def test_base_de_contato_pendente_nao_aparece_como_problema(base_carregada):
    reg, problemas = limpeza.padronizar(
        {"razao_social": "Empresa CNPJ Real", "cnpj": "11222333000181"}
    )
    assert reg["base_legal"] == "sem_base"
    assert "Sem consentimento nem base legal" not in problemas
    lead_id = _real()
    entrada = next(x for x in ingestao.entrada_recente() if x["lead_id"] == lead_id)
    assert entrada["contato_status"] == "Base de contato pendente"
    assert entrada["problemas"] == ""


def test_crm_exibe_pre_funil_de_cnpjs_reais(base_carregada):
    lead_id = _real()
    orquestrador.tratar([lead_id], "gestor", usar_llm=False)
    gestor = repositorio.usuarios("gestor")[0]
    app = AppTest.from_file(str(ROOT / "paginas" / "crm_funil.py"), default_timeout=30)
    app.session_state["usuario"] = {
        k: gestor[k] for k in ("id", "login", "nome", "papel")
    }
    app.run()
    assert not app.exception, [str(x.message) for x in app.exception]
    assert any("Pré-funil" in str(m.value) for m in app.markdown)
