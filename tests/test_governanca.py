"""Fase 6: LGPD (opt-out, titular, retenção), drift, assistente e grafo editável."""

from __future__ import annotations

import pytest

from banco import consultas, repositorio
from banco.conexao import conectar
from dados import ingestao
from ia import assistente, drift, orquestrador
from nucleo import comercial, estados, lgpd


def _lead_na_fila() -> int:
    reg = {"razao_social": "Fictícia Atacadista LGPD", "cnae": "4639701", "porte": "Média", "interesse": "Crédito",
           "descricao": "Vende para outras empresas com boleto a prazo e sofre com inadimplência.",
           "consentimento": "sim", "origem": "indicacao", "contato_nome": "Titular Teste",
           "email": "titular@teste.exemplo"}  # fmt: skip
    lead_id = ingestao.receber([reg], "formulario", "teste").criados[0]
    orquestrador.tratar([lead_id], "teste", usar_llm=False)
    assert consultas.lead(lead_id)["etapa"] == estados.FILA_BDR
    return lead_id


def test_opt_out_tira_da_fila_e_bloqueia(base_carregada):
    lead_id = _lead_na_fila()
    etapa = lgpd.registrar_opt_out(lead_id, "gestor", "Pedido por e-mail")
    assert etapa == estados.DESCARTADO
    lead = consultas.lead(lead_id)
    assert lead["opt_out"] == 1
    assert consultas.carteira()[lambda d: d["etapa"] == estados.FILA_BDR].empty
    bdr = repositorio.usuarios("bdr")[0]
    with pytest.raises(ValueError, match="opt-out"):
        comercial.registrar_atividade(lead_id, bdr, "Ligação", "Sem resposta", "x")
    with pytest.raises(estados.TransicaoInvalida), conectar() as con:
        estados.mudar(con, lead_id, estados.EM_TRATAMENTO, "teste")
        estados.mudar(con, lead_id, estados.TRATADO, "teste")
        estados.mudar(con, lead_id, estados.FILA_BDR, "teste")


def test_exportar_e_excluir_titular(base_carregada):
    lead_id = _lead_na_fila()
    assert lgpd.buscar_titular("titular@teste")[0]["lead_id"] == lead_id
    assert "titular@teste.exemplo" in lgpd.exportar_titular(lead_id, "gestor")
    lgpd.excluir_titular(lead_id, "gestor")
    assert consultas.contato(lead_id) is None
    assert consultas.lead(lead_id)["opt_out"] == 1
    assert not consultas.auditoria(str(lead_id))[lambda d: d["acao"] == "exclusao_titular"].empty


def test_regularizar_base_de_contato_sem_reter_e_sem_reprocessar(base_carregada):
    reg = {
        "razao_social": "Fictícia Sem Base",
        "descricao": "Vende a prazo para empresas com boleto.",
        "cnae": "4639701",
    }
    lead_id = ingestao.receber([reg], "formulario", "teste").criados[0]
    orquestrador.tratar([lead_id], "teste", usar_llm=False)
    antes = consultas.lead(lead_id)
    assert antes["etapa"] != estados.RETIDO
    assert lgpd.status_contato(lead_id) == "pendente"
    with pytest.raises(ValueError):
        lgpd.regularizar(lead_id, "gestor", "consentimento", "")
    lgpd.regularizar(lead_id, "gestor", "legitimo_interesse", "Finalidade e balanceamento documentados")
    assert lgpd.status_contato(lead_id) == "liberado"
    depois = consultas.lead(lead_id)
    assert depois["etapa"] == antes["etapa"]
    assert depois["nota_final"] == antes["nota_final"]


def test_psi():
    igual = drift.psi(list(range(100)), list(range(100)))
    diferente = drift.psi(list(range(100)), [x + 60 for x in range(100)])
    assert igual < 0.01 < 0.2 < diferente


def test_assistente_local_usa_o_catalogo(base_carregada):
    r = assistente.responder("Qual solução Equifax resolve chargeback?")
    assert r["motor"] == "local" and "Kount Gestão de Chargeback" in r["texto"]
    lead_id = _lead_na_fila()
    responsavel_id = consultas.lead(lead_id)["responsavel_id"]
    bdr = next(u for u in repositorio.usuarios("bdr") if u["id"] == responsavel_id)
    prep = assistente.responder("Prepare-me para a reunião", lead_id, usuario=bdr)
    assert "Reunião com" in prep["texto"] and "titular@teste.exemplo" not in prep["texto"]
