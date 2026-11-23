"""Regressão: cadastrar/qualificar CNPJ público não equivale a autorizar abordagem."""

from __future__ import annotations

from pathlib import Path

import pytest

from banco import consultas, repositorio
from banco.conexao import conectar
from dados import ingestao
from ia import orquestrador
from nucleo import comercial, estados, lgpd


def capturar(cnpj="11222333000181") -> int:
    return ingestao.receber(
        [
            {
                "cnpj": cnpj,
                "razao_social": "Empresa teste de prospecção Ltda",
                "cnae": "4639701",
                "setor": "Distribuição",
                "cidade": "Campinas",
                "uf": "SP",
                "descricao": "Atacado de produtos para o comércio.",
                "base_legal": "sem_base",
            }
        ],
        "cnpja",
        "teste",
    ).criados[0]


def test_novo_cnpj_pode_ser_analisado_e_anotado_sem_base_contato(base_carregada):
    lead_id = capturar()
    gestor = repositorio.usuarios("gestor")[0]
    assert lgpd.status_contato(lead_id) == "pendente"
    resumo = orquestrador.tratar([lead_id], "gestor", usar_llm=False)
    assert resumo["total"] == 1
    assert consultas.lead(lead_id)["etapa"] != estados.RETIDO
    assert consultas.ultimo_tratamento(lead_id)["resultado"] is not None
    assert not consultas.cadencia(lead_id)
    etapa = comercial.registrar_atividade(lead_id, gestor, "Nota", "", "Hipótese comercial a investigar.")
    assert etapa == consultas.lead(lead_id)["etapa"]
    with pytest.raises(ValueError, match="Contato pendente de base legal"):
        comercial.registrar_atividade(lead_id, gestor, "Ligação", "Sem resposta", "")
    assert consultas.lead(lead_id)["primeiro_contato_em"] is None


def test_base_documentada_libera_contato_sem_retirar_score(base_carregada):
    lead_id = capturar()
    gestor = repositorio.usuarios("gestor")[0]
    orquestrador.tratar([lead_id], "gestor", usar_llm=False)
    anterior = consultas.lead(lead_id)
    lgpd.regularizar(
        lead_id,
        gestor["login"],
        "legitimo_interesse",
        "Finalidade comercial específica; necessidade, balanceamento e salvaguardas documentados.",
    )
    assert lgpd.status_contato(lead_id) == "liberado"
    assert consultas.lead(lead_id)["nota_final"] == anterior["nota_final"]
    assert consultas.lead(lead_id)["etapa"] == anterior["etapa"]
    etapa = comercial.registrar_atividade(lead_id, gestor, "Ligação", "Sem resposta", "Contato realizado.")
    assert etapa != estados.RETIDO
    assert consultas.lead(lead_id)["primeiro_contato_em"] is not None


def test_optout_continua_bloqueando_ia_e_contatos(base_carregada):
    lead_id = capturar()
    gestor = repositorio.usuarios("gestor")[0]
    with conectar() as con:
        con.execute("UPDATE leads SET opt_out=1 WHERE id=?", (lead_id,))
    assert lgpd.status_contato(lead_id) == "opt_out"
    orquestrador.tratar([lead_id], "gestor", usar_llm=False)
    assert consultas.lead(lead_id)["etapa"] == estados.RETIDO
    with pytest.raises(ValueError, match="opt-out"):
        comercial.registrar_atividade(lead_id, gestor, "Nota", "", "Teste.")
    with pytest.raises(ValueError, match="opt-out"):
        lgpd.regularizar(lead_id, gestor["login"], "legitimo_interesse", "Justificativa")


def test_migracao_resgata_apenas_bloqueio_antigo_sem_optout(base_carregada):
    disponivel = capturar()
    bloqueado = capturar("66285492000117")
    with conectar() as con:
        for lead_id, bloqueio in ((disponivel, False), (bloqueado, True)):
            con.execute("UPDATE leads SET etapa=?, opt_out=? WHERE id=?", (estados.RETIDO, int(bloqueio), lead_id))
            con.execute(
                """INSERT INTO tratamentos
                   (lead_id, lote, iniciado_em, motor, destino, decomposicao)
                   VALUES (?,?,?,?,?,?)""",
                (
                    lead_id,
                    "legado",
                    "2026-11-20T12:00:00Z",
                    "local",
                    estados.RETIDO,
                    '{"bloqueio":"Sem base legal válida para contato."}',
                ),
            )
    sql = Path(__file__).resolve().parent.parent / "banco" / "migracoes" / "004_separar_analise_contato.sql"
    with conectar() as con:
        con.executescript(sql.read_text(encoding="utf-8"))
    assert consultas.lead(disponivel)["etapa"] == estados.CAPTURADO
    assert consultas.lead(bloqueado)["etapa"] == estados.RETIDO
    assert lgpd.status_contato(disponivel) == "pendente"
    assert [r["para"] for r in consultas.historico_etapas(disponivel)][-1] == estados.CAPTURADO


def test_cadastro_publico_nao_preenche_base_legal_automaticamente(base_carregada):
    lead_id = capturar()
    with conectar() as con:
        c = con.execute(
            "SELECT base_legal FROM consentimentos WHERE lead_id=? ORDER BY id DESC LIMIT 1",
            (lead_id,),
        ).fetchone()
        assert c["base_legal"] == "sem_base"
        assert not lgpd.base_para_contato(con, lead_id)
