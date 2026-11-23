"""Máquina de estados do lead. Toda mudança grava quem, quando, de onde, para onde e por quê."""

from __future__ import annotations

import sqlite3

from banco import repositorio

from . import tempo

CAPTURADO = "Capturado"
EM_TRATAMENTO = "Em tratamento"
TRATADO = "Tratado"
FILA_BDR = "Na fila do BDR"
EM_ANALISE = "Em análise BDR"
NUTRICAO = "Em nutrição"
REVISAO = "Revisão humana"
DESCARTADO = "Descartado"
RETIDO = "Retido LGPD"
EM_CONTATO = "Em contato"
QUALIFICADO = "Qualificado"
REUNIAO = "Reunião marcada"
PROPOSTA = "Proposta"
GANHO = "Ganho"
PERDIDO = "Perdido"

ESTADOS = [CAPTURADO, EM_TRATAMENTO, TRATADO, FILA_BDR, NUTRICAO, REVISAO, DESCARTADO, RETIDO,
           EM_ANALISE, EM_CONTATO, QUALIFICADO, REUNIAO, PROPOSTA, GANHO, PERDIDO]  # fmt: skip

TRANSICOES: dict[str, set[str]] = {
    CAPTURADO: {EM_TRATAMENTO, DESCARTADO, RETIDO},
    EM_TRATAMENTO: {TRATADO, RETIDO, REVISAO, CAPTURADO},
    TRATADO: {FILA_BDR, NUTRICAO, REVISAO, DESCARTADO, RETIDO},
    REVISAO: {FILA_BDR, NUTRICAO, DESCARTADO, EM_TRATAMENTO},
    NUTRICAO: {FILA_BDR, EM_TRATAMENTO, DESCARTADO},
    RETIDO: {EM_TRATAMENTO, DESCARTADO},
    FILA_BDR: {EM_ANALISE, EM_CONTATO, NUTRICAO, PERDIDO, DESCARTADO, EM_TRATAMENTO},
    EM_ANALISE: {FILA_BDR, EM_CONTATO, NUTRICAO, DESCARTADO},
    EM_CONTATO: {QUALIFICADO, EM_ANALISE, NUTRICAO, PERDIDO},
    QUALIFICADO: {REUNIAO, NUTRICAO, PERDIDO},
    REUNIAO: {PROPOSTA, QUALIFICADO, PERDIDO},
    PROPOSTA: {GANHO, PERDIDO},
    GANHO: set(),
    PERDIDO: {NUTRICAO},
    DESCARTADO: {EM_TRATAMENTO},
}

EXIGE_MOTIVO = {PERDIDO, DESCARTADO}
MOTIVOS = ["Sem orçamento", "Já é cliente de concorrente", "Sem fit", "Sem resposta", "Outro"]
# Etapas em que o lead pode ser contatado. Opt-out bloqueia todas.
ETAPAS_DE_CONTATO = {FILA_BDR, EM_CONTATO, QUALIFICADO, REUNIAO, PROPOSTA}
ETAPAS_FUNIL = [EM_CONTATO, QUALIFICADO, REUNIAO, PROPOSTA, GANHO, PERDIDO]


class TransicaoInvalida(ValueError):
    """A mudança de etapa não é permitida."""


def validar(de: str | None, para: str, motivo: str | None, detalhe: str | None, opt_out: bool) -> None:
    if para not in ESTADOS:
        raise TransicaoInvalida(f"Etapa desconhecida: {para}.")
    if de is not None and para not in TRANSICOES.get(de, set()):
        raise TransicaoInvalida(f"Não é possível ir de {de} para {para}.")
    if para in EXIGE_MOTIVO:
        if motivo not in MOTIVOS:
            raise TransicaoInvalida(f"Para marcar como {para}, escolha um motivo da lista.")
        if motivo == "Outro" and not (detalhe or "").strip():
            raise TransicaoInvalida("Descreva o motivo quando escolher Outro.")
    if opt_out and para in ETAPAS_DE_CONTATO:
        raise TransicaoInvalida("O titular pediu opt-out. O lead não pode voltar para contato.")


def mudar(
    con: sqlite3.Connection,
    lead_id: int,
    para: str,
    ator: str,
    motivo: str | None = None,
    detalhe: str | None = None,
    momento: str | None = None,
) -> str:
    """Muda a etapa do lead dentro da transação aberta. Retorna a etapa anterior."""
    linha = con.execute("SELECT etapa, opt_out FROM leads WHERE id=?", (lead_id,)).fetchone()
    if linha is None:
        raise TransicaoInvalida(f"Lead {lead_id} não encontrado.")
    de = linha["etapa"]
    validar(de, para, motivo, detalhe, bool(linha["opt_out"]))
    momento = momento or tempo.iso()
    con.execute(
        "UPDATE leads SET etapa=?, atualizado_em=?, versao=versao+1 WHERE id=?",
        (para, momento, lead_id),
    )
    con.execute(
        "INSERT INTO etapas_historico (lead_id, de, para, ator, motivo, detalhe, registrado_em) VALUES (?,?,?,?,?,?,?)",
        (lead_id, de, para, ator, motivo, detalhe, momento),
    )
    repositorio.auditar(con, ator, "mudanca_etapa", "leads", lead_id, {"de": de, "para": para, "motivo": motivo})
    return de


def registrar_entrada(con: sqlite3.Connection, lead_id: int, ator: str, momento: str | None = None) -> None:
    """Primeiro registro do histórico: o lead nasce como Capturado."""
    con.execute(
        "INSERT INTO etapas_historico (lead_id, de, para, ator, motivo, detalhe, registrado_em) VALUES (?,?,?,?,?,?,?)",
        (lead_id, None, CAPTURADO, ator, None, None, momento or tempo.iso()),
    )
