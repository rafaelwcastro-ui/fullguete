"""CRM & funil: do primeiro contato ao fechamento, com a linha do tempo de ponta a ponta."""

from __future__ import annotations

import html
from datetime import date

import streamlit as st

import catalogo
from banco import consultas, repositorio
from nucleo import campanhas_ui, comercial, estados, tempo, ui

usuario = st.session_state["usuario"]

ui.cabecalho(
    "CRM & funil",
    "Fluxo finalizado: cada lead do primeiro contato até Ganho ou Perdido. O resultado volta para o modelo aprender.",
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

valores = consultas.valores_oportunidades()
funil = funil.assign(empresa=funil["nome_fantasia"].fillna(funil["razao_social"]),
                     valor=funil["id"].map(valores))  # fmt: skip

# ---------- kanban ----------
ui.rotulo("Kanban por etapa")
colunas = st.columns(len(estados.ETAPAS_FUNIL))
for coluna, etapa in zip(colunas, estados.ETAPAS_FUNIL, strict=True):
    grupo = funil[funil["etapa"] == etapa]
    total = grupo["valor"].fillna(0).sum()
    with coluna:
        st.html(
            f'<div class="fg-cartao"><b>{html.escape(etapa)}</b><br>'
            f'<span style="color:var(--fg-texto-2)">{len(grupo)} lead(s)'
            + (f" · R$ {total:,.0f}/mês".replace(",", ".") if total else "")
            + "</span></div>"
        )
        for r in grupo.head(8).itertuples():
            valor = f"R$ {r.valor:,.0f}/mês".replace(",", ".") if r.valor == r.valor and r.valor else ""
            st.html(
                f'<div class="fg-cartao" style="padding:10px 12px"><b>{html.escape(r.empresa)}</b><br>'
                f'<span style="color:var(--fg-texto-2)">{html.escape(catalogo.nome(r.solucao_principal or ""))}</span>'
                + (f"<br>{valor}" if valor else "")
                + "</div>"
            )
        if len(grupo) > 8:
            st.caption(f"Mais {len(grupo) - 8}.")

# ---------- lead selecionado ----------
st.divider()
opcoes = {int(r.id): f"#{r.id} {r.empresa} · {r.etapa} · {r.tags}" for r in funil.itertuples()}
padrao = st.session_state.get("crm_lead")
lead_id = st.selectbox("Abrir lead", list(opcoes), format_func=opcoes.get,
                       index=list(opcoes).index(padrao) if padrao in opcoes else 0)  # fmt: skip
st.session_state["crm_lead"] = lead_id
lead = consultas.lead(lead_id)
opp = consultas.oportunidade(lead_id) or {}

aba_mover, aba_opp, aba_passagem, aba_tempo = st.tabs(
    ["Mover de etapa", "Oportunidade", "Passagem ao executivo", "Linha do tempo"]
)

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
        solucoes = st.multiselect("Soluções propostas (catálogo Equifax)", [s["id"] for s in catalogo.solucoes()], format_func=catalogo.nome,
            default=opp.get("solucoes") or ([lead["solucao_principal"]] if lead["solucao_principal"] else []), placeholder="Selecione")  # fmt: skip
        a, b, c = st.columns(3)
        valor = a.number_input("Valor estimado mensal (R$, fictício)", min_value=0.0, step=500.0,
                               value=float(opp.get("valor_mensal") or 0))  # fmt: skip
        atual_exec = opp.get("executivo_id") or lead["executivo_id"]
        executivo = b.selectbox("Executivo responsável", ids_exec, format_func={e["id"]: e["nome"] for e in execs}.get,
                                index=ids_exec.index(atual_exec) if atual_exec in ids_exec else 0)  # fmt: skip
        prev_atual = opp.get("previsao_fechamento")
        previsao = c.date_input("Previsão de fechamento", value=date.fromisoformat(prev_atual) if prev_atual else None,
                                format="DD/MM/YYYY")  # fmt: skip
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
    st.caption("Valores fictícios, só para a demonstração do funil e da receita prevista.")

with aba_passagem:
    if opp.get("resumo_passagem"):
        st.text(opp["resumo_passagem"])
    else:
        st.caption("Ainda sem resumo. Ele é gerado quando o BDR qualifica e agenda a reunião.")
    if st.button("Gerar resumo de novo", icon=":material/refresh:"):
        if opp:
            with st.spinner("Gerando..."):
                comercial.regerar_resumo(lead_id)
            st.rerun()
        else:
            st.warning("Crie a oportunidade antes de gerar o resumo.")

with aba_tempo:
    cores = {"Captura": "info", "Tratamento IA": "destaque", "Etapa": "", "Atividade do BDR": "alerta",
             "Human in the loop": "alerta", "Aprendizado": "destaque"}  # fmt: skip
    for ev in comercial.linha_do_tempo(lead_id):
        st.html(
            f'<div class="fg-cartao" style="padding:10px 14px">{ui.selo_html(ev["fase"], cores.get(ev["fase"], ""))} '
            f'<span style="color:var(--fg-texto-2)">{tempo.fmt(ev["quando"])}</span>'
            f'<p style="margin:6px 0 0 0">{html.escape(ev["texto"])}</p></div>'
        )
