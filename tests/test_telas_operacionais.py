"""Teste de renderização Streamlit: regressão para erro real em Carteira e CRM."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from banco import repositorio
from dados import cenario_demo, ingestao

RAIZ = Path(__file__).resolve().parent.parent


def _sessao_gestor(app: AppTest) -> None:
    gestor = repositorio.usuarios("gestor")[0]
    app.session_state["usuario"] = {
        "id": gestor["id"],
        "login": gestor["login"],
        "nome": gestor["nome"],
        "papel": gestor["papel"],
    }


def test_carteira_renderiza_com_solucao_nula_e_permite_filtrar(base_carregada):
    cenario_demo.montar()
    ingestao.receber(
        [
            {
                "cnpj": "11222333000181",
                "razao_social": "Loja real sem recomendação",
                "cidade": "Campinas",
                "uf": "SP",
                "base_legal": "sem_base",
            }
        ],
        "cnpja",
        "teste",
    )
    app = AppTest.from_file(str(RAIZ / "paginas" / "carteira.py"), default_timeout=30)
    _sessao_gestor(app)
    app.run()
    assert not app.exception, [str(x.message) for x in app.exception]


def test_crm_renderiza_kanban_interativo_e_ficha(base_carregada):
    cenario_demo.montar()
    app = AppTest.from_file(str(RAIZ / "paginas" / "crm_funil.py"), default_timeout=30)
    _sessao_gestor(app)
    app.run()
    assert not app.exception, [str(x.message) for x in app.exception]
    cartoes = [botao for botao in app.button if botao.key and botao.key.startswith("crm_abrir_")]
    assert cartoes, "Os cartões precisam ter botão de abertura."
    selecionado = int(cartoes[0].key.removeprefix("crm_abrir_"))
    cartoes[0].click()
    app.run()
    assert not app.exception, [str(x.message) for x in app.exception]
    assert app.session_state["crm_seletor"] == selecionado
