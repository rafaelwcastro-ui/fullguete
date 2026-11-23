"""Assistente contextual: histórico comercial restrito, sem contato pessoal no prompt."""

from __future__ import annotations

import pytest

from banco import repositorio
from banco.conexao import conectar
from dados import ingestao
from ia import assistente, provedor


@pytest.fixture
def lead_com_historico(base_carregada):
    lead_id = ingestao.receber(
        [
            {
                "razao_social": "Distribuidora Fictícia Contexto",
                "consentimento": "sim",
                "interesse": "Crédito",
                "contato_nome": "Pessoa Sigilosa",
                "email": "pessoa@exemplo.invalid",
                "origem": "formulario",
            }
        ],
        "formulario",
        "teste",
    ).criados[0]
    bdrs = repositorio.usuarios("bdr")
    bdr = bdrs[0]
    with conectar() as con:
        con.execute("UPDATE leads SET responsavel_id=?, base_ficticia=1 WHERE id=?", (bdr["id"], lead_id))
        con.execute(
            "INSERT INTO atividades (lead_id, usuario_id, registrada_em, tipo, resultado, anotacao) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                lead_id,
                bdr["id"],
                "2026-11-23T12:00:00",
                "Ligação",
                "Interessado",
                "Pessoa Sigilosa respondeu pelo e-mail pessoa@exemplo.invalid.",
            ),
        )
        con.execute(
            "INSERT INTO oportunidades (lead_id, solucoes, valor_mensal, criada_em, atualizada_em) "
            "VALUES (?, ?, ?, ?, ?)",
            (lead_id, '["relatorio_credito_pj"]', 2500.0, "2026-11-23T12:00:00", "2026-11-23T12:00:00"),
        )
    return lead_id, bdr, bdrs[1]


def test_contexto_autorizado_contem_historico_sem_contato(lead_com_historico):
    lead_id, bdr, _ = lead_com_historico
    ctx = assistente.contexto_lead(lead_id, bdr)
    assert ctx["atividades_recentes"][0]["resultado"] == "Interessado"
    assert ctx["oportunidade"]["valor_mensal_estimado"] == 2500.0
    assert ctx["origem_demonstrativa"] is True
    assert "Pessoa Sigilosa" not in str(ctx)
    assert "pessoa@exemplo.invalid" not in str(ctx)


def test_bdr_de_outro_responsavel_nao_consulta_lead(lead_com_historico):
    lead_id, _, outro_bdr = lead_com_historico
    with pytest.raises(PermissionError):
        assistente.contexto_lead(lead_id, outro_bdr)
    with pytest.raises(PermissionError):
        assistente.responder("Histórico do lead", lead_id, usuario=outro_bdr)
    with pytest.raises(PermissionError):
        assistente.contexto_lead(lead_id)


def test_resposta_local_consulta_atividades_reais(lead_com_historico, monkeypatch):
    lead_id, bdr, _ = lead_com_historico
    monkeypatch.setattr(provedor, "disponivel", lambda: False)
    resposta = assistente.responder("Qual o histórico de atividades?", lead_id, usuario=bdr)
    assert resposta["motor"] == "local"
    assert "Ligação" in resposta["texto"] and "Interessado" in resposta["texto"]
    assert "Pessoa Sigilosa" not in resposta["texto"]


def test_chats_separados_por_usuario_e_empresa():
    assert assistente.chave_conversa(1, 10) != assistente.chave_conversa(1, 11)
    assert assistente.chave_conversa(1, 10) != assistente.chave_conversa(2, 10)
    assert assistente.chave_conversa(1, None) != assistente.chave_conversa(1, 10)
