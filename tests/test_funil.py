"""Fase 5: funil até o fechamento, linha do tempo e cenário de demonstração."""

from __future__ import annotations

from banco import consultas, repositorio
from banco.conexao import conectar
from dados import cenario_demo
from nucleo import comercial, estados


def test_cenario_demo_monta_funil_completo_uma_vez(base_carregada):
    resumo = cenario_demo.montar()
    assert resumo["leads"] == 100 and resumo["ganhos"] > 0 and resumo["reunioes"] > 0
    assert cenario_demo.montar() == {"ja_montado": True}
    etapas = repositorio.leads_por_etapa()
    assert etapas.get(estados.GANHO, 0) == resumo["ganhos"]
    with conectar() as con:
        rotulos = con.execute("SELECT COUNT(*) FROM rotulos_treino WHERE fonte='funil'").fetchone()[0]
        ficticios = con.execute("SELECT COUNT(*) FROM leads WHERE base_ficticia=0").fetchone()[0]
    assert rotulos == resumo["ganhos"] + resumo["perdidos"]
    assert ficticios == 0


def test_linha_do_tempo_de_ponta_a_ponta(base_carregada):
    cenario_demo.montar()
    ganho = consultas.leads([estados.GANHO]).iloc[0]
    fases = [e["fase"] for e in comercial.linha_do_tempo(int(ganho["id"]))]
    assert fases[0] == "Captura"
    for fase in ("Tratamento IA", "Atividade do BDR", "Etapa", "Aprendizado"):
        assert fase in fases
    assert fases.index("Captura") < fases.index("Tratamento IA") < fases.index("Atividade do BDR")


def test_mover_no_funil_ate_ganho(base_carregada):
    cenario_demo.montar()
    proposta = consultas.leads([estados.PROPOSTA]).iloc[0]
    gestor = next(u for u in repositorio.usuarios("gestor"))
    comercial.salvar_oportunidade(int(proposta["id"]), gestor, ["relatorio_credito_pj"], 8000.0, None, None)
    comercial.mover_no_funil(int(proposta["id"]), gestor, estados.GANHO)
    with conectar() as con:
        rot = con.execute("SELECT resultado, valor_mensal FROM rotulos_treino WHERE lead_id=?",
                          (int(proposta["id"]),)).fetchone()  # fmt: skip
    assert (rot["resultado"], rot["valor_mensal"]) == (1, 8000.0)
