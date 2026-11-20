"""Consultas e gravações usadas pelas páginas. SQL fica aqui, não nas telas."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .conexao import agora, conectar

CONFIG_PADRAO: dict[str, Any] = {
    "pesos_nota": {"aderencia": 0.5, "propensao": 0.3, "confianca": 0.2},
    "limites_classificacao": {"quente": 80, "morno": 60, "frio": 40},
    "confianca_minima_fila": 0.6,
    "sla_horas": {"Quente": 4, "Morno": 24},
    "retencao_dias": 365,
    "psi_limite": 0.2,
    # Estimativa de custo do modelo leve, em dólares por milhão de tokens. Ajuste ao preço vigente.
    "preco_tokens_usd_milhao": {"entrada": 0.10, "saida": 0.40},
    "tamanho_lote_ia": 15,
}


def _json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, default=str)


# ---------- configurações (com histórico) ----------
def config(chave: str) -> Any:
    with conectar() as con:
        linha = con.execute("SELECT valor FROM configuracoes WHERE chave=?", (chave,)).fetchone()
    return json.loads(linha["valor"]) if linha else CONFIG_PADRAO.get(chave)


def salvar_config(chave: str, valor: Any, ator: str, motivo: str = "", con: sqlite3.Connection | None = None) -> None:
    def _salvar(c: sqlite3.Connection) -> None:
        anterior = c.execute("SELECT valor FROM configuracoes WHERE chave=?", (chave,)).fetchone()
        novo = _json(valor)
        if anterior and anterior["valor"] == novo:
            return
        momento = agora()
        c.execute(
            "INSERT INTO configuracoes (chave, valor, atualizado_em, atualizado_por) VALUES (?,?,?,?) "
            "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, atualizado_em=excluded.atualizado_em, "
            "atualizado_por=excluded.atualizado_por",
            (chave, novo, momento, ator),
        )
        c.execute(
            "INSERT INTO configuracoes_historico "
            "(chave, valor_anterior, valor_novo, alterado_em, alterado_por, motivo) VALUES (?,?,?,?,?,?)",
            (chave, anterior["valor"] if anterior else None, novo, momento, ator, motivo),
        )

    if con is not None:
        _salvar(con)
    else:
        with conectar() as c:
            _salvar(c)


# ---------- auditoria ----------
def auditar(
    con: sqlite3.Connection, ator: str, acao: str, entidade: str, entidade_id: Any = None, detalhe: dict | None = None
) -> None:
    con.execute(
        "INSERT INTO auditoria (ocorrido_em, ator, acao, entidade, entidade_id, detalhe) VALUES (?,?,?,?,?,?)",
        (agora(), ator, acao, entidade, None if entidade_id is None else str(entidade_id), _json(detalhe or {})),
    )


# ---------- usuários ----------
def usuarios(papel: str | None = None, so_ativos: bool = True) -> list[dict]:
    sql = "SELECT id, login, nome, papel, senha_hash, meta_contatos_dia, demonstracao FROM usuarios WHERE 1=1"
    params: list[Any] = []
    if so_ativos:
        sql += " AND ativo=1"
    if papel:
        sql += " AND papel=?"
        params.append(papel)
    with conectar() as con:
        return [dict(r) for r in con.execute(sql + " ORDER BY papel, nome", params)]


def usuarios_para_login() -> dict[str, dict]:
    return {u["login"]: u for u in usuarios()}


# ---------- ICP ----------
def icp_ativo() -> dict | None:
    with conectar() as con:
        linha = con.execute("SELECT * FROM icp_versoes WHERE ativa=1 ORDER BY id DESC LIMIT 1").fetchone()
    if not linha:
        return None
    icp = dict(linha)
    for campo in ("setores", "portes", "palavras_chave"):
        icp[campo] = json.loads(icp[campo])
    return icp


def salvar_icp(icp: dict, ator: str, con: sqlite3.Connection | None = None) -> int:
    def _salvar(c: sqlite3.Connection) -> int:
        c.execute("UPDATE icp_versoes SET ativa=0")
        cur = c.execute(
            "INSERT INTO icp_versoes (criada_em, criada_por, nome, descricao, setores, portes, palavras_chave, ativa) "
            "VALUES (?,?,?,?,?,?,?,1)",
            (
                agora(),
                ator,
                icp["nome"],
                icp["descricao"],
                _json(icp.get("setores", [])),
                _json(icp.get("portes", [])),
                _json(icp.get("palavras_chave", [])),
            ),
        )
        auditar(c, ator, "icp_salvo", "icp_versoes", cur.lastrowid, {"nome": icp["nome"]})
        return int(cur.lastrowid)

    if con is not None:
        return _salvar(con)
    with conectar() as c:
        return _salvar(c)


# ---------- painéis ----------
def contar(tabela: str) -> int:
    permitidas = {"leads", "leads_brutos", "rotulos_treino", "usuarios", "tratamentos", "eventos_ia", "auditoria"}
    if tabela not in permitidas:
        raise ValueError(f"Tabela não permitida: {tabela}")
    with conectar() as con:
        return int(con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0])


def leads_por_etapa() -> dict[str, int]:
    with conectar() as con:
        return {r["etapa"]: r["n"] for r in con.execute("SELECT etapa, COUNT(*) n FROM leads GROUP BY etapa")}


def resumo_historico() -> dict:
    with conectar() as con:
        linha = con.execute("SELECT COUNT(*) n, COALESCE(SUM(resultado),0) ganhos FROM rotulos_treino").fetchone()
    return {"total": int(linha["n"]), "ganhos": int(linha["ganhos"])}
