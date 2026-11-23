"""Integração CNPJá Comercial: filtros oficiais, segurança e ingestão."""

from __future__ import annotations

import pytest

from banco import consultas
from dados import cnpja, ingestao


def empresa_exemplo():
    return {
        "taxId": "11222333000181",
        "alias": "Loja Demonstrativa",
        "founded": "2026-04-12",
        "company": {"name": "Empresa Teste Comercial Ltda", "size": {"id": 3}},
        "address": {"city": "Campinas", "state": "SP", "municipality": 3509502},
        "mainActivity": {"id": 4711302, "text": "Supermercados"},
        "members": [{"name": "Pessoa Sigilosa", "taxId": "***"}],
        "emails": [{"address": "sigilo@example.invalid"}],
    }


def test_filtro_abril_2026_campinas_cnae_exato():
    filtros = cnpja.filtros("Varejo", "SP", 3509502, 2026, 4, "4711-3/02", 10)
    assert filtros == {
        "limit": 10,
        "address.state.in": "SP",
        "address.municipality.in": "3509502",
        "status.id.in": "2",
        "founded.gte": "2026-04-01",
        "founded.lte": "2026-04-30",
        "mainActivity.id.in": "4711302",
    }


def test_tag_varejo_e_multiplos_cnaes():
    filtro_tag = cnpja.filtros("Varejo", "SP", 3509502, 2026, 4)
    assert "4711302" in filtro_tag["mainActivity.id.in"]
    explicitos = cnpja.filtros("Varejo", "SP", 3509502, 2026, 4, "4711302,4781400")
    assert explicitos["mainActivity.id.in"] == "4711302,4781400"
    sem_tag = cnpja.filtros("Todos", "SP", 3509502, 2026, 4)
    assert "mainActivity.id.in" not in sem_tag
    with pytest.raises(ValueError):
        cnpja.filtros("Varejo", "SP", 3509502, 2026, 4, "47")


def test_codigo_ibge_obtido_por_nome_sem_acentos(monkeypatch):
    class Resposta:
        status_code = 200

        def json(self):
            return [
                {"id": 3550308, "nome": "São Paulo"},
                {"id": 3509502, "nome": "Campinas"},
            ]

    def get(url, *, headers, params, timeout, allow_redirects):
        assert "/estados/SP/municipios" in url
        assert headers == {}
        return Resposta()

    monkeypatch.setattr(cnpja.requests, "get", get)
    assert cnpja.municipio_ibge("Campinas", "SP") == 3509502
    assert cnpja.municipio_ibge("Sao Paulo", "SP") == 3550308


def test_saldo_gratis_e_autenticacao_sem_bearer(monkeypatch):
    chamadas = []

    class Resposta:
        status_code = 200

        def json(self):
            return {"perpetual": 0, "transient": 50, "user": {"email": "private@example.invalid"}}

    def get(url, *, headers, params, timeout, allow_redirects):
        chamadas.append((url, headers, params))
        return Resposta()

    monkeypatch.setattr(cnpja.requests, "get", get)
    assert cnpja.saldo("minha-chave") == {"perpetual": 0, "transient": 50}
    assert chamadas[0] == ("https://api.cnpja.com/credit", {"Authorization": "minha-chave"}, None)


def test_pesquisa_comercial_e_normalizacao_sem_pessoas(monkeypatch):
    chamadas = []

    class Resposta:
        status_code = 200

        def json(self):
            return {"count": 12, "next": "token-pagina-2", "records": [empresa_exemplo()]}

    def get(url, *, headers, params, timeout, allow_redirects):
        chamadas.append((url, headers, params))
        return Resposta()

    monkeypatch.setattr(cnpja.requests, "get", get)
    filtros = cnpja.filtros("Todos", "SP", 3509502, 2026, 4, limite=1)
    resultado = cnpja.pesquisar("minha-chave", filtros)
    assert chamadas[0][0] == "https://api.cnpja.com/office"
    assert chamadas[0][1] == {"Authorization": "minha-chave"}
    assert chamadas[0][2]["founded.gte"] == "2026-04-01"
    assert resultado.total == 12 and resultado.next_token == "token-pagina-2"
    assert resultado.recebidas == 1 and resultado.rejeitadas == 0
    empresa = resultado.empresas[0]
    assert empresa["cnpj"] == "11222333000181"
    assert empresa["razao_social"] == "Empresa Teste Comercial Ltda"
    assert empresa["data_abertura"] == "12/04/2026"
    assert empresa["base_legal"] == "sem_base"
    assert "Pessoa Sigilosa" not in str(empresa)
    assert "sigilo@example.invalid" not in str(empresa)


def test_erro_429_revela_cota_nao_chave(monkeypatch):
    class Resposta:
        status_code = 429

    monkeypatch.setattr(cnpja.requests, "get", lambda *a, **kw: Resposta())
    with pytest.raises(cnpja.ErroCnpja) as exc:
        cnpja.pesquisar("CHAVE_SUPER_PRIVADA", {"limit": 1})
    assert exc.value.status == 429
    assert "Créditos" in str(exc.value)
    assert "CHAVE_SUPER_PRIVADA" not in str(exc.value)


def test_importacao_com_deduplicacao_e_sem_contato(base_carregada):
    empresa = cnpja._registro(empresa_exemplo())
    importado = ingestao.receber([empresa], "cnpja", "teste")
    assert len(importado.criados) == 1
    lead_id = importado.criados[0]
    assert consultas.lead(lead_id)["origem"] == "cnpja"
    assert consultas.lead(lead_id)["cnpj"] == "11222333000181"
    assert consultas.contato(lead_id) is None
    assert consultas.consentimento(lead_id)["base_legal"] == "sem_base"
    repetido = ingestao.receber([empresa], "cnpja", "teste")
    assert repetido.criados == []
    assert len(repetido.duplicados) == 1


def test_token_de_pagina_nao_repete_filtros(monkeypatch):
    chamados = []

    class Resposta:
        status_code = 200

        def json(self):
            return {"count": 0, "next": None, "records": []}

    def get(url, *, headers, params, timeout, allow_redirects):
        chamados.append(params)
        return Resposta()

    monkeypatch.setattr(cnpja.requests, "get", get)
    cnpja.pesquisar("chave", {"token": "cursor-123"})
    assert chamados == [{"token": "cursor-123"}]
