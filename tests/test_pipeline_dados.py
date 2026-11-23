"""Fase 2: limpeza, deduplicação, reconhecimento de colunas e ingestão em camadas."""

from __future__ import annotations

import pandas as pd

from banco.conexao import conectar
from dados import ingestao, limpeza


def test_reconhece_colunas_comuns():
    mapa = limpeza.reconhecer_colunas(["Razão Social", "CNPJ", "Município", "Estado", "E-mail", "Celular", "Obs"])
    assert mapa == {
        "Razão Social": "razao_social", "CNPJ": "cnpj", "Município": "cidade", "Estado": "uf",
        "E-mail": "email", "Celular": "telefone", "Obs": "descricao",
    }  # fmt: skip


def test_padroniza_campos_e_aponta_problemas():
    reg, problemas = limpeza.padronizar({
        "razao_social": "  Exemplo   Ltda ", "cnpj": "11.222.333/0001-81", "telefone": "+55 (61) 99999-0000",
        "email": "CONTATO@EXEMPLO.COM.BR", "uf": "df", "porte": "pequena", "site": "https://www.exemplo.com.br/",
        "interesse": "crédito", "consentimento": "Sim",
    })  # fmt: skip
    assert reg["razao_social"] == "Exemplo Ltda"
    assert reg["cnpj"] == "11222333000181"
    assert reg["telefone"] == "(61) 99999-0000"
    assert reg["email"] == "contato@exemplo.com.br"
    assert reg["uf"] == "DF"
    assert reg["porte"] == "EPP"
    assert reg["site"] == "www.exemplo.com.br"
    assert reg["interesse"] == "Crédito"
    assert reg["base_legal"] == "consentimento"
    assert problemas == []


def test_aponta_cnpj_invalido_e_separa_pendencia_de_contato():
    reg, problemas = limpeza.padronizar({"razao_social": "X", "cnpj": "11222333000182", "email": "sem-arroba"})
    assert "CNPJ com dígito verificador inválido" in problemas
    assert "E-mail inválido" in problemas
    assert reg["base_legal"] == "sem_base"
    assert "Sem consentimento nem base legal" not in problemas


def test_chave_de_deduplicacao():
    com_cnpj = limpeza.chave_dedup({"cnpj": "11222333000181", "razao_social": "A"})
    sem_cnpj_1 = limpeza.chave_dedup({"razao_social": "Loja São João", "cidade": "Goiânia", "uf": "GO"})
    sem_cnpj_2 = limpeza.chave_dedup({"razao_social": "LOJA SAO JOAO", "cidade": "goiania", "uf": "GO"})
    assert com_cnpj == "cnpj:11222333000181"
    assert sem_cnpj_1 == sem_cnpj_2


def test_planilha_marca_duplicado_no_arquivo():
    df = pd.DataFrame({
        "Empresa": ["Alfa", "Alfa", "Beta", ""],
        "Cidade": ["Recife", "Recife", "Natal", ""],
        "UF": ["PE", "PE", "RN", ""],
    })  # fmt: skip
    registros, previa, rel = limpeza.preparar_planilha(df)
    assert rel["linhas"] == 4
    assert "Duplicado no arquivo" in previa.loc[1, "problemas"]
    assert "Sem nome" in previa.loc[3, "problemas"]
    assert len(registros) == 4


def test_remove_dados_pessoais_de_texto_livre():
    texto = limpeza.remover_dados_pessoais("Falar com joao@empresa.com ou (11) 98888-7777 sobre crediário.")
    assert "joao@" not in texto and "98888" not in texto
    assert "crediário" in texto


def test_ingestao_cria_camadas_e_deduplica(base_carregada):
    reg = {"razao_social": "Alfa Distribuidora", "cnpj": "11222333000181", "contato_nome": "Pessoa Teste",
           "email": "pessoa@alfa.exemplo", "consentimento": "sim", "descricao": "Vende a prazo"}  # fmt: skip
    r1 = ingestao.receber([reg], "formulario", "teste")
    r2 = ingestao.receber([reg, {"razao_social": ""}], "formulario", "teste")
    assert len(r1.criados) == 1
    assert len(r2.criados) == 0 and len(r2.duplicados) == 1 and len(r2.rejeitados) == 1
    with conectar() as con:
        assert con.execute("SELECT COUNT(*) FROM leads_brutos").fetchone()[0] == 3
        lead = con.execute("SELECT * FROM leads").fetchone()
        contato = con.execute("SELECT * FROM contatos").fetchone()
        hist = con.execute("SELECT de, para FROM etapas_historico").fetchall()
    assert lead["etapa"] == "Capturado"
    assert contato["email"] == "pessoa@alfa.exemplo"
    # O lead (prata) não guarda os dados pessoais.
    assert "pessoa@alfa.exemplo" not in " ".join(str(v) for v in dict(lead).values())
    assert [tuple(h) for h in hist] == [(None, "Capturado")]


def test_base_ficticia_entra_marcada(base_carregada):
    r = ingestao.carregar_ficticias(5, "teste")
    assert len(r.criados) == 5
    with conectar() as con:
        assert con.execute("SELECT COUNT(*) FROM leads WHERE base_ficticia=1").fetchone()[0] == 5
    assert len(ingestao.ficticias_disponiveis()) == 145
    assert ingestao.entrada_recente(3)[0]["status"] == "Recebido"
