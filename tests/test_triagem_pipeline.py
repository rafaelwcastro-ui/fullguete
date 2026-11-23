"""Regressão de leads reais que eram tratados, mas não apareciam na Fila do BDR."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from banco import consultas, repositorio
from banco.conexao import conectar
from dados import ingestao
from ia import orquestrador
from nucleo import estados, lgpd, triagem

ROOT = Path(__file__).resolve().parent.parent


def importar_real(cnpj="11222333000181") -> int:
    return ingestao.receber(
        [
            {
                "cnpj": cnpj,
                "razao_social": "MERCEARIA CAMPINAS LTDA",
                "nome_fantasia": "Mercearia Campinas",
                "cnae": "4712100",
                "setor": "Comércio varejista de alimentos",
                "cidade": "Campinas",
                "uf": "SP",
                "data_abertura": "14/04/2026",
                "base_legal": "sem_base",
            }
        ],
        "cnpja",
        "teste",
    ).criados[0]


def preparar_para_triagem(base_carregada, etapa=estados.NUTRICAO) -> tuple[int, dict]:
    lead_id = importar_real()
    orquestrador.tratar([lead_id], "teste", usar_llm=False)
    with conectar() as con:
        con.execute("UPDATE leads SET etapa=?, responsavel_id=NULL WHERE id=?", (etapa, lead_id))
    return lead_id, repositorio.usuarios("gestor")[0]


def test_encaminha_nutricao_apos_ia_sem_inventar_base_legal(base_carregada):
    lead_id, gestor = preparar_para_triagem(base_carregada)
    bdr = repositorio.usuarios("bdr")[0]
    before = consultas.lead(lead_id)
    assert triagem.encaminhar([lead_id], gestor, bdr["id"], "Aderência comercial para avaliação humana") == 1
    after = consultas.lead(lead_id)
    assert after["etapa"] == estados.FILA_BDR
    assert after["responsavel_id"] == bdr["id"]
    assert after["nota_final"] == before["nota_final"]
    assert after["classificacao"] == before["classificacao"]
    assert lgpd.status_contato(lead_id) == "pendente"
    assert consultas.cadencia(lead_id) == []
    assert lead_id in consultas.carteira(bdr["id"])["id"].tolist()
    assert "Triagem comercial manual" in consultas.historico_etapas(lead_id)[-1]["detalhe"]
    logs = consultas.auditoria(str(lead_id))
    assert "encaminhamento_manual" in logs["acao"].tolist()


def test_eh_possivel_encaminhar_revisao_sem_forcar_score(base_carregada):
    lead_id, gestor = preparar_para_triagem(base_carregada, estados.REVISAO)
    bdr = repositorio.usuarios("bdr")[0]
    assert triagem.encaminhar([lead_id], gestor, bdr["id"], "Gestor confirmou oportunidade comercial") == 1
    assert consultas.lead(lead_id)["etapa"] == estados.FILA_BDR


def test_capturado_descartado_optout_nao_podem_pular_triagem(base_carregada):
    lead_id, gestor = preparar_para_triagem(base_carregada)
    bdr = repositorio.usuarios("bdr")[0]
    with conectar() as con:
        con.execute("UPDATE leads SET etapa=? WHERE id=?", (estados.CAPTURADO, lead_id))
    with pytest.raises(ValueError, match="precisa ser tratado"):
        triagem.encaminhar([lead_id], gestor, bdr["id"], "Pedido do gestor para prospecção")
    with conectar() as con:
        con.execute("UPDATE leads SET etapa=? WHERE id=?", (estados.DESCARTADO, lead_id))
    with pytest.raises(ValueError, match="precisa ser tratado"):
        triagem.encaminhar([lead_id], gestor, bdr["id"], "Pedido do gestor para prospecção")
    with conectar() as con:
        con.execute("UPDATE leads SET etapa=?, opt_out=1 WHERE id=?", (estados.NUTRICAO, lead_id))
    with pytest.raises(ValueError, match="opt-out"):
        triagem.encaminhar([lead_id], gestor, bdr["id"], "Pedido do gestor para prospecção")


def test_somente_gestor_pode_encaminhar_e_com_motivo(base_carregada):
    lead_id, gestor = preparar_para_triagem(base_carregada)
    bdr = repositorio.usuarios("bdr")[0]
    with pytest.raises(PermissionError):
        triagem.encaminhar([lead_id], bdr, bdr["id"], "BDR tentou encaminhar sozinho")
    with pytest.raises(ValueError, match="Justifique"):
        triagem.encaminhar([lead_id], gestor, bdr["id"], "ok")
    with pytest.raises(ValueError, match="BDR ativo"):
        triagem.encaminhar([lead_id], gestor, 999999, "Motivo suficiente para triagem")


def test_lote_eh_atomico_se_um_lead_estiver_invalido(base_carregada):
    lead_id, gestor = preparar_para_triagem(base_carregada)
    novo = importar_real("66285492000117")
    bdr = repositorio.usuarios("bdr")[0]
    with pytest.raises(ValueError, match="precisa ser tratado"):
        triagem.encaminhar([lead_id, novo], gestor, bdr["id"], "Análise de duas oportunidades diferentes")
    assert consultas.lead(lead_id)["etapa"] == estados.NUTRICAO
    assert consultas.lead(lead_id)["responsavel_id"] is None


def test_consulta_carteira_inclui_cnpj_real_e_situacao(base_carregada):
    lead_id, _ = preparar_para_triagem(base_carregada)
    d = consultas.carteira(None, incluir_sem_responsavel=True)
    assert d.loc[d["id"] == lead_id, "cnpj"].iloc[0] == "11222333000181"
    assert "nutrição" in triagem.situacao_operacional(estados.NUTRICAO).lower()
    assert "sem BDR" in triagem.situacao_operacional(estados.FILA_BDR)


def test_pagina_fila_exibe_cnpj_que_a_ia_mandou_para_nutricao(base_carregada):
    lead_id, gestor = preparar_para_triagem(base_carregada)
    app = AppTest.from_file(str(ROOT / "paginas" / "fila_bdr.py"), default_timeout=30)
    app.session_state["usuario"] = {k: gestor[k] for k in ("id", "login", "nome", "papel")}
    app.run()
    assert not app.exception, [str(x.message) for x in app.exception]
    assert any("CNPJs capturados" in str(x.value) for x in app.markdown)
    assert lead_id in consultas.carteira(None, incluir_sem_responsavel=True)["id"].tolist()


def test_carteira_seleciona_empresa_e_tem_acao_de_encaminhamento(base_carregada):
    lead_id, gestor = preparar_para_triagem(base_carregada)
    app = AppTest.from_file(str(ROOT / "paginas" / "carteira.py"), default_timeout=30)
    app.session_state["usuario"] = {k: gestor[k] for k in ("id", "login", "nome", "papel")}
    app.run()
    assert not app.exception, [str(x.message) for x in app.exception]
    assert any("Enviar este lead para a fila" in x.label for x in app.button)
