"""Da captura ao trabalho comercial: decisão BDR, agenda persistida e CRM."""

from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from banco import consultas, repositorio
from banco.conexao import conectar
from dados import ingestao
from ia import orquestrador
from nucleo import agenda, comercial, estados, gestao_leads, lgpd, tempo, triagem


def _preparar(base_carregada) -> tuple[int, dict, dict]:
    reg = {
        "cnpj": "11222333000181",
        "razao_social": "Mercado exemplo Campinas Ltda",
        "cidade": "Campinas",
        "uf": "SP",
        "cnae": "4712100",
        "setor": "Varejo",
        "base_legal": "sem_base",
    }
    lead_id = ingestao.receber([reg], "cnpja", "gestor").criados[0]
    orquestrador.tratar([lead_id], "gestor", usar_llm=False)
    gestor = repositorio.usuarios("gestor")[0]
    bdr = repositorio.usuarios("bdr")[0]
    if consultas.lead(lead_id)["etapa"] != estados.FILA_BDR:
        triagem.encaminhar([lead_id], gestor, bdr["id"], "Oportunidade comercial para revisão do BDR.")
    else:
        with conectar() as con:
            comercial.atribuir(con, lead_id, bdr["id"], "gestor", "Atribuição manual de teste")
    return lead_id, gestor, bdr


def test_status_analise_e_agenda_nao_fingem_contato(base_carregada):
    lead_id, gestor, bdr = _preparar(base_carregada)
    etapa = gestao_leads.mudar_status(lead_id, bdr, estados.EM_ANALISE, "Avaliar potencial e preparar abordagem")
    assert etapa == estados.EM_ANALISE
    antes = consultas.lead(lead_id)
    assert antes["primeiro_contato_em"] is None
    assert antes["classificacao"] is not None
    ident = agenda.agendar(
        lead_id,
        bdr,
        "Tarefa interna",
        "Revisar perfil de compra",
        tempo.daqui(dias=1),
        "Análise interna sem envio ao cliente",
    )
    apos = consultas.lead(lead_id)
    assert apos["etapa"] == estados.EM_ANALISE
    assert apos["primeiro_contato_em"] is None
    assert apos["proxima_acao"] == "Revisar perfil de compra"
    assert any(ev["id"] == ident for ev in agenda.listar(bdr))
    assert any(ev["id"] == ident for ev in agenda.listar(gestor))
    assert ident not in [ev["id"] for ev in agenda.listar(repositorio.usuarios("bdr")[1])]
    assert lead_id in consultas.carteira(bdr["id"])["id"].tolist()
    agenda.concluir(ident, bdr, "Concluído")
    assert not agenda.listar(bdr)
    assert consultas.lead(lead_id)["proxima_acao"] is None
    assert agenda.listar(bdr, status="Concluído")[0]["status"] == "Concluído"


def test_contato_real_altera_status_e_crm_e_requer_base(base_carregada):
    lead_id, gestor, bdr = _preparar(base_carregada)
    gestao_leads.mudar_status(lead_id, bdr, estados.EM_ANALISE, "Pesquisa de aderência em andamento")
    with pytest.raises(ValueError, match="base legal"):
        gestao_leads.mudar_status(
            lead_id,
            bdr,
            estados.EM_CONTATO,
            "Tentativa documentada de ligação",
            canal_contato="Ligação",
            resultado_contato="Sem resposta",
        )
    assert consultas.lead(lead_id)["primeiro_contato_em"] is None
    lgpd.regularizar(
        lead_id,
        gestor["login"],
        "legitimo_interesse",
        "Finalidade, necessidade e balanceamento documentados; teste de operação comercial.",
    )
    etapa = gestao_leads.mudar_status(
        lead_id,
        bdr,
        estados.EM_CONTATO,
        "Ligação realizada para iniciar a conversa",
        canal_contato="Ligação",
        resultado_contato="Falou com outra pessoa",
    )
    assert etapa == estados.EM_CONTATO
    assert consultas.lead(lead_id)["primeiro_contato_em"]
    assert consultas.atividades(lead_id)[0]["tipo"] == "Ligação"
    assert lead_id in consultas.leads(estados.ETAPAS_FUNIL)["id"].tolist()


def test_qualificacao_real_e_reuniao_geram_agenda_exec(base_carregada):
    lead_id, gestor, bdr = _preparar(base_carregada)
    lgpd.regularizar(
        lead_id,
        gestor["login"],
        "legitimo_interesse",
        "Avaliação documentada de contato comercial no âmbito do teste.",
    )
    gestao_leads.mudar_status(
        lead_id,
        bdr,
        estados.EM_CONTATO,
        "Contato efetivo documentado",
        canal_contato="E-mail",
        resultado_contato="Interessado",
    )
    with pytest.raises(ValueError, match="BANT"):
        gestao_leads.mudar_status(lead_id, bdr, estados.QUALIFICADO, "Qualificado pelo BDR")
    comercial.salvar_bant(
        lead_id,
        bdr,
        {"orcamento": "Em avaliação", "autoridade": "Gestor", "necessidade": "Crédito", "prazo": "30 dias"},
    )
    assert (
        gestao_leads.mudar_status(lead_id, bdr, estados.QUALIFICADO, "Necessidade validada no contato")
        == estados.QUALIFICADO
    )
    executivo = repositorio.usuarios("executivo")[0]
    quando = tempo.daqui(dias=2)
    comercial.qualificar_e_agendar(
        lead_id,
        bdr,
        quando,
        executivo["id"],
        [consultas.lead(lead_id)["solucao_principal"]],
        "Reunião comercial confirmada.",
    )
    assert consultas.lead(lead_id)["etapa"] == estados.REUNIAO
    assert any(ev["lead_id"] == lead_id and ev["tipo"] == "Reunião confirmada" for ev in agenda.listar(executivo))


def test_reuniao_confirmada_bloqueada_sem_base_ou_sem_contato(base_carregada):
    lead_id, gestor, bdr = _preparar(base_carregada)
    with pytest.raises(ValueError, match="base legal"):
        agenda.agendar(lead_id, bdr, "Reunião confirmada", "Reunião externa", tempo.daqui(dias=2))
    agenda.agendar(lead_id, bdr, "Reunião planejada", "Avaliar possibilidade de reunião", tempo.daqui(dias=3))
    lgpd.regularizar(lead_id, gestor["login"], "legitimo_interesse", "Contato com avaliação documentada")
    with pytest.raises(ValueError, match="contato efetivo"):
        agenda.agendar(lead_id, bdr, "Reunião confirmada", "Reunião externa", tempo.daqui(dias=2))
    assert consultas.lead(lead_id)["etapa"] == estados.FILA_BDR


def test_permissao_agenda_e_bdr_inclui_optout(base_carregada):
    lead_id, gestor, bdr = _preparar(base_carregada)
    outro = repositorio.usuarios("bdr")[1]
    with pytest.raises(PermissionError):
        agenda.agendar(lead_id, outro, "Tarefa interna", "Tarefa fora da carteira", tempo.daqui(dias=1))
    with pytest.raises(PermissionError):
        gestao_leads.mudar_status(lead_id, outro, estados.EM_ANALISE, "Tentar mudar outro lead")
    compromisso = agenda.agendar(lead_id, bdr, "Retorno", "Preparar retorno", tempo.daqui(dias=1))
    with pytest.raises(PermissionError):
        agenda.concluir(compromisso, outro, "Concluído")
    lgpd.registrar_opt_out(lead_id, gestor["login"], "Solicitação do titular.")
    with pytest.raises(ValueError, match="Opt-out"):
        agenda.agendar(lead_id, bdr, "Tarefa interna", "Novo contato indevido", tempo.daqui(dias=1))
    with pytest.raises(ValueError, match="Opt-out"):
        gestao_leads.mudar_status(lead_id, bdr, estados.EM_ANALISE, "Ignorar opt-out seria indevido")


def test_nota_interna_nao_registra_falso_resultado_de_conversa(base_carregada):
    lead_id, gestor, bdr = _preparar(base_carregada)
    comercial.registrar_atividade(lead_id, bdr, "Nota", "Falou com o decisor", "Anotação interna sobre perfil.")
    atividade = consultas.atividades(lead_id)[0]
    assert atividade["tipo"] == "Nota"
    assert atividade["resultado"] == ""
    assert consultas.lead(lead_id)["primeiro_contato_em"] is None


def test_telas_streamlit_mostram_gestao_manual_e_agenda(base_carregada):
    lead_id, gestor, bdr = _preparar(base_carregada)
    gestor_sessao = {k: gestor[k] for k in ("id", "login", "nome", "papel")}
    bdr_sessao = {k: bdr[k] for k in ("id", "login", "nome", "papel")}
    agenda.agendar(lead_id, bdr, "Tarefa interna", "Organizar ação da semana", tempo.daqui(dias=2))
    app_fila = AppTest.from_file("paginas/fila_bdr.py", default_timeout=30)
    app_fila.session_state["usuario"] = bdr_sessao
    app_fila.run()
    assert not app_fila.exception, [str(x.message) for x in app_fila.exception]
    assert any("Alterar status" in x.label for x in app_fila.expander)
    app_crm = AppTest.from_file("paginas/crm_funil.py", default_timeout=30)
    app_crm.session_state["usuario"] = gestor_sessao
    app_crm.run()
    assert not app_crm.exception, [str(x.message) for x in app_crm.exception]
    assert any("Minha agenda comercial" in x.label for x in app_crm.expander)
