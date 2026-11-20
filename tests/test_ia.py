"""Fase 3: nota, JSON do LLM, grafo, propensão e orquestrador em modo simulado."""

from __future__ import annotations

import json

import pytest

import catalogo
from banco import consultas
from banco.conexao import conectar
from dados import ingestao
from ia import agentes, esquemas, grafo, nota, orquestrador, propensao, provedor
from nucleo import estados

# ---------- nota e classificação ----------


@pytest.mark.parametrize(
    ("valor", "classe"),
    [(100, "Quente"), (80, "Quente"), (79.9, "Morno"), (60, "Morno"), (59.9, "Frio"), (40, "Frio"),
     (39.9, "Descartar"), (0, "Descartar")],
)  # fmt: skip
def test_classificacao_nos_limites(valor, classe):
    assert nota.classificar(valor) == classe


def test_nota_final_decomposta():
    final, partes = nota.combinar(80, 50, 0.9)
    assert partes == {"aderencia": 40.0, "propensao": 15.0, "confianca": 18.0}
    assert final == 73.0


def test_destinos():
    assert nota.destino("Quente", 0.8)[0] == estados.FILA_BDR
    assert nota.destino("Morno", 0.59)[0] == estados.REVISAO
    assert nota.destino("Morno", 0.6)[0] == estados.FILA_BDR
    assert nota.destino("Frio", 0.9)[0] == estados.NUTRICAO
    etapa, motivo, _ = nota.destino("Descartar", 0.9)
    assert (etapa, motivo) == (estados.DESCARTADO, "Sem fit")
    assert nota.destino("Quente", 0.9, precisa_revisao=True)[0] == estados.REVISAO


# ---------- validação do JSON ----------
def _resultado(lead_id="1", principal="relatorio_credito_pj", comp="negativacao") -> dict:
    return {
        "lead_id": lead_id, "resumo_empresa": "Distribuidora de alimentos.", "dores_provaveis": ["Atrasos"],
        "nota_aderencia": 85, "justificativa": "Vende a prazo. Tem atrasos.",
        "solucao_principal": {"id": principal, "motivo": "Avalia o comprador.", "confianca": 0.8},
        "solucoes_complementares": [{"id": comp, "motivo": "Recupera atrasos."}],
        "perguntas_descoberta": ["Pergunta 1?", "Pergunta 2?", "Pergunta 3?"],
        "roteiro": {"ligacao": "Olá, tudo bem? Vamos falar.", "email_assunto": "Assunto",
                    "email_corpo": "Corpo do e-mail curto.", "whatsapp": "Olá, tudo bem?"},
        "objecoes": [{"objecao": "Caro", "resposta": "Vale a pena."}],
        "sinais_risco": [], "precisa_revisao_humana": False, "motivo_revisao": "",
    }  # fmt: skip


CANDIDATAS = {"1": {"relatorio_credito_pj", "negativacao", "onescore_pj"}}


def test_json_valido():
    saida = esquemas.validar_lote(json.dumps({"resultados": [_resultado()]}), CANDIDATAS)
    assert saida["1"].solucao_principal.id == "relatorio_credito_pj"


def test_json_invalido():
    ruim = _resultado()
    del ruim["roteiro"]
    with pytest.raises(esquemas.ValidationError):
        esquemas.validar_lote(json.dumps({"resultados": [ruim]}), CANDIDATAS)
    with pytest.raises(esquemas.ValidationError):
        esquemas.validar_lote("isto não é json", CANDIDATAS)
    duas_perguntas = _resultado()
    duas_perguntas["perguntas_descoberta"] = ["a?", "b?"]
    with pytest.raises(esquemas.ValidationError):
        esquemas.validar_lote(json.dumps({"resultados": [duas_perguntas]}), CANDIDATAS)


def test_json_com_id_fora_do_catalogo_e_rejeitado():
    with pytest.raises(esquemas.ErroValidacao, match="fora das candidatas"):
        esquemas.validar_lote(json.dumps({"resultados": [_resultado(principal="produto_inventado")]}), CANDIDATAS)
    # Existe no catálogo, mas não estava entre as candidatas enviadas (RAG): também é rejeitado.
    with pytest.raises(esquemas.ErroValidacao):
        esquemas.validar_lote(json.dumps({"resultados": [_resultado(comp="safe_banking")]}), CANDIDATAS)


def test_json_sem_um_dos_leads_e_rejeitado():
    with pytest.raises(esquemas.ErroValidacao, match="deixou de fora"):
        esquemas.validar_lote(json.dumps({"resultados": [_resultado()]}), {**CANDIDATAS, "2": {"negativacao"}})


# ---------- grafo ----------
@pytest.mark.parametrize(
    ("segmento", "sinais", "interesse", "esperada"),
    [
        ("atacado_distribuicao", ["vende_prazo_pj"], "Crédito", "relatorio_credito_pj"),
        ("ecommerce", ["ecommerce_volume", "chargeback"], "Antifraude", {"kount_gestao_chargeback", "konduto_performance"}),
        ("meios_pagamento", ["pix_p2p"], "Antifraude", "safe_banking"),
        ("varejo_crediario", ["crediario_pf"], "Crédito", {"onescore_pf", "relatorio_credito_pf"}),
        ("educacao", ["recorrencia_pf", "inadimplencia"], "Cobrança", {"negativacao", "acerta_consulta_cpf"}),
    ],
)  # fmt: skip
def test_grafo_candidatas_coerentes(segmento, sinais, interesse, esperada):
    cand = grafo.candidatas(segmento, sinais, interesse)
    assert cand, "o grafo precisa devolver candidatas"
    topo = cand[0]["solucao_id"]
    assert topo in (esperada if isinstance(esperada, set) else {esperada})
    assert all(c["solucao_id"] in catalogo.ids() for c in cand)
    assert cand[0]["caminhos"][0]["frase"]


# ---------- propensão ----------
def test_treino_e_predicao_da_propensao(base_carregada):
    resumo = propensao.treinar("teste")
    comp = resumo["comparacao"]
    assert set(comp) == {"regressao_logistica", "arvore_decisao"}
    assert max(m["auc"] for m in comp.values()) > 0.65
    probs, versao = propensao.prever([{"segmento": "atacado_distribuicao", "origem": "indicacao", "porte_ordem": 3,
                                       "log_funcionarios": 4.5, "n_sinais": 3, "forca_segmento": 0.9,
                                       "interesse_declarado": 1, "interesse_alinhado": 1, "empresa_ativa": 1,
                                       "tem_site": 1}])  # fmt: skip
    assert 0 <= probs[0] <= 1 and versao.startswith("v1")
    assert propensao.treinar("teste")["versao"].startswith("v2")
    ativos = [v for v in propensao.historico_versoes() if v["ativo"]]
    assert len(ativos) == 1


# ---------- orquestrador ----------
def _capturar(**extra) -> int:
    reg = {
        "razao_social": "Fictícia Distribuidora Teste Ltda", "cnae": "4639701", "porte": "Média",
        "descricao": "Distribuidora que vende para outras empresas com boleto a prazo e sofre com inadimplência.",
        "interesse": "Crédito", "consentimento": "sim", "contato_nome": "Pessoa Secreta",
        "email": "pessoa.secreta@teste.exemplo", "telefone": "(11) 91234-5678", "origem": "indicacao",
        "cidade": "Recife", "uf": "PE",
    }  # fmt: skip
    reg.update(extra)
    return ingestao.receber([reg], "formulario", "teste").criados[0]


def test_orquestrador_do_capturado_ate_a_fila(base_carregada):
    lead_id = _capturar()
    resumo = orquestrador.tratar([lead_id], "teste", usar_llm=False)
    assert resumo["total"] == 1
    lead = consultas.lead(lead_id)
    trat = consultas.ultimo_tratamento(lead_id)
    assert lead["etapa"] == estados.FILA_BDR, trat["decomposicao"]
    assert lead["responsavel_id"] is not None
    assert lead["solucao_principal"] in catalogo.ids()
    assert set(trat["decomposicao"]["partes"]) == {"aderencia", "propensao", "confianca"}
    assert [e["agente"] for e in trat["etapas"]] == [a for a, _ in agentes.AGENTES]
    assert trat["recomendacoes"][0]["caminho_grafo"]["caminhos"]
    assert len(consultas.cadencia(lead_id)) == 5
    hist = [h["para"] for h in consultas.historico_etapas(lead_id)]
    assert hist == [estados.CAPTURADO, estados.EM_TRATAMENTO, estados.TRATADO, estados.FILA_BDR]


def test_sem_base_legal_fica_retido_e_nao_chama_ia(base_carregada, monkeypatch):
    chamadas = []
    monkeypatch.setattr(provedor, "disponivel", lambda: True)
    monkeypatch.setattr(provedor, "chamar", lambda *a, **k: chamadas.append(1))
    lead_id = _capturar(consentimento="", base_legal="")
    orquestrador.tratar([lead_id], "teste", usar_llm=True)
    assert consultas.lead(lead_id)["etapa"] == estados.RETIDO
    assert chamadas == []


def test_opt_out_na_origem_bloqueia_fila(base_carregada):
    lead_id = _capturar()
    with conectar() as con:
        con.execute("UPDATE leads SET opt_out=1 WHERE id=?", (lead_id,))
    orquestrador.tratar([lead_id], "teste", usar_llm=False)
    assert consultas.lead(lead_id)["etapa"] == estados.RETIDO
    assert consultas.leads([estados.FILA_BDR]).empty


def test_contato_pessoal_nunca_vai_para_o_llm(base_carregada, monkeypatch):
    enviados = []

    def falso(sistema, usuario, **kwargs):
        enviados.append(sistema + usuario)
        raise provedor.ErroIA("simulado")

    monkeypatch.setattr(provedor, "disponivel", lambda: True)
    monkeypatch.setattr(provedor, "chamar", falso)
    lead_id = _capturar(descricao="Vende a prazo. Falar com pessoa.secreta@teste.exemplo ou (11) 91234-5678.")
    orquestrador.tratar([lead_id], "teste", usar_llm=True)
    assert enviados, "o LLM deveria ter sido chamado"
    texto = " ".join(enviados)
    for dado in ("Pessoa Secreta", "pessoa.secreta@teste.exemplo", "91234-5678", "Recife"):
        assert dado not in texto


def test_json_invalido_tenta_de_novo_e_cai_no_plano_b(base_carregada, monkeypatch):
    tentativas = []

    def responde_errado(sistema, usuario, **kwargs):
        tentativas.append(usuario)
        return provedor.Resposta('{"resultados": [{"lead_id": "x"}]}', 100, 50, 10, "teste")

    monkeypatch.setattr(provedor, "disponivel", lambda: True)
    monkeypatch.setattr(provedor, "chamar", responde_errado)
    lead_id = _capturar()
    resumo = orquestrador.tratar([lead_id], "teste", usar_llm=True)
    assert len(tentativas) == 2
    assert "falhou na validação" in tentativas[1]
    assert resumo["planos_b"] == 1
    trat = consultas.ultimo_tratamento(lead_id)
    assert trat["plano_b"] == 1 and trat["resultado"]["solucao_principal"]["id"] in catalogo.ids()
    with conectar() as con:
        assert con.execute("SELECT COUNT(*) FROM eventos_ia WHERE plano_b=1").fetchone()[0] >= 1


def test_llm_valido_e_usado_e_guardado_no_cache(base_carregada, monkeypatch):
    def responde_certo(sistema, usuario, **kwargs):
        empresas = json.loads(usuario.split("<empresas>\n")[1].split("\n</empresas>")[0])
        resultados = []
        for e in empresas:
            ids = [c["id"] for c in e["candidatas"]]
            resultados.append(_resultado(e["lead_id"], ids[0], ids[1]))
        return provedor.Resposta(json.dumps({"resultados": resultados}), 1000, 500, 900, "gemini-teste")

    monkeypatch.setattr(provedor, "disponivel", lambda: True)
    monkeypatch.setattr(provedor, "chamar", responde_certo)
    lead_id = _capturar()
    orquestrador.tratar([lead_id], "teste", usar_llm=True)
    trat = consultas.ultimo_tratamento(lead_id)
    assert trat["motor"] == "gemini" and trat["plano_b"] == 0
    assert trat["versao_prompt"] == "v1"
    with conectar() as con:
        assert con.execute("SELECT COUNT(*) FROM cache_ia").fetchone()[0] == 1
