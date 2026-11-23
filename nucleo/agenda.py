"""Agenda operacional do Fullguete: tarefas, retornos e reuniões por lead.

Agendar um compromisso não equivale a fazer contato nem muda a etapa do funil.
Toda alteração tem responsável, autoria e trilha de auditoria.
"""

from __future__ import annotations

from datetime import timedelta

from banco import repositorio
from banco.conexao import conectar

from . import lgpd, tempo

TIPOS = ("Tarefa interna", "Retorno", "Reunião planejada", "Reunião confirmada")
STATUS = ("Pendente", "Concluído", "Cancelado")


def _autorizar(con, lead, usuario: dict) -> None:
    papel = usuario.get("papel")
    if papel == "gestor":
        return
    if papel == "bdr" and lead["responsavel_id"] == usuario["id"]:
        return
    if papel == "executivo" and lead["executivo_id"] == usuario["id"]:
        return
    raise PermissionError("Você não está autorizado a operar a agenda deste lead.")


def _sincronizar_proxima_acao(con, lead_id: int) -> None:
    compromisso = con.execute(
        """SELECT titulo, inicio_em FROM agenda_compromissos
           WHERE lead_id=? AND status='Pendente' ORDER BY inicio_em, id LIMIT 1""",
        (lead_id,),
    ).fetchone()
    con.execute(
        "UPDATE leads SET proxima_acao=?, retorno_em=?, atualizado_em=? WHERE id=?",
        (
            compromisso["titulo"] if compromisso else None,
            compromisso["inicio_em"] if compromisso else None,
            tempo.iso(),
            lead_id,
        ),
    )


def agendar(
    lead_id: int,
    usuario: dict,
    tipo: str,
    titulo: str,
    inicio_em: str,
    descricao: str = "",
    responsavel_id: int | None = None,
) -> int:
    """Cria um compromisso e atualiza a próxima ação sem fingir avanço no CRM."""
    if tipo not in TIPOS:
        raise ValueError("Tipo de compromisso inválido.")
    titulo = titulo.strip()
    if len(titulo) < 4:
        raise ValueError("Descreva a ação com pelo menos 4 caracteres.")
    quando = tempo.ler(inicio_em)
    if quando is None or quando <= tempo.agora():
        raise ValueError("O compromisso deve ter data e hora futuras.")
    if quando > tempo.agora() + timedelta(days=366):
        raise ValueError("Agende compromissos até 12 meses à frente.")
    if len(descricao) > 2000:
        raise ValueError("Observação muito longa.")
    momento = tempo.iso()
    with conectar() as con:
        lead = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if lead is None:
            raise ValueError("Lead não encontrado.")
        _autorizar(con, lead, usuario)
        if lead["opt_out"]:
            raise ValueError("Opt-out ativo: não é possível criar compromisso comercial.")
        destino = responsavel_id if responsavel_id is not None else (lead["responsavel_id"] or usuario["id"])
        if usuario["papel"] != "gestor" and destino != usuario["id"]:
            raise PermissionError("Só o gestor pode atribuir compromissos a outros usuários.")
        responsavel = con.execute("SELECT id, ativo FROM usuarios WHERE id=?", (destino,)).fetchone()
        if responsavel is None or not responsavel["ativo"]:
            raise ValueError("Responsável não encontrado ou inativo.")
        if tipo == "Reunião confirmada":
            if not lgpd.base_para_contato(con, lead_id):
                raise ValueError("Reunião confirmada exige base legal de contato documentada.")
            if not lead["primeiro_contato_em"]:
                raise ValueError("Registre o contato efetivo antes de confirmar uma reunião.")
        if tipo in ("Reunião planejada", "Reunião confirmada"):
            existe = con.execute(
                """SELECT id FROM agenda_compromissos
                   WHERE responsavel_id=? AND inicio_em=? AND status='Pendente'
                     AND tipo IN ('Reunião planejada','Reunião confirmada')""",
                (destino, tempo.iso(quando)),
            ).fetchone()
            if existe:
                raise ValueError("Já existe uma reunião para este responsável nesse horário.")
        cur = con.execute(
            """INSERT INTO agenda_compromissos
               (lead_id, responsavel_id, criado_por, tipo, titulo, descricao,
                inicio_em, criado_em, atualizado_em)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                lead_id,
                destino,
                usuario["id"],
                tipo,
                titulo[:180],
                descricao.strip(),
                tempo.iso(quando),
                momento,
                momento,
            ),
        )
        _sincronizar_proxima_acao(con, lead_id)
        repositorio.auditar(
            con,
            usuario["login"],
            "agenda_criada",
            "leads",
            lead_id,
            {"compromisso_id": cur.lastrowid, "tipo": tipo, "inicio_em": tempo.iso(quando), "responsavel": destino},
        )
        return int(cur.lastrowid)


def listar(usuario: dict, *, status: str = "Pendente", limite: int = 100) -> list[dict]:
    """Retorna agenda de acordo com o acesso do gestor, BDR ou executivo."""
    if status not in (*STATUS, "Todos"):
        raise ValueError("Status de agenda inválido.")
    papel = usuario.get("papel")
    if papel not in ("gestor", "bdr", "executivo"):
        raise PermissionError("Perfil sem acesso à agenda.")
    where = ["1=1"]
    params: list = []
    if papel != "gestor":
        where.append("a.responsavel_id=?")
        params.append(usuario["id"])
    if status != "Todos":
        where.append("a.status=?")
        params.append(status)
    sql = (
        "SELECT a.*, l.razao_social, l.nome_fantasia, l.cnpj, l.etapa, l.opt_out, "
        "u.nome responsavel FROM agenda_compromissos a JOIN leads l ON l.id=a.lead_id "
        "JOIN usuarios u ON u.id=a.responsavel_id WHERE "
        + " AND ".join(where)
        + " ORDER BY CASE WHEN a.status='Pendente' THEN 0 ELSE 1 END, a.inicio_em, a.id LIMIT ?"
    )
    with conectar() as con:
        return [dict(r) for r in con.execute(sql, [*params, max(1, min(limite, 500))])]


def concluir(compromisso_id: int, usuario: dict, novo_status: str) -> None:
    if novo_status not in ("Concluído", "Cancelado"):
        raise ValueError("Use Concluído ou Cancelado para resolver o compromisso.")
    with conectar() as con:
        compromisso = con.execute(
            """SELECT a.*, l.responsavel_id lead_bdr, l.executivo_id lead_executivo
               FROM agenda_compromissos a JOIN leads l ON l.id=a.lead_id WHERE a.id=?""",
            (compromisso_id,),
        ).fetchone()
        if compromisso is None:
            raise ValueError("Compromisso não encontrado.")
        if usuario.get("papel") != "gestor" and compromisso["responsavel_id"] != usuario["id"]:
            raise PermissionError("Somente o responsável ou gestor pode concluir este compromisso.")
        if compromisso["status"] != "Pendente":
            raise ValueError("Este compromisso já foi resolvido.")
        agora = tempo.iso()
        con.execute(
            """UPDATE agenda_compromissos SET status=?, atualizado_em=?, concluido_em=?
               WHERE id=? AND status='Pendente'""",
            (novo_status, agora, agora if novo_status == "Concluído" else None, compromisso_id),
        )
        _sincronizar_proxima_acao(con, compromisso["lead_id"])
        repositorio.auditar(
            con,
            usuario["login"],
            "agenda_status",
            "leads",
            compromisso["lead_id"],
            {"compromisso_id": compromisso_id, "status": novo_status},
        )


def registrar_reuniao_passagem(
    con, lead_id: int, usuario: dict, executivo_id: int, quando: str, observacao: str
) -> int:
    """Integra a qualificação existente à agenda na mesma transação SQL."""
    existente = con.execute(
        """SELECT id FROM agenda_compromissos
           WHERE lead_id=? AND tipo='Reunião confirmada' AND inicio_em=? AND status='Pendente'""",
        (lead_id, quando),
    ).fetchone()
    if existente:
        return int(existente["id"])
    executivo = con.execute(
        "SELECT id FROM usuarios WHERE id=? AND papel='executivo' AND ativo=1",
        (executivo_id,),
    ).fetchone()
    if executivo is None:
        raise ValueError("Selecione um executivo ativo para a reunião.")
    momento = tempo.iso()
    cur = con.execute(
        """INSERT INTO agenda_compromissos
           (lead_id, responsavel_id, criado_por, tipo, titulo, descricao, inicio_em, criado_em, atualizado_em)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            lead_id,
            executivo_id,
            usuario["id"],
            "Reunião confirmada",
            "Reunião comercial com executivo de contas",
            observacao.strip(),
            quando,
            momento,
            momento,
        ),
    )
    _sincronizar_proxima_acao(con, lead_id)
    repositorio.auditar(
        con,
        usuario["login"],
        "agenda_reuniao_confirmada",
        "leads",
        lead_id,
        {"compromisso_id": cur.lastrowid, "executivo_id": executivo_id, "quando": quando},
    )
    return int(cur.lastrowid)
