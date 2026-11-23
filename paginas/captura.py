"""Captura de leads: ponto de entrada único, com as regras de entrada visíveis."""

from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from dados import busca_cnpj, cnpja, cnpjws, ingestao, limpeza
from dados import cnpj as cnpj_util
from dados.features import INTERESSES, PORTES
from nucleo import config, ui

usuario = st.session_state["usuario"]
ator = usuario["login"]

ui.cabecalho(
    "Captura de leads",
    "Todo lead entra por aqui. Cada registro é gravado como chegou e depois limpo, deduplicado e separado dos "
    "dados pessoais do contato.",
    secao="Prospecção",
)

BASES_LEGAIS = {
    "consentimento": "Consentimento do titular",
    "legitimo_interesse": "Legítimo interesse (contato B2B)",
    "sem_base": "Sem base legal ainda",
}
ORIGENS_FORM = ["site", "evento", "indicacao", "linkedin", "formulario"]


def _mostrar_resultado(resultado: ingestao.ResultadoIngestao) -> None:
    if resultado.criados:
        st.success(resultado.resumo)
    else:
        st.warning(resultado.resumo)
    for nome, lead_id in resultado.duplicados:
        st.caption(f"{nome}: já existe como lead #{lead_id}.")
    for nome, motivo in resultado.rejeitados:
        st.caption(f"{nome}: {motivo}.")
    if resultado.criados:
        st.session_state["captura_ultimos"] = resultado.criados
        _apos_captura(resultado.criados)


def _tratar(lead_ids: list[int]) -> None:
    from ia import orquestrador

    barra = st.progress(0.0, text="Enviando para os agentes...")
    resumo = orquestrador.tratar(lead_ids, ator, progresso=lambda etapa, p: barra.progress(min(p, 1.0), text=etapa))
    barra.empty()
    destinos = "; ".join(f"{d}: {n}" for d, n in resumo["destinos"].items())
    st.session_state["captura_msg"] = f"Tratamento concluído. {destinos}. Veja os detalhes em Tratamento IA."
    st.rerun()


def _apos_captura(lead_ids: list[int]) -> None:
    if st.session_state.get("auto_tratar"):
        _tratar(lead_ids)


st.toggle(
    "Tratar automaticamente ao capturar",
    key="auto_tratar",
    help="Quando ligado, cada lead capturado segue direto para os agentes de IA.",
)


if msg := st.session_state.pop("captura_msg", None):
    st.success(msg)

aba_form, aba_planilha, aba_cnpj, aba_cnpja, aba_busca_real, aba_site, aba_base = st.tabs(
    [
        "Formulário manual",
        "Planilha",
        "CNPJs conhecidos",
        "Buscar empresas (CNPJá)",
        "LocalizaCNPJ (legado)",
        "Site / webhook (simulado)",
        "Base fictícia",
    ]
)

# ---------- formulário manual ----------
CAMPOS_FORM = ["razao_social", "nome_fantasia", "setor", "cnae", "porte", "cidade", "uf", "site", "descricao"]


def _buscar_cnpj() -> None:
    numero = st.session_state.get("f_cnpj", "")
    st.session_state.pop("f_aviso", None)
    try:
        registro, do_cache = cnpjws.consultar(numero, config.token_cnpjws(), ingestao.cnpjs_ficticios())
    except (ValueError, cnpjws.ErroCaptura) as erro:
        st.session_state["f_aviso"] = ("erro", str(erro))
        return
    if registro is None:
        st.session_state["f_aviso"] = ("aviso", "CNPJ não encontrado no CNPJ.ws.")
        return
    for campo in CAMPOS_FORM:
        if registro.get(campo):
            st.session_state[f"f_{campo}"] = registro[campo]
    st.session_state["f_cnpjws"] = registro
    origem = "cache local" if do_cache else "CNPJ.ws"
    st.session_state["f_aviso"] = ("ok", f"Dados reais carregados do {origem}. Confira antes de salvar.")


with aba_form:
    c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
    c1.text_input("CNPJ", key="f_cnpj", placeholder="00.000.000/0000-00", max_chars=18)
    c2.button("Buscar dados", on_click=_buscar_cnpj, icon=":material/search:", width="stretch")
    st.caption(
        "A busca usa a API real do CNPJ.ws. Sem token, a API pública aceita 3 consultas por minuto. "
        "CNPJs da base fictícia não são enviados."
    )
    if aviso := st.session_state.get("f_aviso"):
        tipo, texto = aviso
        {"erro": st.error, "aviso": st.warning, "ok": st.success}[tipo](texto)

    with st.form("form_lead", clear_on_submit=False):
        ui.rotulo("Empresa")
        a, b = st.columns(2)
        a.text_input("Razão social", key="f_razao_social", max_chars=150)
        b.text_input("Nome fantasia", key="f_nome_fantasia", max_chars=150)
        a, b, c = st.columns([2, 1, 1])
        a.text_input("Setor ou atividade principal", key="f_setor", max_chars=150)
        b.text_input("CNAE", key="f_cnae", max_chars=10)
        c.selectbox("Porte", ["", *PORTES], key="f_porte")
        a, b, c = st.columns([2, 1, 2])
        a.text_input("Cidade", key="f_cidade", max_chars=80)
        b.selectbox("UF", ["", *sorted(limpeza.UFS)], key="f_uf")
        c.text_input("Site", key="f_site", max_chars=120)
        st.text_area("Descrição da empresa", key="f_descricao", max_chars=1000,
                     placeholder="O que a empresa faz, como vende, que dores relatou.")  # fmt: skip

        ui.rotulo("Contato (dados pessoais, nunca vão para a IA)")
        a, b = st.columns(2)
        contato_nome = a.text_input("Nome do contato", max_chars=100)
        cargo = b.text_input("Cargo", max_chars=80)
        a, b = st.columns(2)
        email = a.text_input("E-mail", max_chars=120)
        telefone = b.text_input("Telefone", max_chars=20)

        ui.rotulo("Interesse e origem")
        a, b = st.columns(2)
        interesse = a.selectbox("Interesse declarado", INTERESSES, index=len(INTERESSES) - 1)
        origem = b.selectbox("Origem", ORIGENS_FORM, format_func=ingestao.ORIGENS_ROTULO.get)
        observacao = st.text_input("Observação", max_chars=300)

        ui.rotulo("LGPD")
        base_legal = st.radio("Base legal para contato", list(BASES_LEGAIS), format_func=BASES_LEGAIS.get,
                              horizontal=True)  # fmt: skip
        consentiu = st.checkbox("O titular autorizou o contato comercial (registro do consentimento)")
        salvar = st.form_submit_button("Capturar lead", type="primary", icon=":material/add:")

    if salvar:
        estado = st.session_state
        if base_legal == "consentimento" and not consentiu:
            st.error("Marque o registro do consentimento ou escolha outra base legal.")
        else:
            registro = {campo: estado.get(f"f_{campo}", "") for campo in CAMPOS_FORM}
            registro.update(
                cnpj=estado.get("f_cnpj", ""), contato_nome=contato_nome, cargo=cargo, email=email,
                telefone=telefone, interesse=interesse, origem=origem, observacao=observacao,
                base_legal=base_legal, consentimento="sim" if consentiu else "",
            )  # fmt: skip
            buscado = estado.get("f_cnpjws") or {}
            if buscado and cnpj_util.so_digitos(buscado.get("cnpj")) == cnpj_util.so_digitos(registro["cnpj"]):
                registro["dados_cnpjws"] = buscado.get("dados_cnpjws")
                registro["situacao_cadastral"] = buscado.get("situacao_cadastral")
            _mostrar_resultado(ingestao.receber([registro], "formulario", ator))

# ---------- planilha ----------
with aba_planilha:
    st.caption("CSV ou Excel. As colunas são reconhecidas por nomes comuns. Revise os problemas antes de importar.")
    arquivo = st.file_uploader("Planilha de leads", type=["csv", "xlsx", "xls"])
    exemplo = config.RAIZ / "data" / "exemplo_leads.csv"
    if exemplo.exists():
        st.download_button("Baixar planilha de exemplo", exemplo.read_bytes(), "exemplo_leads.csv", "text/csv",
                           on_click="ignore")  # fmt: skip
    if arquivo is not None:
        try:
            registros, previa, rel = limpeza.preparar_planilha(limpeza.ler_planilha(arquivo, arquivo.name))
        except Exception as erro:  # arquivo corrompido ou sem coluna de empresa
            st.error(f"Não consegui ler a planilha: {erro}")
        else:
            st.markdown(f"**{rel['linhas']}** linhas. Colunas reconhecidas: {', '.join(rel['colunas_reconhecidas'])}.")
            if rel["colunas_ignoradas"]:
                st.caption(f"Ignoradas: {', '.join(rel['colunas_ignoradas'])}.")
            if rel["com_problemas"]:
                st.warning(f"{rel['com_problemas']} linha(s) com problemas. Veja a coluna Problemas.")
            st.dataframe(previa, hide_index=True, width="stretch", column_config={
                "empresa": "Empresa", "cnpj": "CNPJ", "uf": "UF", "base_legal": "Base legal",
                "problemas": st.column_config.TextColumn("Problemas", width="large"),
            })  # fmt: skip
            if st.button(f"Importar {len(registros)} linha(s)", type="primary", key="importar_planilha"):
                for r in registros:
                    r["origem"] = r.get("origem") or "planilha"
                _mostrar_resultado(ingestao.receber(registros, "planilha", ator))

# ---------- CNPJs conhecidos ----------
with aba_cnpj:
    token = config.token_cnpjws()
    limite = cnpjws.MAX_LISTA_COMERCIAL if token else cnpjws.MAX_LISTA_PUBLICA
    st.caption(
        f"Cole uma lista de CNPJs. Os dados vêm do CNPJ.ws. Até {limite} CNPJs novos por vez"
        + ("." if token else " sem token (limite da API pública); os já consultados saem do cache.")
    )
    with st.form("form_cnpjs"):
        lista = st.text_area("CNPJs", placeholder="Um por linha ou separados por vírgula", max_chars=2000)
        consultar = st.form_submit_button("Consultar e capturar", type="primary")
    if consultar:
        try:
            with st.spinner("Consultando o CNPJ.ws..."):
                saida = cnpjws.consultar_lista(lista, token, ingestao.cnpjs_ficticios())
        except (ValueError, cnpjws.ErroCaptura) as erro:
            st.error(str(erro))
        else:
            for numero, erro in saida["erros"]:
                st.caption(f"{numero}: {erro}")
            if saida["nao_encontrados"]:
                st.caption(f"Não encontrados: {', '.join(saida['nao_encontrados'])}.")
            if saida["encontrados"]:
                registros = [{**r, "origem": "cnpj_lista", "base_legal": "legitimo_interesse"}
                             for r in saida["encontrados"]]  # fmt: skip
                _mostrar_resultado(ingestao.receber(registros, "cnpj_lista", ator))
                st.caption(
                    "Leads vindos de lista entram com base legal de legítimo interesse (contato B2B). "
                    "Revise em Governança & LGPD se for o caso."
                )
    with st.expander("Busca por CNAE e região (filtro opcional, exige token comercial)"):
        st.caption("A região serve só para filtrar a busca. Ela não entra no cálculo da nota.")
        a, b, c = st.columns([2, 1, 1])
        cnae = a.text_input("CNAE principal", placeholder="Ex.: 4639701", max_chars=10)
        uf = b.selectbox("UF (filtro)", ["", *sorted(cnpjws.UF_IBGE)], format_func=lambda s: s or "Todas")
        qtd = c.number_input("Máximo", 1, cnpjws.MAX_LISTA_COMERCIAL, 10)
        if st.button("Buscar CNPJs", disabled=not token):
            try:
                achados = cnpjws.pesquisar(token, cnae=cnae, uf=uf, limite=int(qtd))
            except (ValueError, cnpjws.ErroCaptura) as erro:
                st.error(str(erro))
            else:
                st.code("\n".join(achados) or "Nada encontrado.")
                st.caption("Copie os CNPJs para a lista acima para capturar.")
        if not token:
            st.caption("Configure CNPJ_WS_TOKEN no .env para liberar a busca.")

# ---------- CNPJá Comercial: pesquisa de empresas por filtros ----------
with aba_cnpja:
    st.markdown("#### Descobrir empresas reais — CNPJá Comercial")
    st.caption(
        "Pesquisa real de CNPJs por município IBGE, CNAE e abertura, "
        "com verificação de saldo e importação seletiva. Não usa a LocalizaCNPJ."
    )
    chave_salva = config.token_cnpja()
    if chave_salva:
        st.success("Chave CNPJá configurada nos Secrets do servidor.")
    else:
        st.text_input(
            "Chave da API CNPJá Comercial",
            type="password",
            key="cnpja_chave_sessao",
            help="A chave não fica gravada nos leads nem no repositório. Use a API Comercial, não a API Pública.",
        )
    chave_cnpja = chave_salva or st.session_state.get("cnpja_chave_sessao", "")
    if st.button(
        "Validar chave e consultar saldo (grátis)",
        key="cnpja_validar",
        disabled=not bool(chave_cnpja),
        icon=":material/key:",
    ):
        try:
            saldo = cnpja.saldo(chave_cnpja)
        except cnpja.ErroCnpja as erro:
            st.error(str(erro))
        else:
            st.success("Chave reconhecida pela CNPJá (HTTP 200).")
            st.caption(f"Créditos mensais: {saldo['transient']} · Acumulados: {saldo['perpetual']}")

    st.info(
        "A busca comercial consome 1 crédito a cada 10 registros retornados. "
        "Comece com 10 empresas. O filtro 'Varejo' utiliza CNAEs exemplificativos, "
        "não representa todo o varejo. Você pode informar CNAEs específicos."
    )
    with st.form("cnpja_pesquisa_comercial"):
        a, b, c = st.columns([1.3, 2, 0.8])
        segmento_c = a.selectbox("Segmento / tag", list(cnpja.SEGMENTOS), index=1)
        cidade_c = b.text_input("Cidade", value="Campinas", max_chars=100)
        uf_c = c.selectbox("UF", sorted(limpeza.UFS), index=sorted(limpeza.UFS).index("SP"))
        a, b, c = st.columns([1, 1, 1.5])
        mes_c = a.selectbox(
            "Mês de abertura",
            list(range(1, 13)),
            index=3,
            format_func=lambda m: cnpja.MESES[m - 1],
        )
        ano_c = b.number_input("Ano de abertura", min_value=2000, max_value=2100, value=2026)
        codigos_c = c.text_input("CNAE(s), opcional", placeholder="Ex.: 4711302,4781400", max_chars=110)
        a, b, c = st.columns([1, 1.2, 2.2])
        limite_c = a.selectbox("Por página", [1, 5, 10, 20, 50], index=2)
        ibge_c = b.text_input(
            "Código IBGE (opcional)", max_chars=7,
            help="Preencher apenas se souber o código; vazio, buscamos pelo nome da cidade no IBGE.",
        )
        enviar_c = c.form_submit_button(
            "Pesquisar CNPJs na CNPJá",
            type="primary",
            disabled=not bool(chave_cnpja),
            width="stretch",
            icon=":material/search:",
        )
    if enviar_c:
        st.session_state.pop("cnpja_pagina", None)
        st.session_state.pop("cnpja_filtros", None)
        try:
            codigo_c = int(ibge_c) if ibge_c.strip() else cnpja.municipio_ibge(cidade_c, uf_c)
            parametros_c = cnpja.filtros(
                segmento_c, uf_c, codigo_c, int(ano_c), mes_c, codigos_c, limite_c
            )
            with st.spinner("Consultando a base real de estabelecimentos CNPJá..."):
                resultado_c = cnpja.pesquisar(chave_cnpja, parametros_c)
        except (ValueError, cnpja.ErroCnpja) as erro:
            st.error(str(erro))
        else:
            st.session_state["cnpja_pagina"] = resultado_c
            st.session_state["cnpja_filtros"] = parametros_c

    pagina_c = st.session_state.get("cnpja_pagina")
    if pagina_c is not None:
        st.divider()
        st.caption(
            f"Resposta da API: {pagina_c.recebidas} registro(s) recebidos, "
            f"{pagina_c.rejeitadas} rejeitado(s) por ausência de CNPJ/razão social. "
            f"Total informado pela fonte: {pagina_c.total}."
        )
        if not pagina_c.empresas:
            st.warning(
                "A consulta retornou zero empresas aproveitáveis. "
                "Confira o período, o CNAE e o código IBGE do município."
            )
        else:
            dados_c = pd.DataFrame(pagina_c.empresas)
            colunas_c = [
                "cnpj",
                "razao_social",
                "nome_fantasia",
                "cidade",
                "uf",
                "cnae",
                "setor",
                "data_abertura",
            ]
            st.dataframe(
                dados_c[colunas_c],
                hide_index=True,
                width="stretch",
            )
            st.download_button(
                "Exportar CSV",
                dados_c[colunas_c].to_csv(sep=";", index=False).encode("utf-8-sig"),
                "cnpja_empresas_reais.csv",
                "text/csv",
                on_click="ignore",
                icon=":material/download:",
            )
            opcoes_c = {empresa["cnpj"]: empresa for empresa in pagina_c.empresas}
            escolhidos_c = st.multiselect(
                "Importar para o Fullguete",
                list(opcoes_c),
                default=list(opcoes_c),
                format_func=lambda n: f"{opcoes_c[n]['razao_social']} — {n}",
                key="cnpja_selecao",
            )
            st.warning(
                "CNPJ público não constitui consentimento para contato. "
                "Os novos registros entram sem base legal de contato até análise."
            )
            if st.button(
                f"Importar {len(escolhidos_c)} empresa(s)",
                disabled=not bool(escolhidos_c),
                key="cnpja_importar",
            ):
                registros_c = [opcoes_c[numero] for numero in escolhidos_c]
                _mostrar_resultado(ingestao.receber(registros_c, "cnpja", ator))

        if pagina_c.next_token and st.button(
            "Carregar próxima página (consome créditos)", key="cnpja_proxima"
        ):
            try:
                with st.spinner("Consultando próxima página..."):
                    proximo_c = cnpja.pesquisar(chave_cnpja, {"token": pagina_c.next_token})
            except cnpja.ErroCnpja as erro:
                st.error(str(erro))
            else:
                existentes_c = {item["cnpj"]: item for item in pagina_c.empresas}
                existentes_c.update({item["cnpj"]: item for item in proximo_c.empresas})
                proximo_c.empresas = list(existentes_c.values())
                proximo_c.recebidas += pagina_c.recebidas
                proximo_c.rejeitadas += pagina_c.rejeitadas
                st.session_state["cnpja_pagina"] = proximo_c
                st.rerun()


# ---------- descoberta de CNPJs reais por filtros ----------
with aba_busca_real:
    st.markdown("#### Buscar empresas reais na base de CNPJs")
    st.caption(
        "Descubra estabelecimentos por atividade, cidade e mês de abertura. "
        "A consulta é feita na base da Receita Federal organizada pelo provedor LocalizaCNPJ. "
        "Os resultados não são fictícios e não são capturados automaticamente."
    )
    chave_configurada = config.token_localizacnpj()
    if chave_configurada:
        st.success("API de pesquisa configurada nos Secrets do portal.")
    else:
        st.info(
            "Esta pesquisa usa uma chave gratuita da LocalizaCNPJ. "
            "Cadastre sua chave no provedor e informe-a abaixo. "
            "O plano Free possui limites de uso."
        )
        st.markdown("[Documentação e cadastro da API LocalizaCNPJ](https://api.localizacnpj.com.br/)")
        st.text_input(
            "Chave de API gratuita",
            type="password",
            key="busca_real_chave",
            help="Usada apenas na sessão, enviada ao provedor pelo servidor; não é gravada na base de leads.",
        )
    chave = chave_configurada or st.session_state.get("busca_real_chave", "")

    if st.button("Verificar conexão com a API", disabled=not bool(chave), icon=":material/check_circle:"):
        try:
            conta = busca_cnpj.verificar_conexao(chave)
        except busca_cnpj.ErroBusca as erro:
            st.error(str(erro))
        else:
            if conta["ativa"]:
                st.success(f"Conexão autenticada. Plano: {conta['plano']}. Conta ativa.")
            else:
                st.warning("A chave foi reconhecida, mas a conta não consta como ativa.")

    with st.form("buscar_cnpjs_reais"):
        st.markdown("**Filtros da prospecção**")
        a, b, c = st.columns([1.5, 2, 0.8])
        segmento = a.selectbox("Tag de segmento", list(busca_cnpj.SEGMENTOS), index=0)
        cidade = b.text_input("Cidade", value="Campinas", max_chars=100)
        uf = c.selectbox("UF", sorted(limpeza.UFS), index=sorted(limpeza.UFS).index("SP"))
        a, b, c = st.columns([1.2, 1, 1.4])
        mes = a.selectbox(
            "Mês de abertura",
            list(range(1, 13)),
            index=3,
            format_func=lambda m: busca_cnpj.MESES[m - 1],
        )
        ano = b.number_input("Ano de abertura", min_value=2000, max_value=2100, value=2026)
        cnae = c.text_input("CNAE (opcional, substitui a tag)", placeholder="Ex.: 4711302", max_chars=10)
        a, b, c = st.columns([1.2, 2, 1.6])
        limite = a.selectbox("Resultados por página", [10, 25, 50, 100], index=1)
        buscar_real = b.form_submit_button(
            "Buscar empresas reais",
            type="primary",
            icon=":material/search:",
            disabled=not bool(chave),
            width="stretch",
        )
        diagnosticar_real = c.form_submit_button(
            "Diagnóstico técnico",
            icon=":material/monitor_heart:",
            disabled=not bool(chave),
            width="stretch",
        )
    st.write("Filtros:", segmento, f"{cidade}/{uf}", f"Abertura: {busca_cnpj.MESES[mes - 1]}/{ano}")
    st.caption(
        "O diagnóstico testa a conta, a saúde da base e uma busca mínima "
        "(primeiro dia do mês, CNAE 4711302, limite 1). "
        "Consome uma consulta da cota da API; Health Check tem limite próprio."
    )

    if diagnosticar_real:
        st.markdown("**Diagnóstico do serviço LocalizaCNPJ**")
        try:
            conta = busca_cnpj.verificar_conexao(chave)
        except busca_cnpj.ErroBusca as erro:
            st.error(f"Autenticação: {erro}")
        else:
            if not conta["ativa"]:
                st.error("A chave existe, mas o provedor indica conta inativa.")
            else:
                st.success(f"Autenticação OK · plano {conta['plano']}.")
                with st.spinner("Verificando a saúde da base e a consulta mínima..."):
                    saude = busca_cnpj.verificar_saude()
                    filtros_teste = busca_cnpj.filtros_diagnostico(cidade, uf, int(ano), mes)
                    try:
                        amostra = busca_cnpj.buscar(chave, filtros_teste)
                    except busca_cnpj.ErroBusca as erro:
                        resultado_teste = {"erro": str(erro), "http": erro.status_code}
                    else:
                        resultado_teste = {"encontrados": amostra.total_api, "http": 200}

                estado_base = saude["db_ready"]
                if estado_base is True:
                    st.info("Health Check: banco acessível no provedor (HTTP 200).")
                elif estado_base is False:
                    st.error("Health Check: o banco do provedor não está pronto.")
                else:
                    st.warning(f"Health Check: {saude['aviso']} HTTP: {saude['http'] or 'sem resposta'}.")

                if resultado_teste["http"] == 200:
                    st.success(
                        "Busca mínima bem-sucedida (HTTP 200). "
                        f"Empresas retornadas: {resultado_teste['encontrados']}. "
                        "Se a consulta mensal falha com 503, o custo da busca ampla é a causa provável."
                    )
                elif resultado_teste["http"] == 503:
                    st.error(
                        "Busca mínima também falhou com HTTP 503. "
                        "Mesmo com um dia e um CNAE específico, o fornecedor não concluiu a consulta. "
                        "É necessário suporte ou uma fonte alternativa de dados."
                    )
                else:
                    st.error(
                        f"Busca mínima falhou (HTTP {resultado_teste['http'] or 'sem resposta'}). "
                        f"{resultado_teste['erro']}"
                    )
                with st.expander("Filtros exatos do teste (sem chave)"):
                    st.json(filtros_teste)

    if buscar_real:
        for estado in (
            "busca_real_resultados",
            "busca_real_cursor",
            "busca_real_mais",
            "busca_real_filtros",
            "busca_real_total_api",
            "busca_real_descartados",
        ):
            st.session_state.pop(estado, None)
        try:
            filtros = busca_cnpj.parametros(segmento, cidade, uf, int(ano), mes, cnae, limite=limite)
            with st.spinner("Consultando registros reais de CNPJ..."):
                pagina = busca_cnpj.buscar(chave, filtros)
        except (ValueError, busca_cnpj.ErroBusca) as erro:
            st.error(str(erro))
        else:
            st.session_state["busca_real_filtros"] = filtros
            st.session_state["busca_real_resultados"] = pagina.registros
            st.session_state["busca_real_cursor"] = pagina.next_cursor
            st.session_state["busca_real_mais"] = pagina.has_more
            st.session_state["busca_real_snapshot"] = pagina.snapshot
            st.session_state["busca_real_total_api"] = pagina.total_api
            st.session_state["busca_real_descartados"] = pagina.descartados
            st.session_state.pop("busca_real_selecionados", None)

    registros_reais = st.session_state.get("busca_real_resultados")
    if registros_reais is not None:
        st.divider()
        filtros_usados = st.session_state.get("busca_real_filtros") or {}
        st.caption(
            "Filtros enviados à API: "
            f"cidade={filtros_usados.get('cidade')}, UF={filtros_usados.get('uf')}, "
            f"abertura={filtros_usados.get('abertura_de')} a "
            f"{filtros_usados.get('abertura_ate')}, situação={filtros_usados.get('situacao')}."
        )
        recebidos = st.session_state.get("busca_real_total_api", 0)
        descartados = st.session_state.get("busca_real_descartados", 0)
        if not registros_reais:
            if recebidos:
                st.error(
                    f"A API devolveu {recebidos} registro(s), mas nenhum tinha CNPJ e razão social "
                    "no formato esperado. O problema é a interpretação dos dados, não seus filtros."
                )
            else:
                st.warning(
                    "A API respondeu com sucesso, mas não encontrou empresas para os filtros enviados. "
                    "Experimente outro mês ou CNAE; os nomes de cidade agora são normalizados sem acentos."
                )
        else:
            st.success(f"{len(registros_reais)} empresas reais carregadas nesta pesquisa.")
            if descartados:
                st.warning(f"{descartados} registro(s) da API foram ignorados por dados cadastrais incompletos.")
            snapshot = st.session_state.get("busca_real_snapshot") or "não informado"
            st.caption(
                f"Base do provedor: {snapshot}. Quantidade exibida é parcial quando há mais páginas. "
                "Data de abertura significa início da atividade do estabelecimento."
            )
            tabela = pd.DataFrame(registros_reais)
            colunas = [
                "cnpj",
                "razao_social",
                "nome_fantasia",
                "cidade",
                "uf",
                "cnae",
                "setor",
                "data_abertura",
                "porte",
            ]
            tabela = tabela[colunas].rename(
                columns={
                    "cnpj": "CNPJ",
                    "razao_social": "Razão social",
                    "nome_fantasia": "Fantasia",
                    "cidade": "Cidade",
                    "uf": "UF",
                    "cnae": "CNAE",
                    "setor": "Atividade",
                    "data_abertura": "Abertura",
                    "porte": "Porte",
                }
            )
            st.dataframe(tabela, width="stretch", hide_index=True)
            st.download_button(
                "Exportar resultados CSV",
                tabela.to_csv(sep=";", index=False).encode("utf-8-sig"),
                "fullguete_cnpjs_reais.csv",
                "text/csv",
                on_click="ignore",
                icon=":material/download:",
            )

            st.markdown("**Importar resultados para a captura de leads**")
            por_cnpj = {r["cnpj"]: r for r in registros_reais}
            selecionar = st.multiselect(
                "Empresas que deseja importar",
                list(por_cnpj),
                default=list(por_cnpj),
                format_func=lambda numero: f"{por_cnpj[numero]['razao_social']} · {numero}",
            )
            st.warning(
                "Dados cadastrais públicos não significam consentimento para contato. "
                "Por padrão, os leads são retidos até validação da base legal."
            )
            legitimo = st.checkbox(
                "Analisei e documentei a finalidade, a necessidade e o legítimo interesse para contato B2B "
                "dessas empresas.",
                key="busca_real_legitimo",
            )
            if st.button(
                f"Importar {len(selecionar)} empresas selecionadas",
                type="primary",
                disabled=not bool(selecionar),
                icon=":material/add_business:",
            ):
                registros = []
                for numero in selecionar:
                    empresa = {**por_cnpj[numero]}
                    empresa["base_legal"] = "legitimo_interesse" if legitimo else "sem_base"
                    empresa["consentimento"] = ""
                    registros.append(empresa)
                _mostrar_resultado(ingestao.receber(registros, "busca_cnpj", ator))

        if (
            st.session_state.get("busca_real_mais")
            and st.session_state.get("busca_real_cursor")
            and st.button("Carregar próxima página", icon=":material/arrow_forward:")
        ):
            try:
                filtros = {
                    **st.session_state["busca_real_filtros"],
                    "cursor": st.session_state["busca_real_cursor"],
                }
                with st.spinner("Carregando mais empresas..."):
                    proxima = busca_cnpj.buscar(chave, filtros)
            except busca_cnpj.ErroBusca as erro:
                st.error(str(erro))
            else:
                existentes = {r["cnpj"]: r for r in st.session_state["busca_real_resultados"]}
                existentes.update({r["cnpj"]: r for r in proxima.registros})
                st.session_state["busca_real_resultados"] = list(existentes.values())
                st.session_state["busca_real_cursor"] = proxima.next_cursor
                st.session_state["busca_real_mais"] = proxima.has_more
                st.session_state["busca_real_snapshot"] = proxima.snapshot
                st.session_state["busca_real_total_api"] += proxima.total_api
                st.session_state["busca_real_descartados"] += proxima.descartados
                st.session_state.pop("busca_real_selecionados", None)
                st.rerun()

# ---------- site / webhook simulado ----------
with aba_site:
    st.html(ui.selo_simulado())
    st.caption(
        "Simula o formulário do site enviando leads para um webhook, um a um, como em produção. "
        "Os leads vêm da base fictícia."
    )
    disponiveis = len(ingestao.ficticias_disponiveis())
    a, b = st.columns([1, 3], vertical_alignment="bottom")
    quantos = a.number_input("Quantos leads", 1, max(1, min(30, disponiveis)), min(10, max(1, disponiveis)))
    if b.button("Simular chegada de leads", type="primary", icon=":material/bolt:", disabled=disponiveis == 0):
        painel = st.empty()
        chegaram: list[dict] = []
        criados: list[int] = []
        for empresa in ingestao.ficticias_disponiveis()[: int(quantos)]:
            registro = {**ingestao.registro_ficticio(empresa), "origem": "site"}
            r = ingestao.receber([registro], "webhook_site", "webhook_site", ficticio=True)
            criados += r.criados
            chegaram.insert(0, {"hora": time.strftime("%H:%M:%S"), "empresa": empresa["nome_fantasia"],
                                "status": "Recebido" if r.criados else "Rejeitado"})  # fmt: skip
            painel.dataframe(pd.DataFrame(chegaram), hide_index=True, width="stretch")
            time.sleep(0.35)
        st.success(f"{len(criados)} lead(s) chegaram pelo site.")
        if criados:
            st.session_state["captura_ultimos"] = criados
            _apos_captura(criados)
    if disponiveis == 0:
        st.info("Todas as empresas da base fictícia já entraram no funil.")

# ---------- base fictícia ----------
with aba_base:
    st.html(ui.selo_simulado("Base fictícia"))
    disponiveis = len(ingestao.ficticias_disponiveis())
    st.caption(
        f"{disponiveis} de 150 empresas fictícias ainda não entraram. Nomes, CNPJs e contatos são inventados; "
        "os CNPJs nunca vão para a API."
    )
    a, b = st.columns([1, 3], vertical_alignment="bottom")
    qtd_base = a.number_input("Quantidade", 1, max(1, disponiveis), min(40, max(1, disponiveis)))
    if b.button("Carregar base fictícia", disabled=disponiveis == 0):
        _mostrar_resultado(ingestao.carregar_ficticias(int(qtd_base), ator))

    from dados import cenario_demo

    if not cenario_demo.montado():
        st.divider()
        st.caption(
            "Cenário de demonstração: captura e trata 100 empresas fictícias, espalha as datas pelo último mês e "
            "simula o trabalho dos BDRs (contatos, reuniões, ganhos e perdas)."
        )
        if st.button("Montar cenário de demonstração", disabled=disponiveis < cenario_demo.QUANTIDADE):
            with st.spinner("Montando um mês fictício de operação..."):
                r = cenario_demo.montar(ator)
            st.success(f"Cenário pronto: {r['leads']} leads, {r['reunioes']} reuniões, {r['ganhos']} ganhos.")

# ---------- entrada em tempo real ----------
st.divider()
ui.rotulo("Entrada em tempo real")
recentes = ingestao.entrada_recente(40)
if recentes:
    tabela = pd.DataFrame(recentes)
    tabela["empresa"] = [
        f"{e}  (fictícia)" if f else e for e, f in zip(tabela["empresa"], tabela["ficticio"], strict=False)
    ]
    st.dataframe(
        tabela[["recebido_em", "empresa", "canal", "status", "etapa", "problemas"]],
        hide_index=True,
        width="stretch",
        column_config={
            "recebido_em": "Recebido em", "empresa": "Empresa", "canal": "Canal", "status": "Status",
            "etapa": "Etapa do lead", "problemas": st.column_config.TextColumn("Problemas", width="large"),
        },
    )  # fmt: skip
else:
    st.info("Nenhum lead recebido ainda.")

from banco import consultas  # noqa: E402
from nucleo import estados  # noqa: E402

pendentes = consultas.leads([estados.CAPTURADO])
if not pendentes.empty:
    a, b = st.columns([3, 1], vertical_alignment="center")
    a.markdown(f"**{len(pendentes)}** lead(s) capturados aguardando tratamento.")
    if b.button("Enviar para tratamento", type="primary", icon=":material/psychology:", width="stretch"):
        _tratar(pendentes["id"].tolist())

with st.expander("Regras de entrada"):
    for regra in ingestao.REGRAS_ENTRADA:
        st.markdown(f"- {regra}")
