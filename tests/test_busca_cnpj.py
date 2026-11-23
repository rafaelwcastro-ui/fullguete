"""Busca real de CNPJs: filtros de abertura aplicados no provedor e LGPD."""

from __future__ import annotations

import pytest

from banco import consultas
from dados import busca_cnpj, ingestao


def _empresa():
    return {
        "cnpj_completo": "11222333000181",
        "razao_social": "Empresa Verificada Exemplo Ltda",
        "nome_fantasia": "Loja Exemplo",
        "uf": "SP",
        "municipio": "CAMPINAS",
        "cnae_principal": "4711302",
        "cnae_descricao": "COMERCIO VAREJISTA DE MERCADORIAS",
        "data_abertura": "20260415",
        "situacao": "02",
        "porte": "03",
        "socios": [{"nome_socio": "NOME SIGILOSO", "cnpj_cpf_do_socio": "***123456**"}],
        "correio_eletronico": "pessoa.sigilo@exemplo.invalid",
    }


def test_tags_filtros_varejo_campinas_abril_2026():
    filtros = busca_cnpj.parametros("Varejo", "Campinas", "SP", 2026, 4)
    assert filtros["cidade"] == "Campinas"
    assert filtros["uf"] == "SP"
    assert filtros["atividade"] == "VAREJISTA"
    assert filtros["abertura_de"] == "2026-04-01"
    assert filtros["abertura_ate"] == "2026-04-30"
    assert filtros["situacao"] == "02"


def test_cnae_exato_substitui_tag_e_fevereiro_bissexto():
    filtros = busca_cnpj.parametros("Varejo", "Campinas", "SP", 2024, 2, "4711-3/02", 50)
    assert filtros["cnae"] == "4711302"
    assert "atividade" not in filtros
    assert filtros["abertura_ate"] == "2024-02-29"
    assert filtros["limit"] == 50
    with pytest.raises(ValueError, match="CNAE"):
        busca_cnpj.parametros("Varejo", "Campinas", "SP", 2026, 4, "47")


def test_consulta_real_mockada_e_paginacao(monkeypatch):
    chamadas = []

    class RespostaFicticia:
        status_code = 200

        def json(self):
            return {
                "resultados": [_empresa()], "has_more": True,
                "next_cursor": "proxima-pagina", "snapshot": "2026-11",
            }

    def get(url, *, headers, params, timeout, allow_redirects):
        chamadas.append((url, headers, params, timeout, allow_redirects))
        return RespostaFicticia()

    monkeypatch.setattr(busca_cnpj.requests, "get", get)
    filtros = busca_cnpj.parametros("Varejo", "Campinas", "SP", 2026, 4)
    pagina = busca_cnpj.buscar("minha-chave", filtros)
    assert pagina.has_more and pagina.next_cursor == "proxima-pagina"
    assert pagina.snapshot == "2026-11"
    assert pagina.registros[0]["data_abertura"] == "15/04/2026"
    assert pagina.registros[0]["base_legal"] == "sem_base"
    assert chamadas[0][1] == {"Authorization": "Bearer minha-chave"}
    assert chamadas[0][2]["abertura_de"] == "2026-04-01"
    assert chamadas[0][4] is False
    assert "NOME SIGILOSO" not in str(pagina.registros)
    assert "pessoa.sigilo" not in str(pagina.registros)


def test_erros_do_provedor_nao_expoem_chaves(monkeypatch):
    class Falha:
        status_code = 401

    monkeypatch.setattr(busca_cnpj.requests, "get", lambda *a, **k: Falha())
    with pytest.raises(busca_cnpj.ErroBusca, match="Chave de API inválida") as erro:
        busca_cnpj.buscar("segredo-de-teste", {"uf": "SP"})
    assert "segredo-de-teste" not in str(erro.value)
    with pytest.raises(busca_cnpj.ErroBusca, match="chave"):
        busca_cnpj.buscar("", {"uf": "SP"})


def test_importar_ausencia_base_legal_sem_criar_contatos(base_carregada):
    registro = busca_cnpj.normalizar_empresa(_empresa(), "2026-11")
    resultado = ingestao.receber([registro], "busca_cnpj", "teste")
    assert len(resultado.criados) == 1
    lead_id = resultado.criados[0]
    assert consultas.lead(lead_id)["cnpj"] == "11222333000181"
    assert consultas.lead(lead_id)["origem"] == "busca_cnpj"
    assert consultas.contato(lead_id) is None
    assert consultas.consentimento(lead_id)["base_legal"] == "sem_base"
    duplicado = ingestao.receber([registro], "busca_cnpj", "teste")
    assert not duplicado.criados and len(duplicado.duplicados) == 1
