"""Leituras usadas pelas páginas (sem regra de negócio)."""

from __future__ import annotations

import json

import pandas as pd

from .conexao import conectar


def _df(sql: str, params: list | tuple = ()) -> pd.DataFrame:
    with conectar() as con:
        return pd.read_sql_query(sql, con, params=list(params))


def leads(etapas: list[str] | None = None, responsavel_id: int | None = None, desde: str | None = None) -> pd.DataFrame:
    sql = """SELECT l.*, u.nome responsavel, e.nome executivo
             FROM leads l LEFT JOIN usuarios u ON u.id=l.responsavel_id LEFT JOIN usuarios e ON e.id=l.executivo_id
             WHERE 1=1"""
    params: list = []
    if etapas:
        sql += f" AND l.etapa IN ({','.join('?' * len(etapas))})"
        params += etapas
    if responsavel_id:
        sql += " AND l.responsavel_id=?"
        params.append(responsavel_id)
    if desde:
        sql += " AND l.criado_em >= ?"
        params.append(desde)
    return _df(sql + " ORDER BY l.nota_final DESC NULLS LAST, l.id", params)


def lead(lead_id: int) -> dict | None:
    with conectar() as con:
        linha = con.execute(
            """SELECT l.*, u.nome responsavel, e.nome executivo FROM leads l
               LEFT JOIN usuarios u ON u.id=l.responsavel_id LEFT JOIN usuarios e ON e.id=l.executivo_id
               WHERE l.id=?""",
            (lead_id,),
        ).fetchone()
    return dict(linha) if linha else None


def contato(lead_id: int) -> dict | None:
    with conectar() as con:
        linha = con.execute("SELECT * FROM contatos WHERE lead_id=? ORDER BY id DESC LIMIT 1", (lead_id,)).fetchone()
    return dict(linha) if linha else None


def consentimento(lead_id: int) -> dict | None:
    with conectar() as con:
        linha = con.execute(
            "SELECT * FROM consentimentos WHERE lead_id=? ORDER BY id DESC LIMIT 1", (lead_id,)
        ).fetchone()
    return dict(linha) if linha else None


def ultimo_tratamento(lead_id: int) -> dict | None:
    with conectar() as con:
        linha = con.execute(
            "SELECT * FROM tratamentos WHERE lead_id=? AND concluido_em IS NOT NULL ORDER BY id DESC LIMIT 1",
            (lead_id,),
        ).fetchone()
        if not linha:
            return None
        t = dict(linha)
        t["decomposicao"] = json.loads(t["decomposicao"] or "{}")
        t["resultado"] = json.loads(t["resultado"]) if t["resultado"] else None
        t["recomendacoes"] = [
            {**dict(r), "caminho_grafo": json.loads(r["caminho_grafo"] or "{}")}
            for r in con.execute("SELECT * FROM recomendacoes WHERE tratamento_id=? ORDER BY id", (t["id"],))
        ]
        t["etapas"] = [dict(r) for r in con.execute(
            "SELECT agente, status, tempo_ms, detalhe FROM tratamento_etapas WHERE tratamento_id=? ORDER BY ordem",
            (t["id"],))]  # fmt: skip
    return t


def tratados(desde: str | None = None) -> pd.DataFrame:
    """Último tratamento de cada lead."""
    sql = """SELECT t.id tratamento_id, t.lote, t.concluido_em, t.motor, t.modelo, t.versao_prompt, t.nota_aderencia,
                    t.propensao, t.confianca, t.nota_final, t.classificacao, t.destino, t.plano_b, t.custo_estimado,
                    l.id lead_id, l.razao_social, l.nome_fantasia, l.uf, l.cidade, l.etapa, l.solucao_principal,
                    l.base_ficticia, l.origem
             FROM tratamentos t JOIN leads l ON l.id=t.lead_id
             WHERE t.id IN (SELECT MAX(id) FROM tratamentos WHERE concluido_em IS NOT NULL GROUP BY lead_id)"""
    params: list = []
    if desde:
        sql += " AND t.concluido_em >= ?"
        params.append(desde)
    return _df(sql + " ORDER BY t.nota_final DESC NULLS LAST", params)


def lotes_recentes(limite: int = 10) -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT lote, MIN(iniciado_em) inicio, COUNT(*) n, MAX(motor) motor FROM tratamentos "
            "GROUP BY lote ORDER BY inicio DESC LIMIT ?", (limite,))]  # fmt: skip


def icp_versoes() -> pd.DataFrame:
    return _df("SELECT id, criada_em, criada_por, nome, descricao, setores, portes, palavras_chave, ativa "
               "FROM icp_versoes ORDER BY id DESC")  # fmt: skip


def atividades(lead_id: int) -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute(
            """SELECT a.*, u.nome usuario FROM atividades a LEFT JOIN usuarios u ON u.id=a.usuario_id
               WHERE a.lead_id=? ORDER BY a.id DESC""", (lead_id,))]  # fmt: skip


def historico_etapas(lead_id: int) -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM etapas_historico WHERE lead_id=? ORDER BY id", (lead_id,))]  # fmt: skip


def cadencia(lead_id: int) -> list[dict]:
    with conectar() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM cadencia_passos WHERE lead_id=? ORDER BY dia, id", (lead_id,))]  # fmt: skip


def bant(lead_id: int) -> dict | None:
    with conectar() as con:
        linha = con.execute("SELECT * FROM bant WHERE lead_id=?", (lead_id,)).fetchone()
    return dict(linha) if linha else None


def oportunidade(lead_id: int) -> dict | None:
    with conectar() as con:
        linha = con.execute("SELECT * FROM oportunidades WHERE lead_id=?", (lead_id,)).fetchone()
    if not linha:
        return None
    o = dict(linha)
    o["solucoes"] = json.loads(o["solucoes"] or "[]")
    return o


def correcoes(lead_id: int | None = None) -> pd.DataFrame:
    sql = """SELECT c.*, u.nome usuario, l.razao_social FROM correcoes_ia c
             LEFT JOIN usuarios u ON u.id=c.usuario_id JOIN leads l ON l.id=c.lead_id"""
    params: list = []
    if lead_id:
        sql += " WHERE c.lead_id=?"
        params.append(lead_id)
    return _df(sql + " ORDER BY c.id DESC", params)


def auditoria(entidade_id: str | None = None, limite: int = 300) -> pd.DataFrame:
    sql = "SELECT ocorrido_em, ator, acao, entidade, entidade_id, detalhe FROM auditoria"
    params: list = []
    if entidade_id:
        sql += " WHERE entidade='leads' AND entidade_id=?"
        params.append(str(entidade_id))
    return _df(sql + " ORDER BY id DESC LIMIT ?", [*params, limite])


def carteira(responsavel_id: int | None = None) -> pd.DataFrame:
    """Leads com a última atividade de cada um. Sem responsável = todos."""
    sql = """SELECT l.id, l.razao_social, l.nome_fantasia, l.etapa, l.classificacao, l.nota_final, l.solucao_principal,
                    l.uf, l.cidade, l.retorno_em, l.proxima_acao, l.sla_limite, l.primeiro_contato_em, l.opt_out,
                    l.responsavel_id, l.base_ficticia, l.criado_em, u.nome responsavel,
                    a.registrada_em ultima_atividade_em, a.tipo ultima_atividade_tipo, a.resultado ultima_atividade_resultado
             FROM leads l
             LEFT JOIN usuarios u ON u.id=l.responsavel_id
             LEFT JOIN atividades a ON a.id = (SELECT MAX(id) FROM atividades WHERE lead_id=l.id)
             WHERE l.responsavel_id IS NOT NULL"""
    params: list = []
    if responsavel_id:
        sql += " AND l.responsavel_id=?"
        params.append(responsavel_id)
    return _df(sql + " ORDER BY l.nota_final DESC NULLS LAST", params)


def metas_do_dia(usuario_id: int, inicio_dia: str, inicio_semana: str, agora: str, hoje: str) -> dict:
    with conectar() as con:
        contatos = con.execute(
            "SELECT COUNT(*) FROM atividades WHERE usuario_id=? AND registrada_em>=? AND tipo IN "
            "('Ligação','E-mail','WhatsApp','Reunião')", (usuario_id, inicio_dia),
        ).fetchone()[0]  # fmt: skip
        meta = con.execute("SELECT meta_contatos_dia FROM usuarios WHERE id=?", (usuario_id,)).fetchone()
        ativos = "('Na fila do BDR','Em contato','Qualificado')"
        retornos = con.execute(
            f"SELECT COUNT(*) FROM leads WHERE responsavel_id=? AND etapa IN {ativos} AND substr(retorno_em,1,10)=?",
            (usuario_id, hoje),
        ).fetchone()[0]
        atrasados = con.execute(
            f"""SELECT COUNT(*) FROM leads WHERE responsavel_id=? AND opt_out=0 AND etapa IN {ativos} AND (
                    (etapa='Na fila do BDR' AND primeiro_contato_em IS NULL AND sla_limite < ?)
                    OR (retorno_em IS NOT NULL AND substr(retorno_em,1,10) < ?))""",
            (usuario_id, agora, hoje),
        ).fetchone()[0]
        reunioes = con.execute(
            "SELECT COUNT(*) FROM etapas_historico h JOIN leads l ON l.id=h.lead_id "
            "WHERE l.responsavel_id=? AND h.para='Reunião marcada' AND h.registrado_em>=?", (usuario_id, inicio_semana),
        ).fetchone()[0]  # fmt: skip
    return {"contatos": contatos, "meta": (meta["meta_contatos_dia"] if meta else 20) or 20, "retornos": retornos,
            "atrasados": atrasados, "reunioes_semana": reunioes}  # fmt: skip
