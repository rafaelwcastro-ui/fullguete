"""Máquina de estados: transições permitidas, proibidas, motivo obrigatório e opt-out."""

from __future__ import annotations

import pytest

from banco.conexao import conectar
from dados import ingestao
from nucleo import estados


def _novo_lead() -> int:
    r = ingestao.receber([{"razao_social": "Lead Teste", "cidade": "Natal", "uf": "RN", "consentimento": "sim"}],
                         "formulario", "teste")  # fmt: skip
    return r.criados[0]


def test_caminho_feliz_ate_ganho(base_carregada):
    lead = _novo_lead()
    caminho = [estados.EM_TRATAMENTO, estados.TRATADO, estados.FILA_BDR, estados.EM_CONTATO, estados.QUALIFICADO,
               estados.REUNIAO, estados.PROPOSTA, estados.GANHO]  # fmt: skip
    with conectar() as con:
        for etapa in caminho:
            estados.mudar(con, lead, etapa, "teste")
        hist = con.execute("SELECT para, ator FROM etapas_historico WHERE lead_id=? ORDER BY id", (lead,)).fetchall()
    assert [h["para"] for h in hist] == [estados.CAPTURADO, *caminho]
    assert all(h["ator"] == "teste" for h in hist)


@pytest.mark.parametrize(
    ("de_caminho", "para"),
    [([], estados.GANHO), ([], estados.FILA_BDR), ([estados.EM_TRATAMENTO, estados.TRATADO], estados.PROPOSTA)],
)
def test_transicoes_proibidas(base_carregada, de_caminho, para):
    lead = _novo_lead()
    with conectar() as con:
        for etapa in de_caminho:
            estados.mudar(con, lead, etapa, "teste")
        with pytest.raises(estados.TransicaoInvalida):
            estados.mudar(con, lead, para, "teste")


def test_perdido_e_descartado_exigem_motivo(base_carregada):
    lead = _novo_lead()
    with conectar() as con:
        with pytest.raises(estados.TransicaoInvalida, match="motivo"):
            estados.mudar(con, lead, estados.DESCARTADO, "teste")
        with pytest.raises(estados.TransicaoInvalida, match="Outro"):
            estados.mudar(con, lead, estados.DESCARTADO, "teste", motivo="Outro")
        estados.mudar(con, lead, estados.DESCARTADO, "teste", motivo="Sem fit")
        motivo = con.execute("SELECT motivo FROM etapas_historico WHERE lead_id=? ORDER BY id DESC", (lead,))
        assert motivo.fetchone()[0] == "Sem fit"


def test_opt_out_bloqueia_contato(base_carregada):
    lead = _novo_lead()
    with conectar() as con:
        estados.mudar(con, lead, estados.EM_TRATAMENTO, "teste")
        estados.mudar(con, lead, estados.TRATADO, "teste")
        con.execute("UPDATE leads SET opt_out=1 WHERE id=?", (lead,))
        with pytest.raises(estados.TransicaoInvalida, match="opt-out"):
            estados.mudar(con, lead, estados.FILA_BDR, "teste")
