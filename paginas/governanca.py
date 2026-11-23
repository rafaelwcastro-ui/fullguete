"""Governança & LGPD: princípios, base legal, opt-out, titular, retenção, auditoria, pesos e viés."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

import catalogo
from banco import consultas, metricas, repositorio
from banco.conexao import conectar
from dados.ingestao import CANAIS, ORIGENS_ROTULO
from nucleo import campanhas_ui, componentes, config, estados, lgpd, tempo, ui

usuario = st.session_state["usuario"]
pode_editar = usuario["papel"] == "gestor"

ui.cabecalho(
    "Governança & LGPD",
    "Como o Fullguete usa dados e IA com responsabilidade, e onde cada decisão fica registrada.",
    secao="Controles",
)
if msg := st.session_state.pop("gov_msg", None):
    st.success(msg)

abas = st.tabs(["Princípios", "Base legal e opt-out", "Titular de dados", "Retenção", "Trilha de auditoria",
                "Pesos e limites", "Checagem de viés"])  # fmt: skip

# ---------- princípios ----------
with abas[0]:
    st.markdown(
        """
**O Fullguete não toma decisão de crédito.** Ele prioriza prospects comerciais para o time que vende soluções
Equifax. Decisões de crédito são do cliente, usando essas soluções.

- **Human in the loop.** Nenhum agente envia mensagem nem fecha negócio. Casos de baixa confiança vão para revisão
  humana, e o BDR pode corrigir a IA, sempre com motivo registrado.
- **Minimização de dados.** Nome, e-mail e telefone do contato ficam numa tabela separada e nunca vão para o LLM.
  E-mails e telefones digitados em campos livres são removidos antes do envio.
- **Explicabilidade (XAI).** Toda nota mostra quanto veio da aderência, da propensão e da confiança, a justificativa
  em português e o caminho no grafo que levou à solução.
- **Sem segmentação territorial.** UF e município são só dados cadastrais e filtros. Não entram na nota.
- **Qualificação e contato separados.** Ausência de base documentada para abordagem não retém o CNPJ nem impede a análise interna. Contatos exigem base legal fundamentada; opt-out continua bloqueando.
- **Checagem de viés.** A distribuição de notas e de conversão por segmento e porte é acompanhada nesta página.
- **Dados fictícios e integrações simuladas** são sempre rotulados. CNPJá e CNPJ.ws são APIs reais;
  os dados públicos não comprovam faturamento, inadimplência ou comportamento de crédito.
"""
    )

# ---------- base legal e opt-out ----------
with abas[1]:
    with conectar() as con:
        base = pd.read_sql_query(
            """SELECT l.canal, l.origem, c.base_legal, COUNT(*) leads, SUM(l.opt_out) opt_outs
               FROM leads l JOIN consentimentos c ON c.id = (SELECT MAX(id) FROM consentimentos WHERE lead_id=l.id)
               GROUP BY l.canal, l.origem, c.base_legal""", con)  # fmt: skip
    if not base.empty:
        ui.rotulo("Base legal por origem")
        base["canal"] = base["canal"].map(lambda c: CANAIS.get(c, c))
        base["origem"] = base["origem"].map(lambda o: ORIGENS_ROTULO.get(o, o))
        base["base_legal"] = base["base_legal"].map({"consentimento": "Consentimento", "legitimo_interesse":
                                                     "Legítimo interesse", "sem_base": "Sem base legal"})  # fmt: skip
        tabela = base.pivot_table(index=["canal", "origem"], columns="base_legal", values="leads", aggfunc="sum",
                                  fill_value=0).reset_index()  # fmt: skip
        st.dataframe(tabela, hide_index=True, width="stretch")

    a, b = st.columns(2)
    with a:
        ui.rotulo("Registrar opt-out")
        ativos = consultas.leads([e for e in estados.ESTADOS if e not in (estados.GANHO,)])
        ativos = ativos[ativos["opt_out"] == 0]
        opcoes = {int(r.id): f"#{r.id} {r.nome_fantasia or r.razao_social} · {r.etapa}" for r in ativos.itertuples()}
        with st.form("opt_out"):
            alvo = st.selectbox("Lead", list(opcoes), format_func=opcoes.get) if opcoes else None
            obs = st.text_input("Como o pedido chegou", max_chars=200)
            ok = st.form_submit_button("Registrar opt-out", type="primary", disabled=not opcoes)
        if ok and alvo:
            etapa = lgpd.registrar_opt_out(alvo, usuario["login"], obs)
            st.session_state["gov_msg"] = f"Opt-out registrado. O lead saiu das filas e foi para {etapa}."
            st.rerun()
        st.caption("O opt-out tira o lead de todas as filas e bloqueia novos contatos.")
    with b:
        ui.rotulo("Documentar base legal para contato")
        with conectar() as con:
            pendentes_ids = {
                int(linha["id"])
                for linha in con.execute(
                    """SELECT l.id FROM leads l
                       JOIN consentimentos c ON c.id=(
                           SELECT MAX(c2.id) FROM consentimentos c2 WHERE c2.lead_id=l.id
                       )
                       WHERE l.opt_out=0 AND c.base_legal='sem_base'"""
                )
            }
        pendentes = consultas.leads()
        pendentes = pendentes[pendentes["id"].isin(pendentes_ids)]
        if not pendentes.empty:
            pendentes = campanhas_ui.aplicar(pendentes, "id", "lgpd_campanha")
        st.caption(
            "O cadastro e a análise de CNPJs são realizados separadamente do contato. "
            "Documente consentimento ou legítimo interesse fundamentado antes de uma abordagem."
        )
        opcoes_r = {
            int(r.id): f"#{r.id} {r.nome_fantasia or r.razao_social} · {r.etapa}" for r in pendentes.itertuples()
        }
        with st.form("regularizar"):
            alvo_r = st.selectbox("Lead pendente", list(opcoes_r), format_func=opcoes_r.get) if opcoes_r else None
            base_legal = st.radio("Nova base legal", ["consentimento", "legitimo_interesse"], horizontal=True,
                                  format_func={"consentimento": "Consentimento", "legitimo_interesse": "Legítimo interesse"}.get)  # fmt: skip
            obs_r = st.text_area(
                "Fundamentação da base legal (obrigatório)",
                max_chars=600,
                help="Para legítimo interesse, documente finalidade, necessidade, balanceamento e salvaguardas.",
            )
            ok_r = st.form_submit_button("Registrar base para contato", disabled=not (opcoes_r and pode_editar))
        if ok_r and alvo_r:
            try:
                etapa_anterior = consultas.lead(alvo_r)["etapa"]
                lgpd.regularizar(alvo_r, usuario["login"], base_legal, obs_r)
                if etapa_anterior == estados.RETIDO:
                    from ia import orquestrador

                    orquestrador.tratar([alvo_r], usuario["login"])
            except ValueError as erro:
                st.error(str(erro))
            else:
                st.session_state["gov_msg"] = (
                    "Base legal de contato registrada. "
                    "O lead continua no fluxo comercial, sem perder score ou histórico."
                )
                st.rerun()

# ---------- titular ----------
with abas[2]:
    st.caption("Atenda pedidos de acesso e de exclusão. A exclusão apaga os dados pessoais do contato e as anotações; "
               "os dados da empresa e a trilha de auditoria ficam.")  # fmt: skip
    termo = st.text_input("Buscar titular por e-mail, nome ou telefone", max_chars=120)
    achados = lgpd.buscar_titular(termo) if termo else []
    if termo and not achados:
        st.caption("Nenhum titular encontrado.")
    if achados:
        rotulos = {a["lead_id"]: f"{a['nome'] or 'sem nome'} · {a['email'] or 'sem e-mail'} · {a['razao_social']}"
                   for a in achados}  # fmt: skip
        titular = st.selectbox("Titular", list(rotulos), format_func=rotulos.get)
        a, b = st.columns(2)
        with a:
            st.download_button("Exportar dados do titular (JSON)", lgpd.exportar_titular(titular, usuario["login"]),
                               f"titular_lead_{titular}.json", "application/json", on_click="ignore")  # fmt: skip
        with b, st.form("excluir_titular"):
            confirmo = st.checkbox("Confirmo a exclusão dos dados pessoais deste titular. Não dá para desfazer.")
            if st.form_submit_button("Excluir dados pessoais", disabled=not pode_editar):
                if not confirmo:
                    st.error("Marque a confirmação.")
                else:
                    lgpd.excluir_titular(titular, usuario["login"])
                    st.session_state["gov_msg"] = "Dados pessoais excluídos e opt-out registrado."
                    st.rerun()
        if not pode_editar:
            st.caption("Só o gestor pode excluir dados.")

# ---------- retenção ----------
with abas[3]:
    dias = int(repositorio.config("retencao_dias") or 365)
    with st.form("retencao"):
        novo = st.number_input("Guardar dados pessoais de leads parados por até (dias)", 30, 3650, dias, step=30)
        motivo = st.text_input("Motivo da alteração", max_chars=200)
        if st.form_submit_button("Salvar política", disabled=not pode_editar):
            repositorio.salvar_config("retencao_dias", int(novo), usuario["login"], motivo)
            st.session_state["gov_msg"] = "Política de retenção atualizada."
            st.rerun()
    candidatos = lgpd.candidatos_retencao(dias)
    st.markdown(f"**{len(candidatos)}** lead(s) parados há mais de {dias} dias ainda guardam dados pessoais.")
    if st.button("Aplicar a política agora", disabled=not (pode_editar and candidatos)):
        n = lgpd.aplicar_retencao(dias, usuario["login"])
        st.session_state["gov_msg"] = f"Dados pessoais removidos de {n} lead(s)."
        st.rerun()

# ---------- auditoria ----------
with abas[4]:
    a, b = st.columns([1, 2])
    lead_filtro = a.number_input("Filtrar por lead (#)", min_value=0, value=0, step=1)
    acoes = b.multiselect("Ações", ["decisao_ia", "mudanca_etapa", "correcao_ia", "atividade", "opt_out", "captura",
                                    "atribuicao", "modelo_treinado", "exclusao_titular", "passagem_executivo"], placeholder="Todas")  # fmt: skip
    trilha = consultas.auditoria(str(lead_filtro) if lead_filtro else None, limite=500)
    if acoes:
        trilha = trilha[trilha["acao"].isin(acoes)]
    trilha["ocorrido_em"] = trilha["ocorrido_em"].map(tempo.fmt)
    st.dataframe(trilha, hide_index=True, width="stretch", column_config={
        "ocorrido_em": "Quando", "ator": "Quem", "acao": "Ação", "entidade": "Entidade", "entidade_id": "Id",
        "detalhe": st.column_config.TextColumn("Detalhe", width="large")})  # fmt: skip
    if lead_filtro:
        corr = consultas.correcoes(int(lead_filtro))
        if not corr.empty:
            ui.rotulo("Revisões humanas e correções da IA deste lead")
            st.dataframe(corr[["registrada_em", "usuario", "campo", "valor_ia", "valor_correto", "concorda", "motivo"]],
                         hide_index=True, width="stretch")  # fmt: skip

# ---------- pesos e limites ----------
with abas[5]:
    pesos = repositorio.config("pesos_nota")
    limites = repositorio.config("limites_classificacao")
    with st.form("pesos"):
        ui.rotulo("Pesos da nota final")
        a, b, c = st.columns(3)
        p_ad = a.slider("Aderência ao ICP", 0.0, 1.0, float(pesos["aderencia"]), 0.05)
        p_pr = b.slider("Propensão de conversão", 0.0, 1.0, float(pesos["propensao"]), 0.05)
        p_co = c.slider("Confiança da recomendação", 0.0, 1.0, float(pesos["confianca"]), 0.05)
        ui.rotulo("Limites da classificação")
        a, b, c, d = st.columns(4)
        l_q = a.number_input("Quente a partir de", 0, 100, int(limites["quente"]))
        l_m = b.number_input("Morno a partir de", 0, 100, int(limites["morno"]))
        l_f = c.number_input("Frio a partir de", 0, 100, int(limites["frio"]))
        conf_min = d.number_input("Confiança mínima para a fila", 0.0, 1.0,
                                  float(repositorio.config("confianca_minima_fila")), 0.05)  # fmt: skip
        sla = repositorio.config("sla_horas")
        a, b, c = st.columns(3)
        sla_q = a.number_input("SLA Quente (horas)", 1, 168, int(sla["Quente"]))
        sla_m = b.number_input("SLA Morno (horas)", 1, 168, int(sla["Morno"]))
        psi = c.number_input("Limite de alerta do PSI", 0.05, 1.0, float(repositorio.config("psi_limite")), 0.05)
        motivo = st.text_input("Motivo da alteração (obrigatório)", max_chars=200)
        salvar = st.form_submit_button("Salvar configuração", type="primary", disabled=not pode_editar)
    if salvar:
        if not motivo.strip():
            st.error("Escreva o motivo.")
        elif not (l_q > l_m > l_f):
            st.error("Os limites precisam seguir Quente > Morno > Frio.")
        elif p_ad + p_pr + p_co == 0:
            st.error("Pelo menos um peso precisa ser maior que zero.")
        else:
            total = p_ad + p_pr + p_co
            ator = usuario["login"]
            repositorio.salvar_config("pesos_nota", {"aderencia": round(p_ad / total, 3), "propensao": round(p_pr / total, 3),
                                                     "confianca": round(p_co / total, 3)}, ator, motivo)  # fmt: skip
            repositorio.salvar_config("limites_classificacao", {"quente": l_q, "morno": l_m, "frio": l_f}, ator, motivo)
            repositorio.salvar_config("confianca_minima_fila", conf_min, ator, motivo)
            repositorio.salvar_config("sla_horas", {"Quente": sla_q, "Morno": sla_m}, ator, motivo)
            repositorio.salvar_config("psi_limite", psi, ator, motivo)
            st.session_state["gov_msg"] = "Configuração salva. Reprocesse os leads para aplicar às notas atuais."
            st.rerun()
    if not pode_editar:
        st.caption("Só o gestor altera pesos e limites.")
    st.caption("Os pesos são normalizados para somar 1.")
    with conectar() as con:
        hist = pd.read_sql_query("SELECT alterado_em, alterado_por, chave, valor_anterior, valor_novo, motivo "
                                 "FROM configuracoes_historico ORDER BY id DESC LIMIT 100", con)  # fmt: skip
    hist["alterado_em"] = hist["alterado_em"].map(tempo.fmt)
    ui.rotulo("Histórico de alterações")
    st.dataframe(hist, hide_index=True, width="stretch")

# ---------- viés ----------
with abas[6]:
    df = metricas.leads_tempo()
    tratados = df[df["nota_final"].notna()]
    if tratados.empty:
        st.info("Sem leads tratados ainda.")
    else:
        segs = {s["id"]: s["nome"] for s in catalogo.carregar_regras()["segmentos"]}
        tratados = tratados.assign(segmento_nome=tratados["segmento"].map(lambda s: segs.get(s, "Outros")),
                                   ganhou=tratados["etapa"].eq(estados.GANHO))  # fmt: skip
        for coluna, titulo in (("segmento_nome", "segmento"), ("porte", "porte")):
            ui.rotulo(f"Notas e conversão por {titulo}")
            a, b = st.columns([1.4, 1])
            with a:
                fig = px.box(tratados, x=coluna, y="nota_final", points=False, color_discrete_sequence=["#2DD4BF"],
                             labels={coluna: "", "nota_final": "Nota final"})  # fmt: skip
                st.plotly_chart(componentes.layout_grafico(fig, 300), width="stretch", config={"displayModeBar": False})
            with b:
                resumo = tratados.groupby(coluna).agg(leads=("id", "count"), nota_media=("nota_final", "mean"),
                                                      ganhos=("ganhou", "sum")).reset_index()  # fmt: skip
                resumo["conversao"] = (resumo["ganhos"] / resumo["leads"]).map("{:.0%}".format)
                resumo["nota_media"] = resumo["nota_media"].round(0)
                st.dataframe(resumo, hide_index=True, width="stretch")
        st.caption("Diferenças grandes entre grupos com perfis parecidos merecem revisão do ICP, dos pesos e das regras do "
                   "grafo. A localização não entra na nota, por isso não há corte por região.")  # fmt: skip

# ---------- base de demonstração ----------
if config.simulado() and pode_editar:
    with st.expander("Base de demonstração"):
        st.caption("Apaga o banco do modo simulado e monta de novo o mês fictício. Útil para ensaiar a apresentação.")
        confirmo = st.checkbox("Confirmo que quero apagar e remontar a base de demonstração")
        if st.button("Reiniciar base de demonstração", disabled=not confirmo):
            from dados import cenario_demo

            with st.spinner("Remontando..."):
                cenario_demo.reiniciar(usuario["login"])
            st.cache_resource.clear()
            st.session_state.clear()
            st.rerun()
