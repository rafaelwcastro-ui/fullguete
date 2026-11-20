"""Carteira, pipeline e atividades privadas por usuário do portal."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone

import pandas as pd

from . import banco, dados

ETAPAS = ("A prospectar", "Em contato", "Em qualificação", "Reunião marcada", "Encerrado")
TIPOS_ATIVIDADE = ("Nota", "Ligação", "E-mail", "WhatsApp", "Reunião")
CAMPOS = (*dados.COLUNAS, "justificativa")


class ConflitoCarteira(RuntimeError):
    """O lead foi modificado depois que a ficha foi aberta."""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _dados(lead: dict) -> dict:
    return {campo: str(valor) if pd.notna(valor := lead.get(campo)) else "" for campo in CAMPOS}


def _atividade(con, carteira_id: int, tipo: str, descricao: str, agora: str) -> None:
    con.execute(
        "INSERT INTO atividades_bdr (carteira_id, tipo, descricao, registrada_em) VALUES (?, ?, ?, ?)",
        (carteira_id, tipo, descricao, agora),
    )


def adicionar(responsavel: str, ranking: pd.DataFrame, analise_id: int, origem: str, metodo: str) -> tuple[int, int]:
    """Envia leads selecionados para o BDR, preservando a atividade comercial."""
    inseridos = atualizados = 0
    prefixo = "demo:" if origem in {"Base fictícia", "exemplo_leads.csv"} else "real:"
    agora = _agora()
    with banco.conectar() as con:
        con.execute("BEGIN IMMEDIATE")
        for registro in ranking.to_dict("records"):
            lead = _dados(registro)
            cnpj = lead["cnpj"]
            chave_nome = prefixo + dados.identidade_empresa(lead["empresa"], lead["cidade"], lead["uf"])
            chave = prefixo + cnpj if re.fullmatch(r"[0-9]{14}", cnpj) else chave_nome
            atual = con.execute(
                "SELECT * FROM carteira_bdr WHERE responsavel=? AND chave=?", (responsavel, chave),
            ).fetchone()
            if atual is None and chave != chave_nome:
                # Se o BDR já conhecia a empresa pelo nome, incorpora o CNPJ à mesma ficha.
                atual = con.execute(
                    "SELECT * FROM carteira_bdr WHERE responsavel=? AND chave=?", (responsavel, chave_nome),
                ).fetchone()
            elif atual is None:
                iguais = con.execute(
                    "SELECT * FROM carteira_bdr WHERE responsavel=? AND chave_nome=?", (responsavel, chave_nome),
                ).fetchall()
                if len(iguais) == 1:
                    atual = iguais[0]
                    chave = atual["chave"]
            score = int(registro["score"])
            if atual is None:
                cur = con.execute(
                    """INSERT INTO carteira_bdr (responsavel, chave, chave_nome, dados, score, etapa,
                                                 origem, metodo, analise_id, atualizada_em)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (responsavel, chave, chave_nome, json.dumps(lead, ensure_ascii=False), score,
                     ETAPAS[0], origem, metodo, analise_id, agora),
                )
                _atividade(con, cur.lastrowid, "Entrada na carteira", f"Adicionado pelo ranking #{analise_id}.", agora)
                inseridos += 1
            elif analise_id > atual["analise_id"]:
                anteriores = json.loads(atual["dados"])
                preenchidos = {campo: valor for campo, valor in lead.items() if valor}
                anteriores.update(preenchidos)
                con.execute(
                    """UPDATE carteira_bdr SET chave=?, chave_nome=?, dados=?, score=?, origem=?, metodo=?,
                              analise_id=?, atualizada_em=? WHERE id=?""",
                    (chave, chave_nome, json.dumps(anteriores, ensure_ascii=False), score,
                     origem, metodo, analise_id, agora, atual["id"]),
                )
                atualizados += 1
    return inseridos, atualizados


def listar(responsavel: str) -> list[dict]:
    with banco.conectar() as con:
        linhas = con.execute(
            "SELECT * FROM carteira_bdr WHERE responsavel=? ORDER BY score DESC, id",
            (responsavel,),
        ).fetchall()
    return [{**json.loads(linha["dados"]), **dict(linha)} for linha in linhas]


def atividades(responsavel: str, carteira_id: int) -> list[dict]:
    with banco.conectar() as con:
        linhas = con.execute(
            """SELECT a.tipo, a.descricao, a.registrada_em
               FROM atividades_bdr a JOIN carteira_bdr c ON c.id=a.carteira_id
               WHERE c.responsavel=? AND c.id=? ORDER BY a.id DESC""",
            (responsavel, carteira_id),
        )
        return [dict(linha) for linha in linhas]


def registrar(
    responsavel: str, carteira_id: int, *, versao: int, etapa: str, proxima_acao: str,
    retorno: date | None, tipo: str, nota: str,
) -> None:
    if etapa not in ETAPAS or tipo not in TIPOS_ATIVIDADE:
        raise ValueError("Selecione uma etapa e um tipo de atividade válidos.")
    proxima_acao, nota = proxima_acao.strip(), nota.strip()
    if len(nota) > 2000 or len(proxima_acao) > 180:
        raise ValueError("O texto ultrapassa o limite da ficha.")
    data_retorno = retorno.isoformat() if retorno else None
    agora = _agora()
    with banco.conectar() as con:
        con.execute("BEGIN IMMEDIATE")
        atual = con.execute(
            "SELECT etapa, proxima_acao, retorno_em, versao FROM carteira_bdr WHERE id=? AND responsavel=?",
            (carteira_id, responsavel),
        ).fetchone()
        if atual is None or atual["versao"] != versao:
            raise ConflitoCarteira("A ficha mudou em outra sessão. Reabra a ficha para editar a versão atual.")

        mudancas = []
        if etapa != atual["etapa"]:
            mudancas.append(f"Etapa alterada de {atual['etapa']} para {etapa}.")
        if proxima_acao != atual["proxima_acao"]:
            mudancas.append(f"Próxima ação: {proxima_acao}." if proxima_acao else "Próxima ação removida.")
        if data_retorno != atual["retorno_em"]:
            mudancas.append(
                f"Retorno agendado para {retorno:%d/%m/%Y}." if retorno else "Data de retorno removida."
            )
        if not mudancas and not nota:
            raise ValueError("Altere algum campo ou escreva uma nota para registrar uma atividade.")

        con.execute(
            """UPDATE carteira_bdr SET etapa=?, proxima_acao=?, retorno_em=?, atualizada_em=?, versao=versao+1
               WHERE id=? AND responsavel=?""",
            (etapa, proxima_acao, data_retorno, agora, carteira_id, responsavel),
        )
        if mudancas:
            _atividade(con, carteira_id, "Atualização da ficha", " ".join(mudancas), agora)
        if nota:
            _atividade(con, carteira_id, tipo, nota, agora)
