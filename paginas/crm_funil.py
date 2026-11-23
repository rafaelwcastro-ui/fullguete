"""CRM & funil: do primeiro contato ao fechamento, com a linha do tempo de ponta a ponta."""

from __future__ import annotations

import html
from datetime import date, datetime, time

import streamlit as st

import catalogo
from banco import consultas, repositorio
from nucleo import campanhas_ui, comercial, crm_operacional, estados, tempo, ui

usuario = st.session_state["usuario"]

ui.cabecalho(
    "CRM & funil",
    "Gestão operacional do pipeline: abra o lead pelo cartão, registre ações, mova etapas e atualize oportunidades.",
    secao="Relacionamento",
)
if msg := st.session_state.pop("crm_msg", None):
    st.success(msg)

funil = consultas.leads(estados.ETAPAS_FUNIL)
if usuario["papel"] == "bdr":
    funil = funil[funil["responsavel_id"] == usuario["id"]]
elif usuario["papel"] == "executivo":
    so_meus = st.toggle("Só as minhas oportunidades", value=False)
    if so_meus:
        funil = funil[funil["executivo_id"] == usuario["id"]]
if funil.empty:
    st.info(
        "Nenhum lead nesta etapa do CRM. Empresas capturadas podem estar em Capturado, "
        "Retido LGPD ou Fila do BDR. Confira Todos os leads no Tratamento IA."
    )
    st.stop()

funil = campanhas_ui.aplicar(funil, "id", "crm_campanha")
if funil.empty:
    st.info("Nenhum lead desta campanha chegou ao CRM nesta carteira.")
    st.stop()

# ---------- filtros operacionais ----------
valores = consultas.valores_oportunidades()
funil = funil.assign(
    empresa=funil["nome_fantasia"].fillna(funil["razao_social"]),
    valor=funil["id"].map(valores),
)
a, b, c, d = st.columns([2, 1.5, 1.4, 1.3])
busca_crm = a.text_input("Empresa ou CNPJ", placeholder="Encontre uma oportunidade", max_chars=100)
etapas_crm = b.multiselect("Etapas", estados.ETAPAS_FUNIL, placeholder="Todas")
responsaveis_crm = c.selectbox(
    "Responsável BDR",
    ["Todos", *crm_operacional.opcoes_solucoes(funil["responsavel"])],
)
so_reais = d.toggle("Somente empresas reais", value=False)
funil = crm_operacional.filtrar_crm(
    funil,
    termo=busca_crm,
    etapas=etapas_crm,
    responsavel="" if responsaveis_crm == "Todos" else responsaveis_crm,
    somente_reais=so_reais,
)
if funil.empty:
    st.info("Nenhuma oportunidade atende aos filtros. Limpe os filtros ou consulte outras etapas em Tratamento IA.")
    if st.button("Ver todos os leads, inclusive capturados e retidos", key="crm_navegar_vazios"):
        st.switch_page("paginas/tratamento.py")
    st.stop()

resumo_funil = crm_operacional.resumo_crm(funil)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Oportunidades no funil", resumo_funil["leads"])
k2.metric("Valor mensal estimado", ui.reais(resumo_funil["valor_mensal"]))
k3.metric("Empresas reais", resumo_funil["reais"])
k4.metric("Base demonstrativa", resumo_funil["ficticios"])
if resumo_funil["ficticios"]:
    st.caption(
        "Valores e oportunidades da base fictícia são apenas demonstração. "
        "Use 'Somente empresas reais' para acompanhar os leads capturados pela API."
    )
if resumo_funil["reais"] == 0:
    st.info(
        "Nenhuma empresa real chegou ao funil comercial neste filtro. "
        "Os CNPJs capturados podem estar em Capturado ou Retido LGPD, "
        "etapas que não entram no Kanban de relacionamento."
    )
    if st.button("Localizar leads capturados e retidos", key="crm_navegar_todos"):
        st.switch_page("paginas/tratamento.py")

# ---------- kanban interativo ----------
ui.rotulo("Kanban comercial · clique na empresa para abrir a ficha")
colunas = st.columns(len(estados.ETAPAS_FUNIL))
for indice, (coluna, etapa) in enumerate(zip(colunas, estados.ETAPAS_FUNIL, strict=True)):
    grupo = funil[funil["etapa"] == etapa]
    total = sum(crm_operacional.valor_seguro(valor) for valor in grupo["valor"])
    with coluna:
        with st.container(border=True):
            st.markdown(f"**{etapa}**")
            st.caption(f"{len(grupo)} lead(s) · {ui.reais(total)}/mês")
        capacidade = st.session_state.get(f"crm_mostrar_{indice}", 6)
        for registro in grupo.head(capacidade).itertuples():
            with st.container(border=True):
                if st.button(
                    crm_operacional.texto_valido(registro.empresa) or registro.razao_social,
                    key=f"crm_abrir_{registro.id}",
                    width="stretch",
                    help="Abrir a ficha comercial deste lead",
                ):
                    st.session_state["crm_seletor"] = int(registro.id)
                    st.rerun()
                nome_oferta = crm_operacional.nome_solucao(registro.solucao_principal)
                if nome_oferta:
                    st.caption(nome_oferta)
                dinheiro = crm_operacional.valor_seguro(registro.valor)
                if dinheiro:
                    st.caption(f"{ui.reais(dinheiro)}/mês")
                if registro.base_ficticia:
                    st.caption("Dados de demonstração")
        if len(grupo) > capacidade and st.button(
            f"Mostrar mais {min(6, len(grupo) - capacidade)}",
            key=f"crm_mais_{indice}",
            width="stretch",
        ):
            st.session_state[f"crm_mostrar_{indice}"] = capacidade + 6
            st.rerun()

# ---------- ficha comercial do lead selecionado ----------
st.divider()
ui.rotulo("Ficha e operações do lead")
opcoes = {int(r.id): f"#{r.id} · {r.empresa} · {r.etapa}" for r in funil.itertuples()}
if st.session_state.get("crm_seletor") not in opcoes:
    st.session_state["crm_seletor"] = next(iter(opcoes))
lead_id = st.selectbox("Empresa selecionada", list(opcoes), format_func=opcoes.get, key="crm_seletor")
lead = consultas.lead(int(lead_id))
if lead is None:
    st.warning("Este lead não existe mais. Atualize os filtros.")
    st.stop()
opp = consultas.oportunidade(lead_id) or {}
st.markdown(f"### {lead['nome_fantasia'] or lead['razao_social']}")
tags_lead = crm_operacional.texto_valido(funil.loc[funil["id"] == lead_id, "tags"].iloc[0])
a, b, c, d = st.columns(4)
a.caption(f"**Etapa:** {lead['etapa']}")
b.caption(f"**CNPJ:** {lead.get('cnpj') or 'Não informado'}")
c.caption(f"**Responsável:** {lead.get('responsavel') or 'Não atribuído'}")
d.caption(f"**Campanhas:** {tags_lead or 'Sem campanha'}")

aba_ficha, aba_atividade, aba_mover, aba_opp, aba_passagem, aba_tempo = st.tabs(
    ["Visão geral", "Registrar atividade", "Mover etapa", "Oportunidade", "Passagem", "Histórico"]
)

with aba_ficha:
    e, f = st.columns(2)
    with e:
        st.markdown("**Dados da empresa**")
        st.write(f"Atividade: {lead.get('setor') or 'Não informada'}")
        st.write(f"Localização: {lead.get('cidade') or '—'} / {lead.get('uf') or '—'}")
        st.write(f"Abertura: {lead.get('data_abertura') or 'Não informada'}")
        st.write(f"Situação: {lead.get('situacao_cadastral') or 'Não informada'}")
    with f:
        st.markdown("**Orientação comercial**")
        st.write(f"Produto sugerido: {crm_operacional.nome_solucao(lead.get('solucao_principal')) or 'Pendente'}")
        st.write(f"Nota da IA: {lead.get('nota_final') if lead.get('nota_final') is not None else 'Não avaliada'}")
        st.write(f"Próxima ação: {lead.get('proxima_acao') or 'Não registrada'}")
        st.write(f"Retorno: {tempo.fmt(lead['retorno_em']) if lead.get('retorno_em') else 'Não agendado'}")
    if lead.get("opt_out"):
        st.warning("Opt-out ativo. O contato com este lead está bloqueado.")
    atividades = consultas.atividades(lead_id)
    st.markdown("**Últimas atividades**")
    if atividades:
        for atividade in atividades[:5]:
            st.caption(
                f"{tempo.fmt(atividade['registrada_em'])} · {atividade['tipo']} · "
                f"{atividade.get('resultado') or atividade.get('anotacao') or 'Sem detalhe'}"
            )
    else:
        st.caption("Nenhuma atividade registrada. Use a aba Registrar atividade para iniciar o histórico.")

with aba_atividade:
    if lead.get("opt_out"):
        st.warning("Este lead solicitou opt-out. Não é permitido registrar novos contatos.")
    else:
        somente_nota = lead["etapa"] in (estados.GANHO, estados.PERDIDO)
        st.caption("Registre a interação, a próxima ação e, se necessário, a data do retorno.")
        with st.form(f"crm_atividade_{lead_id}"):
            tipos = ["Nota"] if somente_nota else comercial.TIPOS_ATIVIDADE
            tipo_atividade = st.selectbox("Tipo de atividade", tipos)
            resultado_atividade = st.selectbox("Resultado", ["", *comercial.RESULTADOS])
            anotacao_atividade = st.text_area("Anotações", max_chars=1500)
            proxima_atividade = st.text_input("Próxima ação", max_chars=200)
            retorno_atividade = st.date_input("Data de retorno (opcional)", value=None, format="DD/MM/YYYY")
            registrar = st.form_submit_button("Salvar atividade", type="primary")
        if registrar:
            try:
                if not (resultado_atividade or anotacao_atividade.strip()):
                    raise ValueError("Descreva a atividade ou escolha o resultado.")
                retorno_iso = (
                    tempo.iso(datetime.combine(retorno_atividade, time(9, 0), tzinfo=tempo.FUSO))
                    if retorno_atividade
                    else None
                )
                comercial.registrar_atividade(
                    lead_id,
                    usuario,
                    tipo_atividade,
                    resultado_atividade,
                    anotacao_atividade,
                    proxima_atividade,
                    retorno_iso,
                )
            except ValueError as erro:
                st.error(str(erro))
            else:
                st.session_state["crm_msg"] = "Atividade registrada e histórico atualizado."
                st.rerun()


with aba_mover:
    possiveis = [
        e for e in estados.ETAPAS_FUNIL + [estados.NUTRICAO] if e in estados.TRANSICOES.get(lead["etapa"], set())
    ]
    if not possiveis:
        st.info(f"O lead está em {lead['etapa']}, uma etapa final.")
        if lead["etapa"] in (estados.GANHO, estados.PERDIDO):
            st.success("Resultado enviado para o aprendizado do modelo.")
    else:
        with st.form(f"mover_{lead_id}"):
            para = st.selectbox("Mover para", possiveis)
            a, b = st.columns(2)
            motivo = a.selectbox("Motivo (obrigatório para Perdido)", ["", *estados.MOTIVOS])
            detalhe = b.text_input("Detalhe", max_chars=300)
            confirmo = st.checkbox(f"Confirmo a mudança de {lead['etapa']} para a etapa escolhida")
            mover = st.form_submit_button("Mover", type="primary")
        if mover:
            if not confirmo:
                st.error("Marque a confirmação.")
            else:
                try:
                    comercial.mover_no_funil(lead_id, usuario, para, motivo or None, detalhe)
                except (ValueError, estados.TransicaoInvalida) as erro:
                    st.error(str(erro))
                else:
                    texto = f"Lead movido para {para}."
                    if para in (estados.GANHO, estados.PERDIDO):
                        texto += " Resultado enviado para o aprendizado do modelo."
                    st.session_state["crm_msg"] = texto
                    st.rerun()

with aba_opp:
    execs = repositorio.usuarios("executivo")
    ids_exec = [e["id"] for e in execs]
    with st.form(f"opp_{lead_id}"):
        ids_catalogo = [sol["id"] for sol in catalogo.solucoes()]
        sugestoes = opp.get("solucoes") or (
            [lead["solucao_principal"]] if lead["solucao_principal"] else []
        )
        solucoes = st.multiselect(
            "Soluções propostas (catálogo Equifax)",
            ids_catalogo,
            default=[sol for sol in sugestoes if sol in ids_catalogo],
            format_func=catalogo.nome,
            placeholder="Selecione",
        )
        a, b, c = st.columns(3)
        valor = a.number_input(
            "Valor mensal estimado (R$)",
            min_value=0.0,
            step=500.0,
            value=crm_operacional.valor_seguro(opp.get("valor_mensal")),
        )
        atual_exec = opp.get("executivo_id") or lead["executivo_id"]
        opcoes_exec = [None, *ids_exec]
        nomes_exec = {e["id"]: e["nome"] for e in execs}
        executivo = b.selectbox(
            "Executivo responsável",
            opcoes_exec,
            format_func=lambda ident: nomes_exec.get(ident, "Não atribuído"),
            index=opcoes_exec.index(atual_exec) if atual_exec in opcoes_exec else 0,
        )
        prev_atual = opp.get("previsao_fechamento")
        previsao = c.date_input(
            "Previsão de fechamento",
            value=date.fromisoformat(prev_atual) if prev_atual else None,
            format="DD/MM/YYYY",
        )
        salvar = st.form_submit_button("Salvar oportunidade", type="primary")
    if salvar:
        try:
            comercial.salvar_oportunidade(lead_id, usuario, solucoes, valor or None, executivo,
                                          previsao.isoformat() if previsao else None)  # fmt: skip
        except ValueError as erro:
            st.error(str(erro))
        else:
            st.session_state["crm_msg"] = "Oportunidade salva."
            st.rerun()
    st.caption(
        "Valores informados representam estimativas comerciais; quando a empresa é da base demonstrativa, "
        "a oportunidade e seus valores são simulados."
    )

with aba_passagem:
    if opp.get("resumo_passagem"):
        st.text(opp["resumo_passagem"])
    else:
        st.caption("Ainda sem resumo. Ele é gerado quando o BDR qualifica e agenda a reunião.")
    if st.button("Gerar resumo de passagem", icon=":material/refresh:", disabled=not bool(opp)):
        with st.spinner("Gerando resumo de passagem..."):
            comercial.regerar_resumo(lead_id)
        st.session_state["crm_msg"] = "Resumo comercial atualizado."
        st.rerun()
    if not opp:
        st.caption("Salve uma oportunidade antes de gerar o resumo para o executivo.")

with aba_tempo:
    cores = {"Captura": "info", "Tratamento IA": "destaque", "Etapa": "", "Atividade do BDR": "alerta",
             "Human in the loop": "alerta", "Aprendizado": "destaque"}  # fmt: skip
    for ev in comercial.linha_do_tempo(lead_id):
        st.html(
            f'<div class="fg-cartao" style="padding:10px 14px">{ui.selo_html(ev["fase"], cores.get(ev["fase"], ""))} '
            f'<span style="color:var(--fg-texto-2)">{tempo.fmt(ev["quando"])}</span>'
            f'<p style="margin:6px 0 0 0">{html.escape(ev["texto"])}</p></div>'
        )
