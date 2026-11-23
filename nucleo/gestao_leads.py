"""Decisões humanas do BDR, sem confundir análise com contatos efetivos."""

from __future__ import annotations

from banco import repositorio
from banco.conexao import conectar

from . import comercial, estados, lgpd

OPCOES = {
    estados.FILA_BDR: (estados.EM_ANALISE, estados.EM_CONTATO, estados.NUTRICAO, estados.DESCARTADO),
    estados.EM_ANALISE: (estados.FILA_BDR, estados.EM_CONTATO, estados.NUTRICAO, estados.DESCARTADO),
    estados.EM_CONTATO: (estados.QUALIFICADO, estados.EM_ANALISE, estados.NUTRICAO, estados.PERDIDO),
    estados.QUALIFICADO: (estados.NUTRICAO, estados.PERDIDO),
}


def opcoes(etapa: str) -> tuple[str, ...]:
    return OPCOES.get(etapa, ())


def mudar_status(
    lead_id: int,
    usuario: dict,
    para: str,
    justificativa: str,
    *,
    motivo: str | None = None,
    canal_contato: str = "",
    resultado_contato: str = "",
) -> str:
    """Muda uma etapa operacional com autoria e justificativa, respeitando o funil.

    EM_CONTATO só pode ser registrado junto com uma atividade de contato real.
    Qualificação pede primeiro contato e BANT; agenda interna não é contato.
    """
    justificativa = justificativa.strip()
    if len(justificativa) < 8:
        raise ValueError("Informe uma justificativa de pelo menos 8 caracteres.")
    with conectar() as con:
        lead = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if lead is None:
            raise ValueError("Lead não encontrado.")
        if usuario.get("papel") != "gestor" and not (
            usuario.get("papel") == "bdr" and lead["responsavel_id"] == usuario["id"]
        ):
            raise PermissionError("Este lead não pertence à sua fila de BDR.")
        if lead["opt_out"]:
            raise ValueError("Opt-out ativo: não é permitido mudar este lead para trabalho comercial.")
        if para not in opcoes(lead["etapa"]):
            raise estados.TransicaoInvalida(f"Não é possível mudar {lead['etapa']} para {para} nessa tela.")
        if para == estados.EM_CONTATO:
            if not lgpd.base_para_contato(con, lead_id):
                raise ValueError("Antes de registrar contato, documente a base legal em Governança & LGPD.")
            if canal_contato not in comercial.TIPOS_CONTATO or canal_contato == "Reunião":
                raise ValueError("Registre um contato efetivo por Ligação, E-mail ou WhatsApp.")
            if resultado_contato not in comercial.RESULTADOS:
                raise ValueError("Selecione o resultado real do contato.")
        if para == estados.QUALIFICADO:
            if not lead["primeiro_contato_em"]:
                raise ValueError("Registre o primeiro contato antes de qualificar este lead.")
            bant = con.execute("SELECT necessidade FROM bant WHERE lead_id=?", (lead_id,)).fetchone()
            if not bant or not (bant["necessidade"] or "").strip():
                raise ValueError("Preencha a Necessidade no BANT antes de qualificar.")
    if para == estados.EM_CONTATO:
        return comercial.registrar_atividade(lead_id, usuario, canal_contato, resultado_contato, justificativa)
    if para == estados.PERDIDO:
        comercial.fechar(lead_id, usuario, ganho=False, motivo=motivo, detalhe=justificativa)
        return para
    with conectar() as con:
        estados.mudar(con, lead_id, para, usuario["login"], motivo=motivo, detalhe=justificativa)
        repositorio.auditar(
            con,
            usuario["login"],
            "interferencia_manual_bdr",
            "leads",
            lead_id,
            {"destino": para, "justificativa": justificativa, "motivo": motivo},
        )
    return para
