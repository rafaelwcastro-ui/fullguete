"""Projeções do portal montadas a partir da mesma carteira autorizada."""

import pandas as pd
from fastapi import HTTPException

from banco import consultas, metricas
from banco.conexao import reutilizar_transacao
from dados.features import normalizar
from dados.limpeza import remover_dados_pessoais
from ia import assistente
from nucleo import comercial, estados, lgpd, tempo
from portal_api.commands import crm_moves


def rows(con, sql, params):
    return [dict(row) for row in con.execute(sql, params)]


def scoped_lead(con, ident, where, params):
    lead = con.execute(f"SELECT l.* FROM leads l WHERE ({where}) AND l.id=?", [*params, ident]).fetchone()
    if lead is None:
        raise HTTPException(404, "Lead não encontrado.")
    return lead


TERM_FILTER = r"""LOWER(COALESCE(l.nome_fantasia,'') || ' ' || l.razao_social || ' ' || COALESCE(l.cnpj,''))
                 LIKE ? ESCAPE '\'"""


def search_pattern(term: str) -> str:
    escaped = term.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def kanban(con, where, params, termo, page, selected_stage):
    query = f"""WITH matches AS (
        SELECT l.id,l.razao_social,l.nome_fantasia,l.etapa,l.versao,l.nota_final,
           o.valor_mensal,u.nome AS executivo,
           COUNT(*) OVER (PARTITION BY l.etapa) AS total,
           SUM(COALESCE(o.valor_mensal,0)) OVER (PARTITION BY l.etapa) AS valor_coluna,
           ROW_NUMBER() OVER (PARTITION BY l.etapa ORDER BY l.atualizado_em DESC,l.id DESC) AS ordem
        FROM leads l LEFT JOIN oportunidades o ON o.lead_id=l.id LEFT JOIN usuarios u ON u.id=l.executivo_id
        WHERE ({where})
        AND l.etapa IN ({",".join("?" for _ in estados.ETAPAS_FUNIL)})
        AND {TERM_FILTER}
    ) SELECT * FROM matches
      WHERE ordem <= CASE WHEN etapa=? THEN ? ELSE 12 END ORDER BY ordem"""
    cards = rows(con, query, [*params, *estados.ETAPAS_FUNIL, search_pattern(termo), selected_stage, page * 12])
    stages = []
    for stage in estados.ETAPAS_FUNIL:
        items = [card for card in cards if card["etapa"] == stage]
        stages.append(
            {
                "etapa": stage,
                "items": items,
                "total": items[0]["total"] if items else 0,
                "valor": items[0]["valor_coluna"] if items else 0,
            }
        )
    return {"colunas": stages}


def crm_detail(con, ident, actor, where, params):
    lead = scoped_lead(con, ident, where, params)
    with reutilizar_transacao(con):
        opportunity = consultas.oportunidade(ident)
        timeline = comercial.linha_do_tempo(ident, incluir_notas=False)
    if opportunity:
        visible = ("solucoes", "valor_mensal", "previsao_fechamento", "executivo")
        summary = opportunity.get("resumo_passagem")
        owner = con.execute("SELECT nome FROM usuarios WHERE id=?", (lead["executivo_id"],)).fetchone()
        opportunity = {key: opportunity.get(key) for key in visible}
        opportunity["executivo"] = owner["nome"] if owner else None
        if lead["base_ficticia"] and summary:
            opportunity["resumo_passagem"] = remover_dados_pessoais(summary)
    return {
        "oportunidade": opportunity,
        "historico": list(reversed(timeline[-30:])),
        "movimentos": crm_moves(actor, lead["etapa"]),
        "posso_passar": actor["papel"] != "executivo" and lead["etapa"] in (estados.EM_CONTATO, estados.QUALIFICADO),
    }


def schedule(con, actor, where, params, status, lead_id, limit, offset):
    if actor["papel"] != "gestor":
        where += " AND a.responsavel_id=?"
        params.append(actor["id"])
    if status != "Todos":
        where += " AND a.status=?"
        params.append(status)
    if lead_id is not None:
        where += " AND l.id=?"
        params.append(lead_id)
    return {
        "items": rows(
            con,
            f"""SELECT a.id,a.lead_id,a.tipo,a.titulo,a.inicio_em,a.status,
           COALESCE(NULLIF(l.nome_fantasia,''),l.razao_social) empresa,l.versao,u.nome responsavel
           FROM agenda_compromissos a JOIN leads l ON l.id=a.lead_id
           JOIN usuarios u ON u.id=a.responsavel_id WHERE {where}
           ORDER BY CASE WHEN a.status='Pendente' THEN 0 ELSE 1 END,a.inicio_em,a.id LIMIT ? OFFSET ?""",
            [*params, limit, offset],
        )
    }


def funnel(con, source, params):
    total = con.execute(source + "SELECT COUNT(*) FROM scoped", params).fetchone()[0]
    reached = {
        r["para"]: r["total"]
        for r in con.execute(
            source
            + """SELECT h.para,COUNT(DISTINCT h.lead_id) AS total
        FROM etapas_historico h JOIN scoped l ON l.id=h.lead_id GROUP BY h.para""",
            params,
        )
    }
    stages = []
    previous = None
    for name, stage in metricas.FUNIL:
        count = total if stage is None else reached.get(stage, 0)
        stages.append({"etapa": name, "leads": count, "conversao": count / previous if previous else None})
        previous = count
    return stages


def analytics(con, where, params, days, campaign_id):
    if days:
        where += " AND l.criado_em>=?"
        params.append(tempo.daqui(dias=-days))
    if campaign_id:
        where += " AND EXISTS (SELECT 1 FROM buscas_leads bl WHERE bl.lead_id=l.id AND bl.busca_id=?)"
        params.append(campaign_id)
    source = f"WITH scoped AS (SELECT l.* FROM leads l WHERE {where}) "
    stages = funnel(con, source, params)
    columns = ["etapa", "valor_mensal", "primeiro_contato_em", "sla_limite", "fila_em"]
    timing = pd.DataFrame(
        rows(
            con,
            source
            + """SELECT l.etapa,o.valor_mensal,l.primeiro_contato_em,l.sla_limite,
        (SELECT MIN(h.registrado_em) FROM etapas_historico h WHERE h.lead_id=l.id AND h.para=?) fila_em
        FROM scoped l LEFT JOIN oportunidades o ON o.lead_id=l.id""",
            [*params, estados.FILA_BDR],
        ),
        columns=columns,
    )
    timing["valor_mensal"] = pd.to_numeric(timing["valor_mensal"])
    timing["etapa"] = timing["etapa"].astype(object)
    sla = metricas.tempos_e_sla(timing, tempo.iso())
    revenue = metricas.receita(timing)
    productivity = rows(
        con,
        source
        + """SELECT u.nome AS bdr,
        COUNT(DISTINCT a.lead_id) leads,COUNT(*) atividades,
        COUNT(CASE WHEN a.tipo IN ('Ligação','E-mail','WhatsApp','Reunião') THEN 1 END) contatos
        FROM atividades a JOIN scoped l ON l.id=a.lead_id JOIN usuarios u ON u.id=a.usuario_id
        WHERE u.papel='bdr' GROUP BY u.id ORDER BY atividades DESC,u.nome""",
        params,
    )
    campaigns = rows(
        con,
        source
        + """SELECT b.tag,COUNT(*) leads,
        COUNT(CASE WHEN l.etapa='Ganho' THEN 1 END) ganhos,
        COUNT(CASE WHEN l.primeiro_contato_em IS NOT NULL THEN 1 END) contatos
        FROM buscas_leads bl JOIN scoped l ON l.id=bl.lead_id
        JOIN buscas_prospeccao b ON b.id=bl.busca_id GROUP BY b.id ORDER BY leads DESC,b.id DESC LIMIT 30""",
        params,
    )
    ai = dict(
        con.execute(
            source
            + """SELECT COUNT(*) tratamentos,COUNT(DISTINCT t.lead_id) leads,
        AVG(t.tempo_ms) latencia_ms,AVG(t.nota_final) nota_media,
        COUNT(CASE WHEN t.plano_b=1 THEN 1 END) plano_b
        FROM tratamentos t JOIN scoped l ON l.id=t.lead_id WHERE t.concluido_em IS NOT NULL""",
            params,
        ).fetchone()
    )
    feedback = con.execute(
        source
        + """SELECT COUNT(*) avaliacoes,AVG(c.concorda) concordancia
        FROM correcoes_ia c JOIN scoped l ON l.id=c.lead_id""",
        params,
    ).fetchone()
    return {
        "funil": stages,
        "sla": sla,
        "receita": revenue,
        "bdr": productivity,
        "campanhas": campaigns,
        "ia": {**ai, **dict(feedback)},
    }


def consult(con, actor, where, params, prompt, lead_id):
    lead = scoped_lead(con, lead_id, where, params) if lead_id else None
    if lead is not None:
        if lead["etapa"] in (estados.GANHO, estados.PERDIDO, estados.DESCARTADO):
            return {
                "texto": "O lead está encerrado. Consulte o histórico e acompanhe o resultado no Analytics.",
                "motor": "local",
                "fontes": [],
            }
        if not lgpd.base_para_contato(con, lead_id) or lead["etapa"] not in estados.ETAPAS_DE_CONTATO:
            return {
                "texto": "O contato está bloqueado pela etapa ou pela base legal. Revise a qualificação e a base "
                "legal antes de propor uma abordagem. Registre a análise como atividade interna.",
                "motor": "local",
                "fontes": [],
            }
        with reutilizar_transacao(con):
            return assistente.responder(prompt, lead_id, usuario=actor, usar_llm=False, incluir_valores_bant=False)
    scoped = f"WITH scoped AS (SELECT l.* FROM leads l WHERE {where}) "
    bucket = con.execute(
        scoped
        + """SELECT
        COUNT(CASE WHEN etapa=? THEN 1 END) revisao,
        COUNT(CASE WHEN etapa=? AND primeiro_contato_em IS NULL AND sla_limite<? THEN 1 END) vencidos,
        COUNT(CASE WHEN etapa=? THEN 1 END) propostas FROM scoped""",
        [*params, estados.REVISAO, estados.FILA_BDR, tempo.iso(), estados.PROPOSTA],
    ).fetchone()
    candidates = rows(
        con,
        scoped
        + """SELECT id,razao_social empresa,etapa
        FROM scoped WHERE etapa IN (?,?) ORDER BY nota_final DESC NULLS LAST,id LIMIT 10""",
        [*params, estados.REUNIAO, estados.PROPOSTA],
    )
    highlights = [item for item in candidates if lgpd.base_para_contato(con, item["id"])][:3]
    intent = normalizar(prompt)
    if any(term in intent for term in ("gargalo", "prioriz", "oportunidade", "carteira")):
        actions = []
        if bucket["vencidos"]:
            actions.append("Revise os leads com SLA vencido e confirme a base legal antes de qualquer contato.")
        if bucket["revisao"]:
            actions.append("Resolva a revisão humana para liberar os casos elegíveis.")
        if bucket["propostas"]:
            actions.append("Verifique prazos e próximos compromissos das propostas abertas.")
        answer = {
            "texto": " ".join(actions) or "Não há esses gargalos no recorte atual. Acompanhe a fila e os compromissos.",
            "motor": "local",
            "fontes": [],
        }
    else:
        answer = assistente.responder(prompt, usar_llm=False)
    answer["carteira"] = dict(bucket)
    answer["oportunidades"] = highlights
    return answer
