"""Fase 4 e 5: o BDR trabalha o lead até a reunião, e o funil fecha e alimenta o modelo."""

from __future__ import annotations

import pytest

from banco import consultas, repositorio
from banco.conexao import conectar
from dados import ingestao
from ia import orquestrador, propensao
from nucleo import comercial, estados, tempo


def _lead_na_fila() -> tuple[int, dict]:
    reg = {"razao_social": "Fictícia Atacadista Teste", "cnae": "4639701", "porte": "Média", "interesse": "Crédito",
           "descricao": "Distribuidora que vende para outras empresas com boleto a prazo e sofre com inadimplência.",
           "consentimento": "sim", "origem": "indicacao", "contato_nome": "Contato Teste"}  # fmt: skip
    lead_id = ingestao.receber([reg], "formulario", "teste").criados[0]
    orquestrador.tratar([lead_id], "teste", usar_llm=False)
    lead = consultas.lead(lead_id)
    assert lead["etapa"] == estados.FILA_BDR
    bdr = next(u for u in repositorio.usuarios("bdr") if u["id"] == lead["responsavel_id"])
    return lead_id, bdr


def test_bdr_trabalha_ate_a_reuniao(base_carregada):
    lead_id, bdr = _lead_na_fila()
    etapa = comercial.registrar_atividade(lead_id, bdr, "Ligação", "Falou com o decisor", "Tem dor de inadimplência.",
                                          "Enviar material", tempo.daqui(dias=1))  # fmt: skip
    assert etapa == estados.EM_CONTATO
    lead = consultas.lead(lead_id)
    assert lead["primeiro_contato_em"] and lead["proxima_acao"] == "Enviar material"
    assert [p["canal"] for p in consultas.cadencia(lead_id) if p["feito_em"]] == ["Ligação"]

    executivo = repositorio.usuarios("executivo")[0]
    with pytest.raises(ValueError, match="Necessidade"):
        comercial.qualificar_e_agendar(lead_id, bdr, tempo.daqui(dias=2), executivo["id"], ["relatorio_credito_pj"])
    comercial.salvar_bant(lead_id, bdr, {"necessidade": "Reduzir atrasos", "autoridade": "Diretor financeiro"})
    comercial.qualificar_e_agendar(lead_id, bdr, tempo.daqui(dias=2), executivo["id"], ["relatorio_credito_pj"])

    lead = consultas.lead(lead_id)
    assert lead["etapa"] == estados.REUNIAO and lead["executivo_id"] == executivo["id"]
    opp = consultas.oportunidade(lead_id)
    assert opp["solucoes"] == ["relatorio_credito_pj"]
    assert "Reduzir atrasos" in opp["resumo_passagem"]
    assert "Contato Teste" not in opp["resumo_passagem"]
    hist = [h["para"] for h in consultas.historico_etapas(lead_id)]
    assert hist[-3:] == [estados.EM_CONTATO, estados.QUALIFICADO, estados.REUNIAO]


def test_nao_qualifica_sem_primeiro_contato(base_carregada):
    lead_id, bdr = _lead_na_fila()
    with pytest.raises(ValueError, match="primeiro contato"):
        comercial.qualificar_e_agendar(lead_id, bdr, tempo.daqui(dias=2), 1, [])


def test_correcao_e_concordancia_registradas(base_carregada):
    lead_id, bdr = _lead_na_fila()
    sugerida = consultas.lead(lead_id)["solucao_principal"]
    comercial.corrigir_ia(lead_id, bdr, "solucao", sugerida, "A sugestão faz sentido.")
    comercial.corrigir_ia(lead_id, bdr, "solucao", "protesto", "Cliente falou de títulos vencidos.")
    corr = consultas.correcoes(lead_id)
    assert sorted(corr["concorda"].tolist()) == [0, 1]
    assert consultas.lead(lead_id)["solucao_principal"] == "protesto"
    with pytest.raises(ValueError):
        comercial.corrigir_ia(lead_id, bdr, "solucao", "negativacao", "  ")


def test_perdido_exige_motivo_e_vira_rotulo(base_carregada):
    lead_id, bdr = _lead_na_fila()
    with pytest.raises(estados.TransicaoInvalida):
        comercial.fechar(lead_id, bdr, ganho=False, motivo=None)
    comercial.fechar(lead_id, bdr, ganho=False, motivo="Sem orçamento")
    with conectar() as con:
        rot = con.execute("SELECT resultado, motivo FROM rotulos_treino WHERE fonte='funil'").fetchone()
    assert (rot["resultado"], rot["motivo"]) == (0, "Sem orçamento")


def test_ganho_entra_no_retreino(base_carregada):
    lead_id, bdr = _lead_na_fila()
    with conectar() as con:
        for etapa in (estados.EM_CONTATO, estados.QUALIFICADO, estados.REUNIAO, estados.PROPOSTA):
            estados.mudar(con, lead_id, etapa, "teste")
    comercial.fechar(lead_id, bdr, ganho=True)
    assert consultas.lead(lead_id)["etapa"] == estados.GANHO
    resumo = propensao.treinar("teste")
    assert resumo["fontes"].get("funil") == 1


def test_opt_out_bloqueia_novo_contato(base_carregada):
    lead_id, bdr = _lead_na_fila()
    with conectar() as con:
        con.execute("UPDATE leads SET opt_out=1 WHERE id=?", (lead_id,))
    with pytest.raises(ValueError, match="opt-out"):
        comercial.registrar_atividade(lead_id, bdr, "Ligação", "Sem resposta", "tentativa")
