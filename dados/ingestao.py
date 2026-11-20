"""Ingestão: toda origem passa por aqui.

1. Grava o registro como chegou (bronze, leads_brutos).
2. Aplica as regras de entrada: campo obrigatório, deduplicação e base legal.
3. Cria o lead (prata, leads) e separa os dados pessoais (contatos).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field

from banco import repositorio
from banco.conexao import conectar
from nucleo import estados, tempo

from . import base_ficticia, limpeza

CANAIS = {
    "formulario": "Formulário manual",
    "planilha": "Planilha",
    "cnpj_lista": "Lista de CNPJs",
    "webhook_site": "Site / webhook (simulado)",
    "base_ficticia": "Base fictícia",
}
ORIGENS_ROTULO = {
    "site": "Site",
    "formulario": "Formulário",
    "evento": "Evento",
    "indicacao": "Indicação",
    "linkedin": "LinkedIn",
    "planilha": "Planilha",
    "cnpj_lista": "Lista de CNPJs",
}
REGRAS_ENTRADA = [
    "Obrigatório: nome da empresa ou CNPJ válido.",
    "Deduplicação: mesmo CNPJ, ou mesmo nome, cidade e UF quando não há CNPJ.",
    "Consentimento: sem base legal o lead entra, mas fica Retido LGPD e não recebe contato.",
    "Dados pessoais do contato ficam em tabela separada e nunca vão para a IA.",
]


@dataclass
class ResultadoIngestao:
    lote: str
    criados: list[int] = field(default_factory=list)
    duplicados: list[tuple[str, int]] = field(default_factory=list)
    rejeitados: list[tuple[str, str]] = field(default_factory=list)

    @property
    def resumo(self) -> str:
        return (
            f"{len(self.criados)} lead(s) criados, {len(self.duplicados)} duplicado(s) ignorados, "
            f"{len(self.rejeitados)} rejeitado(s)."
        )


def _inserir_lead(con: sqlite3.Connection, reg: dict, canal: str, ator: str, chave: str, ficticio: bool,
                  momento: str) -> int:  # fmt: skip
    empresa, contato = limpeza.separar_contato(reg)
    sinais = reg.get("sinais_simulados") or {}
    try:
        funcionarios = int(empresa["funcionarios"]) if empresa["funcionarios"] else None
    except ValueError:
        funcionarios = None
    cur = con.execute(
        """INSERT INTO leads (criado_em, atualizado_em, origem, canal, cnpj, chave_dedup, razao_social, nome_fantasia,
               cnae, setor, porte, funcionarios, cidade, uf, site, descricao, situacao_cadastral, interesse,
               observacao, sinais_simulados, dados_cnpjws, base_ficticia)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            momento, momento, empresa["origem"] or ("formulario" if canal == "formulario" else canal),
            canal, empresa["cnpj"] or None, chave, empresa["razao_social"], empresa["nome_fantasia"] or None,
            empresa["cnae"] or None, empresa["setor"] or None, empresa["porte"] or None, funcionarios,
            empresa["cidade"] or None, empresa["uf"] or None, empresa["site"] or None,
            empresa["descricao"] or None, reg.get("situacao_cadastral") or None, empresa["interesse"],
            reg.get("observacao") or None, json.dumps(sinais, ensure_ascii=False),
            json.dumps(reg["dados_cnpjws"], ensure_ascii=False) if reg.get("dados_cnpjws") else None,
            int(ficticio),
        ),
    )  # fmt: skip
    lead_id = int(cur.lastrowid)
    if any(contato.values()):
        con.execute(
            "INSERT INTO contatos (lead_id, nome, cargo, email, telefone, criado_em) VALUES (?,?,?,?,?,?)",
            (lead_id, contato["nome"], contato["cargo"], contato["email"], contato["telefone"], momento),
        )
    con.execute(
        "INSERT INTO consentimentos (lead_id, base_legal, consentiu, canal, registrado_em, registrado_por, opt_out_em,"
        " observacao) VALUES (?,?,?,?,?,?,?,?)",
        (lead_id, reg["base_legal"], int(bool(reg["consentimento"])), canal, momento, ator,
         momento if reg.get("opt_out") else None, "Opt-out registrado na origem" if reg.get("opt_out") else None),
    )  # fmt: skip
    if reg.get("opt_out"):
        con.execute("UPDATE leads SET opt_out=1 WHERE id=?", (lead_id,))
    estados.registrar_entrada(con, lead_id, ator, momento)
    return lead_id


def receber(registros: list[dict], canal: str, ator: str, ficticio: bool = False,
            con: sqlite3.Connection | None = None, momento: str | None = None) -> ResultadoIngestao:  # fmt: skip
    """Recebe registros já com campos padrão (vindos de qualquer origem)."""
    if canal not in CANAIS:
        raise ValueError(f"Canal desconhecido: {canal}")
    resultado = ResultadoIngestao(lote=f"cap-{uuid.uuid4().hex[:8]}")

    def _processar(c: sqlite3.Connection) -> None:
        for bruto in registros:
            instante = momento or tempo.iso()
            original = bruto.get("_bruto") or {k: v for k, v in bruto.items() if not k.startswith("_")}
            cur = c.execute(
                "INSERT INTO leads_brutos (recebido_em, origem, lote, payload, base_ficticia) VALUES (?,?,?,?,?)",
                (instante, canal, resultado.lote, json.dumps(original, ensure_ascii=False, default=str),
                 int(ficticio)),
            )  # fmt: skip
            bruto_id = cur.lastrowid
            reg, problemas = limpeza.padronizar(bruto)
            for extra in ("sinais_simulados", "situacao_cadastral", "dados_cnpjws", "opt_out", "observacao"):
                if extra in bruto:
                    reg[extra] = bruto[extra]
            nome = reg["razao_social"] or reg["cnpj"]
            if "Sem nome da empresa nem CNPJ válido" in problemas:
                c.execute("UPDATE leads_brutos SET status='Rejeitado', problemas=? WHERE id=?",
                          (json.dumps(problemas, ensure_ascii=False), bruto_id))  # fmt: skip
                resultado.rejeitados.append((nome or "(sem nome)", "Sem nome da empresa nem CNPJ válido"))
                continue
            if not reg["razao_social"]:
                reg["razao_social"] = f"CNPJ {reg['cnpj']}"
            chave = limpeza.chave_dedup(reg)
            existente = c.execute("SELECT id FROM leads WHERE chave_dedup=?", (chave,)).fetchone()
            if existente:
                problemas.append(f"Duplicado do lead #{existente['id']}")
                c.execute(
                    "UPDATE leads_brutos SET status='Rejeitado', problemas=?, lead_id=? WHERE id=?",
                    (json.dumps(problemas, ensure_ascii=False), existente["id"], bruto_id),
                )
                resultado.duplicados.append((nome, int(existente["id"])))
                continue
            lead_id = _inserir_lead(c, reg, canal, ator, chave, ficticio, instante)
            c.execute(
                "UPDATE leads_brutos SET status='Recebido', problemas=?, lead_id=? WHERE id=?",
                (json.dumps(problemas, ensure_ascii=False), lead_id, bruto_id),
            )
            resultado.criados.append(lead_id)
        repositorio.auditar(c, ator, "captura", "leads_brutos", resultado.lote,
                            {"canal": canal, "criados": len(resultado.criados),
                             "duplicados": len(resultado.duplicados),
                             "rejeitados": len(resultado.rejeitados)})  # fmt: skip

    if con is not None:
        _processar(con)
    else:
        with conectar() as c:
            _processar(c)
    return resultado


# ---------- base fictícia ----------
def registro_ficticio(empresa: dict) -> dict:
    """Converte uma empresa da base fictícia para o formato de captura."""
    contato = empresa["contato"]
    return {
        **{
            k: empresa[k]
            for k in (
                "razao_social",
                "nome_fantasia",
                "cnpj",
                "cnae",
                "setor",
                "porte",
                "cidade",
                "uf",
                "site",
                "descricao",
                "interesse",
                "origem",
                "situacao_cadastral",
                "sinais_simulados",
                "observacao",
            )
        },  # fmt: skip
        "funcionarios": str(empresa["funcionarios"]),
        "contato_nome": contato["nome"],
        "cargo": contato["cargo"],
        "email": contato["email"],
        "telefone": contato["telefone"],
        "base_legal": empresa["base_legal"],
        "consentimento": "sim" if empresa["consentiu"] else "",
        "opt_out": empresa["opt_out"],
    }


def ficticias_disponiveis() -> list[dict]:
    """Empresas da base fictícia que ainda não entraram no funil."""
    with conectar() as con:
        usadas = {r[0] for r in con.execute("SELECT chave_dedup FROM leads")}
    return [e for e in base_ficticia.gerar_empresas() if f"cnpj:{e['cnpj']}" not in usadas]


def cnpjs_ficticios() -> set[str]:
    return {e["cnpj"] for e in base_ficticia.gerar_empresas()}


def carregar_ficticias(quantidade: int, ator: str, canal: str = "base_ficticia") -> ResultadoIngestao:
    escolhidas = ficticias_disponiveis()[:quantidade]
    return receber([registro_ficticio(e) for e in escolhidas], canal, ator, ficticio=True)


# ---------- entrada em tempo real ----------
STATUS_POR_ETAPA = {
    estados.CAPTURADO: "Recebido",
    estados.EM_TRATAMENTO: "Na fila da IA",
    estados.RETIDO: "Retido",
}


def entrada_recente(limite: int = 30) -> list[dict]:
    with conectar() as con:
        linhas = con.execute(
            """SELECT b.id, b.recebido_em, b.origem canal, b.status status_bruto, b.problemas, b.base_ficticia,
                      l.id lead_id, l.razao_social, l.etapa
               FROM leads_brutos b LEFT JOIN leads l ON l.id = b.lead_id
               ORDER BY b.id DESC LIMIT ?""",
            (limite,),
        ).fetchall()
    saida = []
    for r in linhas:
        payload_nome = r["razao_social"] or ""
        status = "Rejeitado" if r["status_bruto"] == "Rejeitado" else STATUS_POR_ETAPA.get(r["etapa"], "Tratado")
        saida.append({
            "recebido_em": tempo.fmt(r["recebido_em"]),
            "empresa": payload_nome,
            "canal": CANAIS.get(r["canal"], r["canal"]),
            "status": status,
            "etapa": r["etapa"] or "",
            "problemas": "; ".join(json.loads(r["problemas"] or "[]")),
            "lead_id": r["lead_id"],
            "ficticio": bool(r["base_ficticia"]),
        })  # fmt: skip
    return saida
