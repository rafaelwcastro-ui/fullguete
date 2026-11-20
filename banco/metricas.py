"""Indicadores de negócio e de operação (consumo da camada ouro e do histórico do funil)."""

from __future__ import annotations

import pandas as pd

from nucleo import estados

from .conexao import conectar
from .consultas import _df

# Ordem do funil de ponta a ponta. Cada etapa conta os leads que já passaram por ela.
FUNIL = [
    ("Capturados", None),
    ("Tratados", estados.TRATADO),
    ("Com o BDR", estados.FILA_BDR),
    ("Em contato", estados.EM_CONTATO),
    ("Qualificados", estados.QUALIFICADO),
    ("Reuniões", estados.REUNIAO),
    ("Propostas", estados.PROPOSTA),
    ("Ganhos", estados.GANHO),
]
# Probabilidade de fechamento por etapa, usada na receita prevista (premissa do protótipo).
PROBABILIDADE_ETAPA = {estados.QUALIFICADO: 0.15, estados.REUNIAO: 0.3, estados.PROPOSTA: 0.6}


def funil(desde: str | None = None) -> list[dict]:
    filtro, params = ("WHERE l.criado_em >= ?", [desde]) if desde else ("", [])
    with conectar() as con:
        total = con.execute(f"SELECT COUNT(*) FROM leads l {filtro}", params).fetchone()[0]
        alcancou = {
            r["para"]: r["n"]
            for r in con.execute(
                f"SELECT h.para, COUNT(DISTINCT h.lead_id) n FROM etapas_historico h JOIN leads l ON l.id=h.lead_id "
                f"{filtro} GROUP BY h.para",
                params,
            )
        }
    saida, anterior = [], None
    for nome, etapa in FUNIL:
        valor = total if etapa is None else alcancou.get(etapa, 0)
        conv = (valor / anterior) if anterior else None
        saida.append({"etapa": nome, "estado": etapa, "leads": valor, "conversao": conv})
        anterior = valor or None
    return saida


def leads_tempo(desde: str | None = None) -> pd.DataFrame:
    """Um lead por linha com os marcos de tempo do funil."""
    filtro, params = ("AND l.criado_em >= ?", [desde]) if desde else ("", [])
    return _df(
        f"""SELECT l.id, l.origem, l.canal, l.etapa, l.classificacao, l.solucao_principal, l.responsavel_id,
                   u.nome responsavel, l.criado_em, l.sla_limite, l.primeiro_contato_em, l.base_ficticia, l.porte,
                   l.segmento, l.nota_final, l.opt_out,
                   (SELECT MIN(registrado_em) FROM etapas_historico WHERE lead_id=l.id AND para='Na fila do BDR') fila_em,
                   (SELECT MIN(registrado_em) FROM etapas_historico WHERE lead_id=l.id AND para='Reunião marcada') reuniao_em,
                   (SELECT MIN(registrado_em) FROM etapas_historico WHERE lead_id=l.id AND para='Ganho') ganho_em,
                   o.valor_mensal
            FROM leads l LEFT JOIN usuarios u ON u.id=l.responsavel_id LEFT JOIN oportunidades o ON o.lead_id=l.id
            WHERE 1=1 {filtro}""",
        params,
    )


def tempos_e_sla(df: pd.DataFrame, agora: str) -> dict:
    na_fila = df[df["fila_em"].notna()].copy()
    if na_fila.empty:
        return {"mediana_h": None, "media_h": None, "sla_pct": None, "vencidos_sem_contato": 0, "contatados": 0}
    contatados = na_fila[na_fila["primeiro_contato_em"].notna()].copy()
    horas = (
        pd.to_datetime(contatados["primeiro_contato_em"]) - pd.to_datetime(contatados["fila_em"])
    ).dt.total_seconds() / 3600
    dentro = (contatados["primeiro_contato_em"] <= contatados["sla_limite"].fillna("9999")).sum()
    vencidos = na_fila[na_fila["primeiro_contato_em"].isna() & (na_fila["sla_limite"].fillna("9999") < agora)
                       & na_fila["etapa"].eq(estados.FILA_BDR)]  # fmt: skip
    base = len(contatados) + len(vencidos)
    return {
        "mediana_h": float(horas.median()) if len(horas) else None,
        "media_h": float(horas.mean()) if len(horas) else None,
        "sla_pct": (dentro / base) if base else None,
        "vencidos_sem_contato": int(len(vencidos)),
        "contatados": int(len(contatados)),
    }


def receita(df: pd.DataFrame) -> dict:
    abertos = df[df["etapa"].isin(PROBABILIDADE_ETAPA) & df["valor_mensal"].notna()]
    prevista = float((abertos["valor_mensal"] * abertos["etapa"].map(PROBABILIDADE_ETAPA)).sum())
    pipeline = float(abertos["valor_mensal"].sum())
    ganha = float(df.loc[df["etapa"] == estados.GANHO, "valor_mensal"].fillna(0).sum())
    return {"prevista": prevista, "pipeline": pipeline, "ganha": ganha}


def recomendadas_e_vendidas() -> pd.DataFrame:
    return _df(
        """SELECT r.solucao_id, COUNT(*) recomendadas,
                  SUM(CASE WHEN l.etapa='Ganho' AND l.solucao_principal=r.solucao_id THEN 1 ELSE 0 END) vendidas
           FROM recomendacoes r JOIN leads l ON l.id=r.lead_id
           WHERE r.tipo='principal' AND r.tratamento_id IN (SELECT MAX(id) FROM tratamentos GROUP BY lead_id)
           GROUP BY r.solucao_id ORDER BY recomendadas DESC"""
    )


def concordancia() -> dict:
    with conectar() as con:
        linha = con.execute("SELECT COUNT(*) n, COALESCE(SUM(concorda),0) ok FROM correcoes_ia").fetchone()
    return {"avaliacoes": int(linha["n"]), "concordancia": (linha["ok"] / linha["n"]) if linha["n"] else None}


def planos_b_semanais() -> tuple[float, float]:
    """Taxa de plano B nos últimos 7 dias e nos 7 anteriores."""
    from nucleo import tempo

    with conectar() as con:

        def taxa(inicio: str, fim: str) -> float:
            r = con.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(plano_b),0) b FROM tratamentos WHERE concluido_em>=? AND concluido_em<?",
                (inicio, fim),
            ).fetchone()
            return (r["b"] / r["n"]) if r["n"] else 0.0

        agora = tempo.iso()
        return taxa(tempo.daqui(dias=-7), agora), taxa(tempo.daqui(dias=-14), tempo.daqui(dias=-7))
