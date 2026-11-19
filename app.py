"""Fullguete — portal de ranqueamento de leads com IA (Streamlit)."""
from __future__ import annotations

import html
import io
import json
import os
from collections.abc import Mapping
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from fullguete import auth, banco, dados, score_ia, score_local
from fullguete.models import PORTES, PerfilClienteIdeal

RAIZ = Path(__file__).parent
EXEMPLO = RAIZ / "data" / "exemplo_leads.csv"
MAX_LEADS_IA = 200  # protege o custo da API num portal público
UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB",
       "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]
CIANO, VIOLETA, LILAS, TEXTO_SUAVE = "#00E5FF", "#8B5CF6", "#C084FC", "#9AA3C7"

st.set_page_config(page_title="Fullguete · Ranking de Leads", page_icon=str(RAIZ / "assets/icone.png"), layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800&family=Inter:wght@400;500;600&display=swap');
html, body, [class*="css"], .stMarkdown, p, label, input, textarea { font-family: 'Inter', sans-serif; }
h1, h2, h3, h4 { font-family: 'Montserrat', sans-serif !important; letter-spacing: -0.01em; }
.stApp { background: radial-gradient(1200px 600px at 85% -10%, rgba(139,92,246,.18), transparent 60%),
                     radial-gradient(900px 500px at -10% 10%, rgba(0,229,255,.10), transparent 60%), #0B1026; }
[data-testid="stSidebar"] { background: #0E1B3D; border-right: 1px solid rgba(0,229,255,.12); }
[data-testid="stMetric"] { background: rgba(14,27,61,.75); border: 1px solid rgba(139,92,246,.35);
    border-radius: 14px; padding: 14px 18px; box-shadow: 0 0 24px rgba(139,92,246,.12); }
[data-testid="stMetricValue"] { font-family: 'Montserrat', sans-serif; color: #FFFFFF; }
.fg-slogan { color: #9AA3C7; margin-top: -10px; margin-bottom: 18px; }
.fg-card { background: rgba(14,27,61,.75); border: 1px solid rgba(0,229,255,.18); border-radius: 14px;
    padding: 16px 18px; margin-bottom: 10px; }
.fg-card b { font-family: 'Montserrat', sans-serif; }
.fg-badge { display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: .8rem; font-weight: 600;
    background: rgba(0,229,255,.12); color: #00E5FF; border: 1px solid rgba(0,229,255,.35); }
.fg-badge.local { background: rgba(192,132,252,.12); color: #C084FC; border-color: rgba(192,132,252,.35); }
</style>
""",
    unsafe_allow_html=True,
)


# ---------- configuração ----------
def segredo(nome: str) -> str:
    try:
        valor = st.secrets.get(nome, "")
    except Exception:  # sem secrets.toml
        valor = ""
    return str(valor or os.environ.get(nome, "")).strip()


def usuarios_configurados() -> dict:
    try:
        bruto = st.secrets.get("usuarios", {})
    except Exception:
        bruto = {}
    return {str(k).lower(): dict(v) for k, v in bruto.items() if isinstance(v, Mapping) and v.get("senha_hash")}


def chave(nome: str, prefixo: str) -> str:
    valor = segredo(nome)
    # ignora vazio e os valores de exemplo do secrets.toml.example
    return valor if valor.startswith(prefixo) and not valor.endswith("...") else ""


# Rótulo na tela -> (provedor, chave, modelo)
IAS: dict[str, tuple[str, str, str]] = {}
if k := chave("ANTHROPIC_API_KEY", "sk-ant-"):
    IAS["Claude (IA)"] = ("anthropic", k, score_ia.MODELO)
if k := chave("OPENAI_API_KEY", "sk-"):
    IAS["OpenAI (IA)"] = ("openai", k, segredo("OPENAI_MODEL") or score_ia.MODELO_OPENAI_PADRAO)

usuario = auth.exigir_login(usuarios_configurados(), logo=str(RAIZ / "assets/logo.png"))

with st.sidebar:
    st.image(str(RAIZ / "assets/logo.png"), width="stretch")
    st.markdown("### Motor de análise")
    opcoes = [*IAS, "Análise local"]
    metodo = st.radio("Como pontuar os leads", opcoes, label_visibility="collapsed")
    if not IAS:
        st.info("Nenhuma chave de IA configurada (Anthropic ou OpenAI): o portal usa a análise local.")
    elif metodo in IAS:
        st.caption(f"Modelo: `{IAS[metodo][2]}` · até {MAX_LEADS_IA} leads por análise.")
    st.divider()
    st.caption(f"Conectado como **{usuario['nome']}**")
    if st.button("Sair", width="stretch"):
        auth.sair()
        st.rerun()
    st.divider()
    st.caption("Fullguete · Inteligência que acelera vendas.")

st.title("Ranking de Leads")
st.markdown('<p class="fg-slogan">Envie sua base, descreva o cliente ideal e veja quem abordar primeiro.</p>',
            unsafe_allow_html=True)

aba_nova, aba_hist, aba_sobre = st.tabs(["Nova análise", "Histórico", "Como funciona"])


# ---------- utilidades de exibição ----------
def para_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Ranking")
    return buf.getvalue()


def exibir_ranking(ranking: pd.DataFrame, metodo_usado: str, chave: str) -> None:
    classe = " local" if metodo_usado.startswith("Análise local") else ""
    st.markdown(f'<span class="fg-badge{classe}">Pontuado por: {metodo_usado}</span>', unsafe_allow_html=True)
    st.write("")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Leads ranqueados", len(ranking))
    c2.metric("Prioritários (≥ 80)", int((ranking["score"] >= 80).sum()))
    c3.metric("Nota média", f"{ranking['score'].mean():.0f}")
    c4.metric("Melhor lead", f"{ranking['score'].iloc[0]}", ranking["empresa"].iloc[0], delta_color="off", delta_arrow="off")

    st.markdown("#### Top 3 para abordar hoje")
    for _, r in ranking.head(3).iterrows():
        local = " · ".join(x for x in [r.get("setor", ""), f"{r.get('cidade', '')}/{r.get('uf', '')}".strip("/")] if x)
        st.markdown(
            f'<div class="fg-card"><b>{html.escape(r["empresa"])}</b> &nbsp;<span class="fg-badge">Fit {r["score"]}/100</span>'
            f'<br><small style="color:{TEXTO_SUAVE}">{html.escape(local)}</small><br>{html.escape(r["justificativa"])}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("#### Ranking completo")
    colunas = [c for c in ["posicao", "empresa", "score", "justificativa", "setor", "porte", "cidade", "uf",
                           "email", "telefone", "site", "cnpj"] if c in ranking.columns]
    st.dataframe(
        ranking[colunas],
        hide_index=True,
        width="stretch",
        column_config={
            "posicao": st.column_config.NumberColumn("#", width="small"),
            "empresa": st.column_config.TextColumn("Empresa", width="medium"),
            "score": st.column_config.ProgressColumn("Nota", min_value=0, max_value=100, format="%d"),
            "justificativa": st.column_config.TextColumn("Por que essa posição", width="large"),
            "setor": "Setor", "porte": "Porte", "cidade": "Cidade", "uf": "UF",
            "email": "E-mail", "telefone": "Telefone", "site": "Site", "cnpj": "CNPJ",
        },
    )

    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("Baixar CSV", ranking[colunas].to_csv(index=False).encode("utf-8-sig"),
                       "ranking_leads.csv", "text/csv", key=f"csv_{chave}")
    d2.download_button("Baixar Excel", para_excel(ranking[colunas]), "ranking_leads.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"xlsx_{chave}")

    g1, g2 = st.columns(2)
    layout = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font_color="#E6E9F5",
                  font_family="Inter", margin=dict(l=10, r=10, t=50, b=10), bargap=0.08, showlegend=False)
    with g1:
        fig = px.histogram(ranking, x="score", nbins=10, range_x=[0, 100],
                           title="Distribuição das notas", labels={"score": "Nota", "count": "Leads"})
        fig.update_traces(marker_color=CIANO, marker_line_width=0,
                          hovertemplate="Notas %{x}<br>%{y} leads<extra></extra>", xbins=dict(start=0, end=100, size=10))
        fig.update_layout(**layout, yaxis_title="Leads")
        fig.update_yaxes(gridcolor="rgba(154,163,199,.15)", zeroline=False)
        fig.update_xaxes(showgrid=False)
        st.plotly_chart(fig, width="stretch", key=f"hist_{chave}")
    with g2:
        por_setor = (ranking.assign(setor=ranking["setor"].replace("", "Não informado"))
                     .groupby("setor", as_index=False)["score"].mean().sort_values("score").tail(10))
        fig = px.bar(por_setor, x="score", y="setor", orientation="h", range_x=[0, 100],
                     title="Nota média por setor (top 10)", labels={"score": "Nota média", "setor": ""})
        fig.update_traces(marker_color=VIOLETA, marker_line_width=0,
                          hovertemplate="%{y}<br>Nota média %{x:.0f}<extra></extra>")
        fig.update_layout(**layout)
        fig.update_xaxes(gridcolor="rgba(154,163,199,.15)", zeroline=False)
        st.plotly_chart(fig, width="stretch", key=f"setor_{chave}")


# ---------- aba: nova análise ----------
with aba_nova:
    st.markdown("### 1. Base de leads")
    col_up, col_ex = st.columns([3, 1])
    arquivo = col_up.file_uploader("Planilha Excel ou CSV", type=["csv", "xlsx", "xls"],
                                   help="Precisa de uma coluna com o nome da empresa. "
                                        "Também usamos setor, porte, cidade, UF e descrição, se existirem.")
    col_ex.write("")
    col_ex.write("")
    if col_ex.button("Usar planilha de exemplo", width="stretch"):
        st.session_state["usar_exemplo"] = True
    if arquivo is not None:
        st.session_state["usar_exemplo"] = False

    origem = None
    if arquivo is not None:
        origem = (arquivo, arquivo.name)
    elif st.session_state.get("usar_exemplo"):
        origem = (str(EXEMPLO), EXEMPLO.name)

    leads = None
    if origem:
        try:
            bruto = dados.ler_planilha(origem[0], origem[1])
            leads, rel = dados.limpar(bruto)
        except Exception as e:  # erro de leitura vira mensagem amigável
            st.error(f"Não consegui ler a planilha: {e}")
        else:
            st.success(
                f"**{origem[1]}** · {rel['linhas_lidas']} linhas lidas → **{rel['leads_validos']} leads válidos** "
                f"({rel['duplicadas']} duplicadas e {rel['sem_nome']} sem nome removidas)."
            )
            with st.expander("Ver dados limpos"):
                st.dataframe(leads, hide_index=True, width="stretch")

    st.markdown("### 2. Perfil do cliente ideal")
    if st.session_state.get("usar_exemplo") and not st.session_state.get("icp_exemplo_aplicado"):
        st.session_state["icp_exemplo_aplicado"] = True
        st.session_state.update(
            icp_desc="Redes de varejo e atacado de alimentos ou bens de consumo com várias lojas, "
                     "em expansão, que precisam organizar a carteira e priorizar vendas.",
            icp_setores="Supermercado, Atacado, Varejo",
            icp_portes=["EPP", "Média", "Grande"],
            icp_ufs=["DF", "GO"],
        )
    with st.form("icp"):
        descricao = st.text_area("Descreva o cliente ideal", key="icp_desc", height=90,
                                 placeholder="Ex.: redes de supermercados regionais, com 5 ou mais lojas, que investem em tecnologia…")
        a, b = st.columns(2)
        setores = a.text_input("Setores-alvo (separe por vírgula)", key="icp_setores",
                               placeholder="Supermercado, Atacado, Varejo")
        portes = b.multiselect("Portes-alvo", PORTES, key="icp_portes")
        c, d = st.columns(2)
        ufs = c.multiselect("Estados-alvo", UFS, key="icp_ufs")
        cidades = d.text_input("Cidades-alvo (opcional, separe por vírgula)", key="icp_cidades")
        enviar = st.form_submit_button("Gerar ranking", type="primary", disabled=leads is None)

    if enviar and leads is not None:
        icp = PerfilClienteIdeal(
            descricao=descricao,
            setores=[s.strip() for s in setores.split(",") if s.strip()],
            portes=portes,
            ufs=ufs,
            cidades=[c.strip() for c in cidades.split(",") if c.strip()],
        )
        if not (icp.descricao.strip() or icp.setores):
            st.warning("Informe pelo menos a descrição ou os setores do cliente ideal.")
        else:
            metodo_usado = metodo
            if metodo in IAS and len(leads) > MAX_LEADS_IA:
                st.warning(f"A base tem {len(leads)} leads; a IA avalia até {MAX_LEADS_IA}. "
                           "Usando a análise local para a base inteira.")
                metodo_usado = "Análise local"
            if metodo_usado in IAS:
                provedor, api_key, modelo = IAS[metodo_usado]
                barra = st.progress(0.0, text=f"{metodo_usado.replace(' (IA)', '')} está avaliando os leads…")
                try:
                    pontuado = score_ia.pontuar(leads, icp, api_key, provedor=provedor, modelo=modelo,
                                                progresso=lambda p: barra.progress(p, text=f"Avaliando… {p:.0%}"))
                except score_ia.ErroIA as e:
                    st.warning(f"{e} Usando a análise local.")
                    pontuado, metodo_usado = score_local.pontuar(leads, icp), "Análise local"
                barra.empty()
            else:
                pontuado = score_local.pontuar(leads, icp)

            ranking = pontuado.sort_values(["score", "empresa"], ascending=[False, True]).reset_index(drop=True)
            ranking.insert(0, "posicao", range(1, len(ranking) + 1))
            analise_id = banco.salvar(ranking, icp.to_dict(), metodo_usado, origem[1])
            st.session_state["resultado"] = (ranking, metodo_usado, analise_id)

    if "resultado" in st.session_state:
        ranking, metodo_usado, analise_id = st.session_state["resultado"]
        st.markdown("### 3. Ranking")
        exibir_ranking(ranking, metodo_usado, f"nova_{analise_id}")


# ---------- aba: histórico ----------
with aba_hist:
    analises = banco.listar_analises()
    if analises.empty:
        st.info("Nenhuma análise salva ainda. Gere um ranking na aba **Nova análise**.")
    else:
        st.caption("No Streamlit Community Cloud o histórico é apagado quando o app reinicia.")
        rotulos = {
            int(r.id): f"#{r.id} · {r.criada_em.replace('T', ' ')} · {r.arquivo} · {r.metodo} · {r.total_leads} leads"
            for r in analises.itertuples()
        }
        escolhida = st.selectbox("Análise", list(rotulos), format_func=rotulos.get)
        linha = analises[analises["id"] == escolhida].iloc[0]
        icp = json.loads(linha["icp"])
        with st.expander("Perfil de cliente ideal usado"):
            st.json(icp)
        leads_hist = banco.carregar_leads(escolhida)
        exibir_ranking(leads_hist, linha["metodo"], f"hist_{escolhida}")
        if st.button("Excluir esta análise", type="secondary"):
            banco.excluir(escolhida)
            st.rerun()


# ---------- aba: como funciona ----------
with aba_sobre:
    st.markdown(
        f"""
### Do arquivo ao ranking

1. **Importação.** Você envia uma planilha Excel ou CSV. O portal reconhece os nomes de coluna mais comuns
   (empresa, razão social, segmento, município…) e aceita CSV separado por vírgula ou ponto e vírgula.
2. **Limpeza (Python + Pandas).** Padroniza textos, CNPJ, e-mail, site e porte; descarta linhas sem nome
   e remove duplicatas pelo CNPJ ou, sem ele, pelo nome + cidade.
3. **Pontuação.**
   - **IA (Claude, da Anthropic, ou OpenAI):** o modelo lê setor, porte, localização e a descrição livre de
     cada empresa, compara com o perfil do cliente ideal e devolve, em JSON estruturado, uma nota de 0 a 100 e a
     justificativa. Os leads vão em lotes de {score_ia.TAMANHO_LOTE}, processados em paralelo.
   - **Análise local:** sem chave de API, a nota combina similaridade textual TF-IDF com o perfil (40 pts),
     setor (25), porte (20) e localização (15).
4. **Ranking e histórico.** O resultado é ordenado, salvo em SQLite e pode ser exportado em CSV ou Excel.
"""
    )
