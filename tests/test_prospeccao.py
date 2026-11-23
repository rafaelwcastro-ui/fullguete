"""Campanhas de prospecção: histórico, tags, deduplicação e escopo do funil."""

from __future__ import annotations

import pandas as pd

from banco import consultas, prospeccao
from banco.conexao import conectar
from ia import agentes
from nucleo import estados


def empresa(cnpj="11222333000181", nome="Loja Exemplo"):
    return {
        "cnpj": cnpj,
        "razao_social": nome,
        "cidade": "Campinas",
        "uf": "SP",
        "cnae": "4711302",
        "setor": "Comércio varejista",
        "data_abertura": "12/04/2026",
        "origem": "cnpja",
        "base_legal": "sem_base",
        "socios": [{"nome": "NOME PRIVADO"}],
        "emails": [{"email": "contato-pessoal@example.invalid"}],
    }


def busca(tag=""):
    return prospeccao.registrar(
        "cnpja",
        "Varejo",
        "Campinas",
        "SP",
        2026,
        4,
        "4711302",
        {"limit": 10, "mainActivity.id.in": "4711302", "token": "SECRETO"},
        [empresa()],
        42,
        "gestor",
        tag_preferida=tag,
    )


def test_historico_cria_tag_e_reabre_sem_api():
    primeira = busca()
    segunda = busca()
    assert primeira.tag == "#varejo-campinas-202604-01"
    assert segunda.tag == "#varejo-campinas-202604-02"
    reaberta = prospeccao.carregar(primeira.id)
    assert reaberta is not None
    assert reaberta.total_fonte == 42
    assert len(reaberta.empresas) == 1
    assert "token" not in reaberta.filtros
    assert "socios" not in str(reaberta.empresas)
    assert "contato-pessoal" not in str(reaberta.empresas)
    assert prospeccao.listar()[0]["encontrados"] == 1


def test_nome_personalizado_sem_duplicar_tag():
    p1 = busca(" #VarejoSP ")
    p2 = busca("#VarejoSP")
    assert p1.tag == "#varejosp-01"
    assert p2.tag == "#varejosp-02"


def test_importar_vincula_novos_e_duplicados_na_mesma_empresa():
    a = busca()
    r1 = prospeccao.importar(a.id, ["11222333000181"], "gestor")
    assert len(r1.criados) == 1
    lead_id = r1.criados[0]
    assert consultas.lead(lead_id)["etapa"] == estados.CAPTURADO
    assert consultas.lead(lead_id)["data_abertura"] == "12/04/2026"
    b = busca()
    r2 = prospeccao.importar(b.id, ["11222333000181"], "gestor")
    assert not r2.criados
    assert len(r2.duplicados) == 1
    assert prospeccao.ids_leads(a.id) == {lead_id}
    assert prospeccao.ids_leads(b.id) == {lead_id}
    etiquetas = prospeccao.etiquetas_por_lead([lead_id])
    assert a.tag in etiquetas[lead_id] and b.tag in etiquetas[lead_id]
    resumo = prospeccao.listar()
    assert resumo[0]["importados"] == 1 and resumo[1]["importados"] == 1
    assert consultas.contato(lead_id) is None


def test_nao_importa_cnpj_de_outra_busca():
    p = busca()
    try:
        prospeccao.importar(p.id, ["99999999999999"], "gestor")
    except ValueError as erro:
        assert "não pertencem" in str(erro)
    else:
        raise AssertionError("A importação fora da campanha deveria falhar")


def test_paginacao_agrega_mais_empresas_sem_apagar_antigas():
    a = busca()
    restante = prospeccao.acrescentar(a.id, [empresa("66285492000117", "Supermercado")], 42)
    assert restante is not None
    assert len(restante.empresas) == 2
    assert prospeccao.carregar(a.id).total_fonte == 42


def test_filtro_preserva_escopo_original_e_expoe_tags():
    p = busca()
    resultado = prospeccao.importar(p.id, ["11222333000181"], "gestor")
    lead_id = resultado.criados[0]
    df = pd.DataFrame({"id": [lead_id, lead_id + 1000], "razao_social": ["A", "B"]})
    so_pesquisa = prospeccao.filtrar_dataframe(df, p.id)
    assert so_pesquisa["id"].tolist() == [lead_id]
    tagged = prospeccao.com_tags(df)
    assert tagged.iloc[0]["tags"] == p.tag
    assert tagged.iloc[1]["tags"] == ""


def test_tratamento_lead_real_nao_cria_sinais_ficticios(monkeypatch):
    from dados import cnpjws

    p = busca()
    r = prospeccao.importar(p.id, ["11222333000181"], "gestor")
    lead_id = r.criados[0]
    monkeypatch.setattr(cnpjws, "consultar", lambda *args, **kwargs: (None, False))
    with conectar() as con:
        lead = dict(con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone())
    ctx = agentes.Contexto(lead=lead, contato=None, consentimento={"base_legal": "sem_base"})
    agentes.enriquecimento(ctx, "", set())
    assert ctx.lead["sinais_simulados"] == {}
    assert "_simulado" not in str(ctx.feats)
    assert "fictícios de demonstração" not in str(ctx.etapas)
