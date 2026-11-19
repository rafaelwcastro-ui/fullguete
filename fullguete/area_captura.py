"""Formulário de captura e revisão da base empresarial."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import captura, dados

BUSCA = "Buscar empresas por filtros"
CONSULTA = "Consultar CNPJs conhecidos"


def exibir(token: str, ufs: list[str]) -> tuple[pd.DataFrame | None, str]:
    modo = st.radio("Tipo de captura", (BUSCA, CONSULTA), horizontal=True)
    busca = modo == BUSCA
    if busca and not token:
        st.info(
            "A busca de empresas por filtros usa a API Comercial Premium do CNPJ.ws. "
            "Configure CNPJ_WS_TOKEN nos Secrets. Para testar sem token, use Consultar CNPJs conhecidos."
        )
    with st.form(f"captura_cnpj_{modo}"):
        if busca:
            a, b, c = st.columns([1, 1, 1.4])
            cnae = a.text_input("CNAE principal", placeholder="Ex. 4711302", max_chars=16)
            uf = b.selectbox("UF", ["", *ufs], format_func=lambda sigla: sigla or "Todas")
            cidade = c.text_input("Código IBGE do município", placeholder="Opcional", max_chars=7)
            limite = st.number_input("Máximo de empresas", min_value=1, max_value=captura.MAX_PESQUISA, value=10)
            st.caption("A captura busca CNPJs ativos e consulta o cadastro das empresas encontradas.")
            enviar = st.form_submit_button("Buscar empresas", type="primary", disabled=not token)
        else:
            maximo = captura.MAX_PESQUISA if token else captura.MAX_PUBLICA
            cnpjs = st.text_area("CNPJs", placeholder="Um por linha ou separados por vírgula", max_chars=600)
            st.caption(f"Até {maximo} CNPJs por consulta.")
            enviar = st.form_submit_button("Consultar CNPJs", type="primary")
    estado = f"captura_resultado_{modo}"
    if enviar:
        st.session_state.pop(estado, None)
        try:
            with st.spinner("Buscando cadastros no CNPJ.ws…"):
                resposta = (
                    captura.pesquisar(token, cnae=cnae, uf=uf, cidade_ibge=cidade, limite=limite)
                    if busca else captura.consultar_cnpjs(cnpjs, token=token)
                )
                st.session_state[estado] = resposta
        except (captura.ErroCaptura, ValueError) as erro:
            st.error(str(erro))

    resposta = st.session_state.get(estado)
    origem = "CNPJ.ws · pesquisa por filtros" if busca else "CNPJ.ws · consulta de CNPJs"
    if resposta is None:
        return None, origem
    if resposta.aviso:
        st.warning(resposta.aviso)
    if resposta.nao_encontrados:
        st.warning(f"{resposta.nao_encontrados} CNPJ(s) sem cadastro disponível.")
    if resposta.empresas.empty:
        st.info("Nenhuma empresa retornou para essa consulta.")
        return None, origem
    leads, relatorio = dados.limpar(resposta.empresas)
    st.success(f"{relatorio['leads_validos']} empresa(s) da API estão prontas para o ranking.")
    with st.expander("Conferir empresas capturadas"):
        st.dataframe(leads, hide_index=True, width="stretch")
    return leads if not leads.empty else None, origem
