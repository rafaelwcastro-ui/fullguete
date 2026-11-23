"""O BANT é incremental e separa hipóteses IA de fatos confirmados pelo BDR."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from banco import consultas, repositorio
from dados import ingestao
from ia import orquestrador
from nucleo import comercial, estados, gestao_leads


def _lead(base_carregada):
    reg = {
        "razao_social": "Distribuidora Teste BANT Ltda",
        "cnae": "4639701",
        "porte": "Média",
        "interesse": "Crédito",
        "descricao": "Distribuidora de mercadorias que vende a prazo.",
        "consentimento": "sim",
        "origem": "indicacao",
    }
    lead_id = ingestao.receber([reg], "formulario", "teste").criados[0]
    orquestrador.tratar([lead_id], "teste", usar_llm=False)
    lead = consultas.lead(lead_id)
    assert lead["etapa"] == estados.FILA_BDR
    bdr = next(u for u in repositorio.usuarios("bdr") if u["id"] == lead["responsavel_id"])
    return lead_id, bdr


def test_salvar_so_um_criterio_nao_exige_outros_tres(base_carregada):
    lead_id, bdr = _lead(base_carregada)
    comercial.salvar_bant(lead_id, bdr, {"orcamento": "Ainda não definido"})
    bant = consultas.bant(lead_id)
    assert bant["orcamento"] == "Ainda não definido"
    assert bant["autoridade"] == ""
    assert bant["necessidade"] == ""
    assert bant["prazo"] == ""
    assert not consultas.bant_validacoes(lead_id).get("orcamento", False)


def test_salvamento_incremental_nao_apaga_campo_confirmado(base_carregada):
    lead_id, bdr = _lead(base_carregada)
    comercial.salvar_bant(
        lead_id, bdr, {"autoridade": "Gerente financeiro"}, {"autoridade": True}
    )
    comercial.salvar_bant(lead_id, bdr, {"necessidade": "Analisar risco dos compradores"})
    bant = consultas.bant(lead_id)
    validacoes = consultas.bant_validacoes(lead_id)
    assert bant["autoridade"] == "Gerente financeiro"
    assert bant["necessidade"] == "Analisar risco dos compradores"
    assert validacoes["autoridade"] is True
    assert validacoes.get("necessidade") is False


def test_alterar_criterio_invalida_confirmacao_anterior(base_carregada):
    lead_id, bdr = _lead(base_carregada)
    comercial.salvar_bant(lead_id, bdr, {"prazo": "30 dias"}, {"prazo": True})
    comercial.salvar_bant(lead_id, bdr, {"prazo": "60 dias"})
    assert consultas.bant(lead_id)["prazo"] == "60 dias"
    assert consultas.bant_validacoes(lead_id)["prazo"] is False


def test_proibir_confirmacao_sem_conteudo_sem_apagar_bant(base_carregada):
    lead_id, bdr = _lead(base_carregada)
    comercial.salvar_bant(lead_id, bdr, {"orcamento": "Em avaliação"})
    with pytest.raises(ValueError, match="Necessidade"):
        comercial.salvar_bant(lead_id, bdr, {"necessidade": ""}, {"necessidade": True})
    assert consultas.bant(lead_id)["orcamento"] == "Em avaliação"
    assert consultas.bant(lead_id)["necessidade"] == ""


def test_bdr_pode_trabalhar_lead_antes_de_completar_bant(base_carregada):
    lead_id, bdr = _lead(base_carregada)
    assert gestao_leads.mudar_status(
        lead_id, bdr, estados.EM_ANALISE, "Preparação comercial sem BANT completo"
    ) == estados.EM_ANALISE
    assert consultas.bant(lead_id) is None
    comercial.registrar_atividade(lead_id, bdr, "Nota", "", "Investigar necessidade")
    assert consultas.lead(lead_id)["etapa"] == estados.EM_ANALISE


def test_tela_bdr_exibe_bant_progressivo_sem_exigir_quatro_campos(base_carregada):
    _lead(base_carregada)
    bdr = repositorio.usuarios("bdr")[0]
    from pathlib import Path

    caminho = Path(__file__).resolve().parent.parent / "paginas" / "fila_bdr.py"
    app = AppTest.from_file(str(caminho), default_timeout=30)
    app.session_state["usuario"] = {k: bdr[k] for k in ("id", "login", "nome", "papel")}
    app.run()
    assert not app.exception, [str(x.message) for x in app.exception]
    assert any("BANT" in tab.label for tab in app.tabs)
