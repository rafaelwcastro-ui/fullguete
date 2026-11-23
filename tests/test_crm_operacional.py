"""Regressões dos filtros e do funil quando o cadastro está incompleto."""

from __future__ import annotations

import math

import pandas as pd

from banco import consultas, repositorio
from dados import cenario_demo
from nucleo import comercial, crm_operacional, estados


def test_menu_solucao_aceita_nan_none_e_tipos_mistos():
    valores = ["Prospecção Qualificada", float("nan"), None, "", 12, " Antifraude ", "antifraude"]
    assert crm_operacional.opcoes_solucoes(valores) == [
        "Antifraude", "antifraude", "Prospecção Qualificada"
    ]
    assert crm_operacional.nome_solucao(None) == ""
    assert crm_operacional.nome_solucao(float("nan")) == ""
    assert crm_operacional.nome_solucao("") == ""


def test_valores_opcionais_nao_quebram_kpis():
    assert crm_operacional.valor_seguro(None) == 0
    assert crm_operacional.valor_seguro(math.nan) == 0
    assert crm_operacional.valor_seguro("nan") == 0
    assert crm_operacional.valor_seguro("invalid") == 0
    assert crm_operacional.valor_seguro(-100) == 0
    assert crm_operacional.valor_seguro("1500.50") == 1500.5


def test_filtrar_crm_pesquisa_cnpj_nome_etapa_e_responsavel():
    dados = pd.DataFrame(
        [
            {
                "id": 1,
                "empresa": "Mercado Campinas",
                "razao_social": "MERCADO CAMPINAS LTDA",
                "cnpj": "11222333000181",
                "etapa": estados.EM_CONTATO,
                "responsavel": "Ana",
                "base_ficticia": 0,
                "valor": None,
            },
            {
                "id": 2,
                "empresa": "Fictícia Comércio",
                "razao_social": "Fictícia Comércio LTDA",
                "cnpj": None,
                "etapa": estados.GANHO,
                "responsavel": None,
                "base_ficticia": 1,
                "valor": 2500,
            },
        ]
    )
    assert crm_operacional.filtrar_crm(dados, termo="11222333000181")["id"].tolist() == [1]
    assert crm_operacional.filtrar_crm(dados, termo="campinas")["id"].tolist() == [1]
    assert crm_operacional.filtrar_crm(dados, etapas=[estados.EM_CONTATO])["id"].tolist() == [1]
    assert crm_operacional.filtrar_crm(dados, responsavel="Ana")["id"].tolist() == [1]
    assert crm_operacional.filtrar_crm(dados, somente_reais=True)["id"].tolist() == [1]
    assert crm_operacional.resumo_crm(dados) == {
        "leads": 2,
        "reais": 1,
        "ficticios": 1,
        "valor_mensal": 2500.0,
    }


def test_funil_real_tem_acoes_que_gravam_atividade_e_movem_etapa(base_carregada):
    cenario_demo.montar()
    candidato = consultas.leads([estados.EM_CONTATO]).iloc[0]
    lead_id = int(candidato["id"])
    gestor = repositorio.usuarios("gestor")[0]
    comercial.registrar_atividade(
        lead_id, gestor, "Nota", "", "Próximo passo validado pelo CRM", "Enviar proposta"
    )
    assert consultas.lead(lead_id)["proxima_acao"] == "Enviar proposta"
    assert consultas.atividades(lead_id)[0]["anotacao"] == "Próximo passo validado pelo CRM"
    comercial.mover_no_funil(lead_id, gestor, estados.QUALIFICADO)
    assert consultas.lead(lead_id)["etapa"] == estados.QUALIFICADO
    assert consultas.historico_etapas(lead_id)[-1]["para"] == estados.QUALIFICADO
