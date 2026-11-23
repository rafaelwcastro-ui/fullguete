"""Teste de renderização Streamlit: regressão para erro real em Carteira e CRM."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from banco import repositorio
from dados import cenario_demo

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
    assert app.button, "Kanban deve renderizar cartões selecionáveis e ações"
