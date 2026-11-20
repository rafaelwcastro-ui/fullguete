"""Operações do time comercial: distribuição, cadência, atividades, BANT, correções e oportunidades."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from banco import repositorio

from . import estados, tempo

CADENCIA_PADRAO = [
    (0, "Ligação", "Primeira ligação com o roteiro de abertura"),
    (0, "E-mail", "E-mail de apresentação"),
    (2, "WhatsApp", "Mensagem curta retomando o assunto"),
    (5, "Ligação", "Segunda ligação com as perguntas de descoberta"),
    (8, "E-mail", "E-mail de encerramento da cadência"),
]
ETAPAS_ATIVAS_BDR = (estados.FILA_BDR, estados.EM_CONTATO, estados.QUALIFICADO)


def escolher_bdr(con: sqlite3.Connection) -> int | None:
    """BDR com a menor fila ativa (empate: o de menor id)."""
    linha = con.execute(
        f"""SELECT u.id, COUNT(l.id) fila FROM usuarios u
            LEFT JOIN leads l ON l.responsavel_id = u.id AND l.etapa IN ({",".join("?" * len(ETAPAS_ATIVAS_BDR))})
            WHERE u.papel='bdr' AND u.ativo=1 GROUP BY u.id ORDER BY fila, u.id LIMIT 1""",
        ETAPAS_ATIVAS_BDR,
    ).fetchone()
    return int(linha["id"]) if linha else None


def atribuir(con: sqlite3.Connection, lead_id: int, usuario_id: int, ator: str, motivo: str,
             momento: str | None = None) -> None:  # fmt: skip
    momento = momento or tempo.iso()
    con.execute("UPDATE atribuicoes SET ativa=0 WHERE lead_id=? AND ativa=1", (lead_id,))
    con.execute(
        "INSERT INTO atribuicoes (lead_id, usuario_id, atribuido_em, atribuido_por, motivo) VALUES (?,?,?,?,?)",
        (lead_id, usuario_id, momento, ator, motivo),
    )
    con.execute("UPDATE leads SET responsavel_id=? WHERE id=?", (usuario_id, lead_id))
    repositorio.auditar(con, ator, "atribuicao", "leads", lead_id, {"usuario_id": usuario_id, "motivo": motivo})


def criar_cadencia(con: sqlite3.Connection, lead_id: int, inicio: str | None = None) -> None:
    if con.execute("SELECT 1 FROM cadencia_passos WHERE lead_id=? AND feito_em IS NULL", (lead_id,)).fetchone():
        return
    base = tempo.ler(inicio) or tempo.agora()
    con.executemany(
        "INSERT INTO cadencia_passos (lead_id, dia, canal, descricao, previsto_para) VALUES (?,?,?,?,?)",
        [(lead_id, dia, canal, desc, tempo.iso(base + timedelta(days=dia))) for dia, canal, desc in CADENCIA_PADRAO],
    )


TIPOS_ATIVIDADE = ["Ligação", "E-mail", "WhatsApp", "Reunião", "Nota"]
TIPOS_CONTATO = {"Ligação", "E-mail", "WhatsApp", "Reunião"}
RESULTADOS = ["Falou com o decisor", "Falou com outra pessoa", "Sem resposta", "Pediu retorno", "Sem interesse",
              "Interessado", "Reunião marcada"]  # fmt: skip
BANT_CAMPOS = {
    "orcamento": "Orçamento",
    "autoridade": "Autoridade",
    "necessidade": "Necessidade",
    "prazo": "Prazo",
}


def _lead(con: sqlite3.Connection, lead_id: int) -> sqlite3.Row:
    linha = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if linha is None:
        raise ValueError("Lead não encontrado.")
    return linha


def registrar_atividade(lead_id: int, usuario: dict, tipo: str, resultado: str, anotacao: str,
                        proxima_acao: str = "", retorno_em: str | None = None) -> str:  # fmt: skip
    """Grava a atividade. O primeiro contato tira o lead da fila e marca o passo da cadência."""
    from banco.conexao import conectar

    if tipo not in TIPOS_ATIVIDADE:
        raise ValueError("Tipo de atividade inválido.")
    if not (anotacao.strip() or resultado):
        raise ValueError("Registre o resultado ou uma anotação.")
    momento = tempo.iso()
    with conectar() as con:
        lead = _lead(con, lead_id)
        if lead["opt_out"]:
            raise ValueError("O titular pediu opt-out. Não registre novos contatos.")
        con.execute(
            "INSERT INTO atividades (lead_id, usuario_id, registrada_em, tipo, resultado, anotacao, proxima_acao, "
            "retorno_em) VALUES (?,?,?,?,?,?,?,?)",
            (lead_id, usuario["id"], momento, tipo, resultado, anotacao.strip(), proxima_acao.strip(), retorno_em),
        )
        con.execute("UPDATE leads SET proxima_acao=?, retorno_em=?, atualizado_em=? WHERE id=?",
                    (proxima_acao.strip() or None, retorno_em, momento, lead_id))  # fmt: skip
        etapa = lead["etapa"]
        if tipo in TIPOS_CONTATO:
            if not lead["primeiro_contato_em"]:
                con.execute("UPDATE leads SET primeiro_contato_em=? WHERE id=?", (momento, lead_id))
            passo = con.execute(
                "SELECT id FROM cadencia_passos WHERE lead_id=? AND canal=? AND feito_em IS NULL ORDER BY dia, id LIMIT 1",
                (lead_id, tipo),
            ).fetchone()
            if passo:
                con.execute("UPDATE cadencia_passos SET feito_em=? WHERE id=?", (momento, passo["id"]))
            if etapa == estados.FILA_BDR:
                estados.mudar(con, lead_id, estados.EM_CONTATO, usuario["login"], detalhe=f"{tipo}: {resultado}")
                etapa = estados.EM_CONTATO
        repositorio.auditar(
            con, usuario["login"], "atividade", "leads", lead_id, {"tipo": tipo, "resultado": resultado}
        )
    return etapa


def marcar_passo(passo_id: int, feito: bool, usuario: dict) -> None:
    from banco.conexao import conectar

    with conectar() as con:
        con.execute("UPDATE cadencia_passos SET feito_em=? WHERE id=?", (tempo.iso() if feito else None, passo_id))


def salvar_bant(lead_id: int, usuario: dict, valores: dict) -> None:
    from banco.conexao import conectar

    campos = {k: (valores.get(k) or "").strip() for k in BANT_CAMPOS}
    with conectar() as con:
        con.execute(
            "INSERT INTO bant (lead_id, orcamento, autoridade, necessidade, prazo, atualizado_em, usuario_id) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(lead_id) DO UPDATE SET orcamento=excluded.orcamento, "
            "autoridade=excluded.autoridade, necessidade=excluded.necessidade, prazo=excluded.prazo, "
            "atualizado_em=excluded.atualizado_em, usuario_id=excluded.usuario_id",
            (lead_id, campos["orcamento"], campos["autoridade"], campos["necessidade"], campos["prazo"], tempo.iso(),
             usuario["id"]),
        )  # fmt: skip
        repositorio.auditar(con, usuario["login"], "bant", "leads", lead_id, {k: bool(v) for k, v in campos.items()})


def corrigir_ia(lead_id: int, usuario: dict, campo: str, valor_correto: str, motivo: str) -> None:
    """O BDR concorda ou discorda da IA. Fica registrado e entra na taxa de concordância."""
    from banco.conexao import conectar

    from .revisao import registrar_correcao

    if campo not in ("solucao", "classificacao"):
        raise ValueError("Campo de correção inválido.")
    with conectar() as con:
        lead = _lead(con, lead_id)
        valor_ia = lead["solucao_principal"] if campo == "solucao" else lead["classificacao"]
        registrar_correcao(con, lead_id, usuario["id"], campo, valor_ia, valor_correto, motivo)
        if valor_correto != valor_ia:
            coluna = "solucao_principal" if campo == "solucao" else "classificacao"
            con.execute(f"UPDATE leads SET {coluna}=? WHERE id=?", (valor_correto, lead_id))


def qualificar_e_agendar(lead_id: int, usuario: dict, data_reuniao: str, executivo_id: int,
                         solucoes: list[str], observacao: str = "") -> None:  # fmt: skip
    """Qualifica o lead, marca a reunião e passa para o executivo de contas com o resumo automático."""
    from banco.conexao import conectar
    from ia import resumo

    with conectar() as con:
        lead = _lead(con, lead_id)
        if lead["etapa"] == estados.FILA_BDR:
            raise ValueError("Registre o primeiro contato antes de qualificar.")
        if lead["etapa"] not in (estados.EM_CONTATO, estados.QUALIFICADO):
            raise ValueError(f"O lead está em {lead['etapa']} e não pode ser qualificado agora.")
        bant = con.execute("SELECT necessidade FROM bant WHERE lead_id=?", (lead_id,)).fetchone()
        if not bant or not (bant["necessidade"] or "").strip():
            raise ValueError("Preencha pelo menos a Necessidade no BANT antes de qualificar.")
        if lead["etapa"] == estados.EM_CONTATO:
            estados.mudar(con, lead_id, estados.QUALIFICADO, usuario["login"], detalhe="BANT preenchido")
        estados.mudar(con, lead_id, estados.REUNIAO, usuario["login"], detalhe=f"Reunião em {tempo.fmt(data_reuniao)}")
        con.execute("UPDATE leads SET executivo_id=?, retorno_em=?, proxima_acao=? WHERE id=?",
                    (executivo_id, data_reuniao, "Reunião com o executivo de contas", lead_id))  # fmt: skip
        momento = tempo.iso()
        con.execute(
            "INSERT INTO atividades (lead_id, usuario_id, registrada_em, tipo, resultado, anotacao, proxima_acao, "
            "retorno_em) VALUES (?,?,?,?,?,?,?,?)",
            (lead_id, usuario["id"], momento, "Reunião", "Reunião marcada", observacao.strip(),
             "Reunião com o executivo de contas", data_reuniao),
        )  # fmt: skip
        con.execute(
            "INSERT INTO oportunidades (lead_id, solucoes, executivo_id, previsao_fechamento, criada_em, atualizada_em) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(lead_id) DO UPDATE SET solucoes=excluded.solucoes, "
            "executivo_id=excluded.executivo_id, atualizada_em=excluded.atualizada_em",
            (lead_id, repositorio._json(solucoes), executivo_id, None, momento, momento),
        )
        repositorio.auditar(con, usuario["login"], "passagem_executivo", "leads", lead_id,
                            {"executivo_id": executivo_id, "reuniao": data_reuniao})  # fmt: skip
    texto, motor = resumo.passagem(lead_id)
    with conectar() as con:
        con.execute("UPDATE oportunidades SET resumo_passagem=? WHERE lead_id=?", (texto, lead_id))
        repositorio.auditar(con, "agente_redator", "resumo_passagem", "leads", lead_id, {"motor": motor})


def mover_nutricao(lead_id: int, usuario: dict, motivo: str) -> None:
    from banco.conexao import conectar

    if not motivo.strip():
        raise ValueError("Explique por que o lead vai para nutrição.")
    with conectar() as con:
        estados.mudar(con, lead_id, estados.NUTRICAO, usuario["login"], detalhe=motivo.strip())


def fechar(lead_id: int, usuario: dict, ganho: bool, motivo: str | None = None, detalhe: str = "") -> None:
    """Ganho ou Perdido. O resultado vira rótulo de treino para a próxima versão do modelo."""

    from banco.conexao import conectar

    with conectar() as con:
        lead = _lead(con, lead_id)
        para = estados.GANHO if ganho else estados.PERDIDO
        estados.mudar(con, lead_id, para, usuario["login"], motivo=None if ganho else motivo, detalhe=detalhe or None)
        registrar_rotulo(con, lead_id, ganho, motivo, lead["solucao_principal"])


def registrar_rotulo(con: sqlite3.Connection, lead_id: int, ganho: bool, motivo: str | None,
                     solucao_id: str | None, momento: str | None = None) -> bool:  # fmt: skip
    """Feedback contínuo: grava o resultado do funil como exemplo de treino."""
    import json

    from dados.features import FEATURES

    linha = con.execute("SELECT features FROM leads_features WHERE lead_id=?", (lead_id,)).fetchone()
    if not linha:
        return False
    feats = json.loads(linha["features"])
    opp = con.execute("SELECT valor_mensal FROM oportunidades WHERE lead_id=?", (lead_id,)).fetchone()
    con.execute("DELETE FROM rotulos_treino WHERE lead_id=? AND fonte='funil'", (lead_id,))
    con.execute(
        "INSERT INTO rotulos_treino (lead_id, fonte, registrado_em, features, resultado, motivo, solucao_id, "
        "valor_mensal) VALUES (?,?,?,?,?,?,?,?)",
        (lead_id, "funil", momento or tempo.iso(), json.dumps({k: feats[k] for k in FEATURES}), int(ganho), motivo,
         solucao_id, opp["valor_mensal"] if opp else None),
    )  # fmt: skip
    repositorio.auditar(con, "sistema", "rotulo_treino", "leads", lead_id, {"ganho": ganho})
    return True
