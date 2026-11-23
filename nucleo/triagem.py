"""Triagem auditável: tornar visíveis os destinos da IA e permitir encaminhamento humano.

A decisão de envio à fila é diferente da autorização para contatar o cliente.
Nunca libera contato nem sobrescreve nota, classificação ou resposta da IA.
"""

from __future__ import annotations

from banco import repositorio
from banco.conexao import conectar

from . import comercial, estados, lgpd, tempo

ENCAMINHAVEIS = {estados.TRATADO, estados.REVISAO, estados.NUTRICAO, estados.FILA_BDR}


def situacao_operacional(etapa: str, responsavel: str | None = None) -> str:
    """Explica em linguagem operacional por que um lead não aparece na fila."""
    if etapa == estados.CAPTURADO:
        return "Aguardando tratamento IA"
    if etapa == estados.EM_TRATAMENTO:
        return "Tratamento ainda em execução"
    if etapa == estados.REVISAO:
        return "IA solicitou revisão humana"
    if etapa == estados.NUTRICAO:
        return "IA recomendou nutrição (não entrou na fila)"
    if etapa == estados.DESCARTADO:
        return "IA descartou: reprocessar ou revisar o ICP"
    if etapa == estados.RETIDO:
        return "Retido por opt-out ou bloqueio específico"
    if etapa == estados.TRATADO:
        return "Tratado, mas ainda sem encaminhamento"
    if etapa == estados.FILA_BDR:
        return f"Na fila de {responsavel}" if responsavel else "Na fila, porém sem BDR atribuído"
    if etapa == estados.EM_ANALISE:
        return f"Em análise pelo BDR {responsavel}" if responsavel else "Em análise BDR sem responsável"
    return f"Etapa do funil: {etapa}"


def encaminhar(lead_ids: list[int], usuario: dict, bdr_id: int, motivo: str) -> int:
    """Gestor encaminha tratados à fila, com motivo e trilha de auditoria.

    Valida todos antes de alterar; uma seleção inválida cancela o lote inteiro.
    """
    if usuario.get("papel") != "gestor":
        raise PermissionError("Somente o gestor pode encaminhar leads manualmente.")
    ids = list(dict.fromkeys(int(i) for i in lead_ids))
    if not ids or len(ids) > 100:
        raise ValueError("Selecione de 1 a 100 empresas.")
    if len(motivo.strip()) < 10:
        raise ValueError("Justifique o encaminhamento com pelo menos 10 caracteres.")
    motivo = motivo.strip()[:500]
    sla_horas = repositorio.config("sla_horas") or {}
    with conectar() as con:
        bdr = con.execute("SELECT id FROM usuarios WHERE id=? AND papel='bdr' AND ativo=1", (bdr_id,)).fetchone()
        if bdr is None:
            raise ValueError("Selecione um BDR ativo.")
        registros = []
        for ident in ids:
            lead = con.execute(
                "SELECT id, etapa, opt_out, responsavel_id, classificacao FROM leads WHERE id=?",
                (ident,),
            ).fetchone()
            if lead is None:
                raise ValueError(f"Lead #{ident} não encontrado.")
            if lead["opt_out"]:
                raise ValueError(f"Lead #{ident} possui opt-out e não pode ir para a fila.")
            if lead["etapa"] not in ENCAMINHAVEIS:
                raise ValueError(
                    f"Lead #{ident} está em {lead['etapa']}; precisa ser tratado ou revisado antes de encaminhar."
                )
            if not con.execute(
                "SELECT 1 FROM tratamentos WHERE lead_id=? AND concluido_em IS NOT NULL LIMIT 1",
                (ident,),
            ).fetchone():
                raise ValueError(f"Lead #{ident} ainda não possui tratamento IA concluído.")
            registros.append(lead)
        for lead in registros:
            ident = lead["id"]
            if lead["etapa"] != estados.FILA_BDR:
                estados.mudar(
                    con,
                    ident,
                    estados.FILA_BDR,
                    usuario["login"],
                    detalhe=f"Triagem comercial manual: {motivo}",
                )
            comercial.atribuir(con, ident, bdr_id, usuario["login"], f"Triagem manual: {motivo}")
            if lead["etapa"] != estados.FILA_BDR:
                con.execute(
                    "UPDATE leads SET sla_limite=? WHERE id=?",
                    (tempo.daqui(horas=sla_horas.get(lead["classificacao"], 24)), ident),
                )
            if lgpd.base_para_contato(con, ident):
                comercial.criar_cadencia(con, ident)
            repositorio.auditar(
                con,
                usuario["login"],
                "encaminhamento_manual",
                "leads",
                ident,
                {
                    "etapa_anterior": lead["etapa"],
                    "classificacao_ia_preservada": lead["classificacao"],
                    "bdr_id": bdr_id,
                    "motivo": motivo,
                },
            )
    return len(ids)
