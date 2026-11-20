"""LGPD na prática: opt-out, regularização da base legal, exportação, exclusão e retenção."""

from __future__ import annotations

import json

from banco import repositorio
from banco.conexao import conectar

from . import estados, tempo

REMOVIDO = "[removido a pedido do titular]"

# Para onde vai o lead quando o titular pede opt-out, conforme a etapa atual.
DESTINO_OPT_OUT = {
    estados.CAPTURADO: (estados.RETIDO, None),
    estados.TRATADO: (estados.RETIDO, None),
    estados.FILA_BDR: (estados.DESCARTADO, "Outro"),
    estados.REVISAO: (estados.DESCARTADO, "Outro"),
    estados.NUTRICAO: (estados.DESCARTADO, "Outro"),
    estados.EM_CONTATO: (estados.PERDIDO, "Outro"),
    estados.QUALIFICADO: (estados.PERDIDO, "Outro"),
    estados.REUNIAO: (estados.PERDIDO, "Outro"),
    estados.PROPOSTA: (estados.PERDIDO, "Outro"),
}


def registrar_opt_out(lead_id: int, ator: str, observacao: str = "") -> str:
    """Tira o lead das filas e bloqueia novo contato. Retorna a etapa final."""
    momento = tempo.iso()
    with conectar() as con:
        lead = con.execute("SELECT etapa, opt_out FROM leads WHERE id=?", (lead_id,)).fetchone()
        if lead is None:
            raise ValueError("Lead não encontrado.")
        etapa = lead["etapa"]
        if etapa in DESTINO_OPT_OUT:
            para, motivo = DESTINO_OPT_OUT[etapa]
            estados.mudar(con, lead_id, para, ator, motivo=motivo, detalhe="Opt-out do titular")
            etapa = para
        con.execute("UPDATE leads SET opt_out=1, atualizado_em=? WHERE id=?", (momento, lead_id))
        con.execute(
            "UPDATE consentimentos SET opt_out_em=?, observacao=? WHERE lead_id=? AND opt_out_em IS NULL",
            (momento, observacao or "Opt-out pedido pelo titular", lead_id),
        )
        con.execute(
            "UPDATE cadencia_passos SET feito_em=? WHERE lead_id=? AND feito_em IS NULL", (momento, lead_id)
        )  # passos pendentes deixam de valer
        repositorio.auditar(con, ator, "opt_out", "leads", lead_id, {"etapa_final": etapa, "observacao": observacao})
    return etapa


def regularizar(lead_id: int, ator: str, base_legal: str, observacao: str) -> None:
    """Registra uma base legal válida para um lead retido. O lead volta para o tratamento."""
    if base_legal not in ("consentimento", "legitimo_interesse"):
        raise ValueError("Escolha uma base legal válida.")
    if not observacao.strip():
        raise ValueError("Descreva como a base legal foi obtida.")
    with conectar() as con:
        lead = con.execute("SELECT etapa, opt_out FROM leads WHERE id=?", (lead_id,)).fetchone()
        if lead["opt_out"]:
            raise ValueError("O titular pediu opt-out. Não é possível regularizar para contato.")
        if lead["etapa"] != estados.RETIDO:
            raise ValueError("Só leads em Retido LGPD precisam de regularização.")
        con.execute(
            "INSERT INTO consentimentos (lead_id, base_legal, consentiu, canal, registrado_em, registrado_por, observacao)"
            " VALUES (?,?,?,?,?,?,?)",
            (lead_id, base_legal, int(base_legal == "consentimento"), "regularizacao", tempo.iso(), ator, observacao),
        )
        repositorio.auditar(con, ator, "base_legal_regularizada", "leads", lead_id, {"base_legal": base_legal})


def buscar_titular(termo: str) -> list[dict]:
    termo = termo.strip().lower()
    if len(termo) < 3:
        return []
    with conectar() as con:
        return [dict(r) for r in con.execute(
            """SELECT c.lead_id, c.nome, c.email, c.telefone, l.razao_social FROM contatos c JOIN leads l ON l.id=c.lead_id
               WHERE lower(c.email) LIKE ? OR lower(c.nome) LIKE ? OR c.telefone LIKE ? LIMIT 20""",
            (f"%{termo}%", f"%{termo}%", f"%{termo}%"))]  # fmt: skip


def exportar_titular(lead_id: int, ator: str) -> str:
    """Tudo o que o Fullguete guarda sobre o titular, em JSON (direito de acesso)."""
    with conectar() as con:
        dados = {
            "contato": [dict(r) for r in con.execute("SELECT * FROM contatos WHERE lead_id=?", (lead_id,))],
            "consentimentos": [
                dict(r) for r in con.execute("SELECT * FROM consentimentos WHERE lead_id=?", (lead_id,))
            ],
            "empresa": dict(
                con.execute(
                    "SELECT razao_social, nome_fantasia, cnpj, setor, cidade, uf, etapa FROM leads WHERE id=?",
                    (lead_id,),
                ).fetchone()
            ),  # fmt: skip
            "atividades": [
                dict(r)
                for r in con.execute(
                    "SELECT registrada_em, tipo, resultado, anotacao FROM atividades WHERE lead_id=?", (lead_id,)
                )
            ],  # fmt: skip
            "observacao": "Dados pessoais do contato nunca foram enviados à IA.",
        }
        repositorio.auditar(con, ator, "exportacao_titular", "leads", lead_id, {})
    return json.dumps(dados, ensure_ascii=False, indent=2, default=str)


def excluir_titular(lead_id: int, ator: str) -> None:
    """Apaga os dados pessoais do contato e as anotações. Os dados da empresa e a trilha de auditoria ficam."""
    momento = tempo.iso()
    with conectar() as con:
        con.execute("DELETE FROM contatos WHERE lead_id=?", (lead_id,))
        con.execute("UPDATE atividades SET anotacao=? WHERE lead_id=? AND anotacao IS NOT NULL AND anotacao != ''",
                    (REMOVIDO, lead_id))  # fmt: skip
        con.execute("UPDATE leads SET observacao=NULL, atualizado_em=? WHERE id=?", (momento, lead_id))
        repositorio.auditar(con, ator, "exclusao_titular", "leads", lead_id, {"quando": momento})
    registrar_opt_out(lead_id, ator, "Exclusão de dados pedida pelo titular")


def candidatos_retencao(dias: int) -> list[int]:
    corte = tempo.daqui(dias=-dias)
    inativas = (estados.DESCARTADO, estados.PERDIDO, estados.NUTRICAO, estados.RETIDO, estados.CAPTURADO)
    with conectar() as con:
        return [r["id"] for r in con.execute(
            f"""SELECT l.id FROM leads l WHERE l.criado_em < ? AND l.etapa IN ({",".join("?" * len(inativas))})
                AND EXISTS (SELECT 1 FROM contatos c WHERE c.lead_id=l.id)
                AND NOT EXISTS (SELECT 1 FROM atividades a WHERE a.lead_id=l.id AND a.registrada_em >= ?)""",
            (corte, *inativas, corte))]  # fmt: skip


def aplicar_retencao(dias: int, ator: str) -> int:
    """Remove os dados pessoais dos leads parados além do prazo de retenção."""
    ids = candidatos_retencao(dias)
    with conectar() as con:
        for lead_id in ids:
            con.execute("DELETE FROM contatos WHERE lead_id=?", (lead_id,))
            con.execute("UPDATE atividades SET anotacao=? WHERE lead_id=? AND anotacao != ''", (REMOVIDO, lead_id))
        repositorio.auditar(con, ator, "retencao_aplicada", "leads", None, {"dias": dias, "leads": len(ids)})
    return len(ids)
