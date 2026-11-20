"""Fase 1: banco, migrações, catálogo, login e base fictícia."""

from __future__ import annotations

import catalogo
from banco import repositorio, semente
from banco.conexao import conectar
from dados import base_ficticia, cnpj, features
from nucleo import auth

TABELAS_SECAO_9 = {
    "usuarios",
    "leads_brutos",
    "leads",
    "contatos",
    "leads_features",
    "consentimentos",
    "icp_versoes",
    "tratamentos",
    "recomendacoes",
    "atribuicoes",
    "atividades",
    "etapas_historico",
    "oportunidades",
    "correcoes_ia",
    "modelos_registro",
    "eventos_ia",
    "auditoria",
}


def test_esquema_tem_todas_as_tabelas():
    with conectar() as con:
        tabelas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        versao = con.execute("SELECT MAX(versao) FROM esquema_versao").fetchone()[0]
    assert tabelas >= TABELAS_SECAO_9
    assert versao >= 1


def test_carga_inicial_idempotente(base_carregada):
    assert base_carregada["usuarios_novos"] == 5
    assert base_carregada["historico_novo"] == 500
    segunda = semente.garantir_base(simulado=True)
    assert segunda == {"usuarios_novos": 0, "historico_novo": 0}
    assert repositorio.contar("rotulos_treino") == 500
    assert repositorio.icp_ativo()["nome"] == "ICP inicial"


def test_papeis_de_demonstracao(base_carregada):
    papeis = sorted(u["papel"] for u in semente.usuarios_demonstracao())
    assert papeis == ["bdr", "bdr", "bdr", "executivo", "gestor"]
    assert semente.usuarios_demonstracao()[0]["login"] == "gestor"


def test_modo_real_desativa_logins_demo(base_carregada):
    semente.garantir_base(simulado=False)
    assert repositorio.usuarios() == []


def test_login_com_hash(base_carregada):
    usuarios = repositorio.usuarios_para_login()
    assert auth.autenticar(usuarios, "BDR.Ana", base_ficticia.SENHA_DEMO)["papel"] == "bdr"
    assert auth.autenticar(usuarios, "bdr.ana", "errada") is None
    assert auth.autenticar(usuarios, "ninguem", "x") is None
    assert base_ficticia.SENHA_DEMO not in usuarios["bdr.ana"]["senha_hash"]


def test_configuracao_guarda_historico(base_carregada):
    repositorio.salvar_config("psi_limite", 0.25, "gestor", "teste")
    assert repositorio.config("psi_limite") == 0.25
    with conectar() as con:
        hist = con.execute("SELECT * FROM configuracoes_historico WHERE chave='psi_limite' ORDER BY id").fetchall()
    assert [h["alterado_por"] for h in hist] == ["sistema", "gestor"]


def test_catalogo_consistente():
    assert len(catalogo.solucoes()) == 29
    assert catalogo.validar() == []


def test_cnpj():
    assert cnpj.valido("11.222.333/0001-81")
    assert not cnpj.valido("11.222.333/0001-82")
    assert not cnpj.valido("11111111111111")
    assert not cnpj.valido("123")
    assert cnpj.formatar("11222333000181") == "11.222.333/0001-81"


def test_base_ficticia_deterministica_e_valida():
    a, b = base_ficticia.gerar_empresas(), base_ficticia.gerar_empresas()
    assert a == b
    assert len(a) == 150
    assert all(cnpj.valido(e["cnpj"]) and e["base_ficticia"] for e in a)
    assert len({e["nome_fantasia"] for e in a}) == 150
    assert all(e["site"].endswith(".exemplo") for e in a)


def test_historico_tem_ganhos_e_perdas():
    hist = base_ficticia.gerar_historico()
    taxa = sum(h["resultado"] for h in hist) / len(hist)
    assert len(hist) == 500
    assert 0.2 < taxa < 0.5
    assert set(hist[0]["features"]) == set(features.FEATURES)


def test_features_sem_localizacao_e_sem_contato():
    empresa = base_ficticia.gerar_empresas()[0]
    f = features.calcular(empresa)
    assert not {"uf", "cidade"} & set(f)
    texto = features.texto_empresa(empresa)
    assert empresa["contato"]["email"] not in texto
    assert empresa["contato"]["nome"] not in texto


def test_detecta_segmento_e_sinais_coerentes():
    lead = {
        "razao_social": "Exemplo Distribuidora Ltda",
        "cnae": "4639701",
        "descricao": "Vende para outras empresas com boleto a prazo e sofre com inadimplência.",
    }
    f = features.calcular(lead)
    assert f["segmento"] == "atacado_distribuicao"
    assert {"vende_prazo_pj", "inadimplencia"} <= set(f["sinais"])
