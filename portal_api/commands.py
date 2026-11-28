"""Contratos e adaptação dos serviços de domínio para a homologação."""

import sqlite3
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

import catalogo
from banco import prospeccao, repositorio
from dados import base_ficticia, cnpja, ingestao
from ia import orquestrador, propensao, segmentos
from nucleo import agenda, comercial, config, estados, gestao_leads, lgpd, revisao, tempo, triagem

Positive = Annotated[int, Field(gt=0)]
Cnpj = Annotated[str, StringConstraints(pattern=r"^[0-9]{14}$")]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
BantField = Literal["orcamento", "autoridade", "necessidade", "prazo"]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CompanySearch(Payload):
    uf: str = Field(pattern=r"^[A-Z]{2}$")
    municipio_ibge: int = Field(ge=1000000, le=9999999)
    ano: int = Field(ge=2000, le=2100)
    mes: int = Field(ge=1, le=12)
    cnae: str = Field(pattern=r"^[0-9]{7}$")


class Search(CompanySearch):
    acao: Literal["buscar"]


class Import(Payload):
    acao: Literal["importar"]
    campanha: Positive
    cnpjs: list[Cnpj] = Field(min_length=1, max_length=10)


class Target(Payload):
    id: Positive
    versao: int = Field(ge=0)


class LeadCommand(Payload):
    leads: list[Target] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def distinct_leads(self):
        if len({lead.id for lead in self.leads}) != len(self.leads):
            raise ValueError("Seleção repetida.")
        return self


class Process(LeadCommand):
    acao: Literal["processar"]


class Assign(LeadCommand):
    acao: Literal["triagem", "atribuir"]
    bdr: Positive
    motivo: Short


class Status(LeadCommand):
    acao: Literal["status"]
    etapa: Short
    motivo: Short | None = None
    justificativa: Short
    canal: str = Field(default="", max_length=30)
    resultado: str = Field(default="", max_length=60)


class SingleLead(LeadCommand):
    leads: list[Target] = Field(min_length=1, max_length=1)


class Review(SingleLead):
    acao: Literal["revisar"]
    decisao: Literal["aprovar", "ajustar", "descartar"]
    motivo: Short
    classificacao: Short | None = None
    solucao: Short | None = None
    motivo_descarte: Short | None = None


class Activity(SingleLead):
    acao: Literal["atividade"]
    tipo: Literal["Ligação", "E-mail", "WhatsApp", "Reunião", "Nota"]
    resultado: str = Field(default="", max_length=60)
    anotacao: str = Field(default="", max_length=1000)
    proxima_acao: str = Field(default="", max_length=180)


class Cadence(SingleLead):
    acao: Literal["cadencia"]
    passo: Positive
    feito: bool


class Bant(SingleLead):
    acao: Literal["bant"]
    valores: dict[BantField, Annotated[str, StringConstraints(max_length=200)]] = Field(min_length=1)
    confirmacoes: dict[BantField, bool] = Field(default_factory=dict)


class Return(SingleLead):
    acao: Literal["retorno"]
    titulo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=180)]
    inicio: datetime


class Opportunity(SingleLead):
    acao: Literal["oportunidade"]
    solucoes: list[Short] = Field(min_length=1, max_length=10)
    valor: float | None = Field(default=None, ge=0, le=100_000_000)
    previsao: date | None = None


class Handoff(SingleLead):
    acao: Literal["passagem"]
    executivo: Positive
    inicio: datetime
    solucoes: list[Short] = Field(min_length=1, max_length=10)


class Move(SingleLead):
    acao: Literal["crm-status"]
    etapa: Short
    motivo: Short | None = None
    justificativa: Short


class Schedule(SingleLead):
    acao: Literal["agenda-criar"]
    tipo: Literal["Tarefa interna", "Retorno", "Reunião planejada", "Reunião confirmada"]
    titulo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=180)]
    inicio: datetime


class ResolveSchedule(SingleLead):
    acao: Literal["agenda-resolver", "agenda-reagendar"]
    compromisso: Positive
    status: Literal["Concluído", "Cancelado"] | None = None
    inicio: datetime | None = None

    @model_validator(mode="after")
    def require_fields(self):
        if self.acao == "agenda-reagendar" and (self.inicio is None or self.status is not None):
            raise ValueError("Informe o novo horário.")
        if self.acao == "agenda-resolver" and (self.status is None or self.inicio is not None):
            raise ValueError("Informe o status de conclusão.")
        return self


CRM_ACTIONS = {"oportunidade", "crm-status", "agenda-criar", "agenda-resolver", "agenda-reagendar"}


def crm_moves(actor: dict, etapa: str) -> list[str]:
    if etapa not in estados.ETAPAS_FUNIL:
        return []
    if actor["papel"] == "bdr":
        return [estados.QUALIFICADO] if etapa == estados.EM_CONTATO else []
    allowed = (estados.QUALIFICADO, estados.PROPOSTA, estados.GANHO, estados.PERDIDO, estados.NUTRICAO)
    return [stage for stage in allowed if stage in estados.TRANSICOES.get(etapa, set())]


def horario(data: datetime) -> str:
    return tempo.iso(data if data.tzinfo else data.replace(tzinfo=tempo.FUSO))


def apply_crm(con: sqlite3.Connection, actor: dict, lead: sqlite3.Row, body) -> dict:
    ident = lead["id"]
    if isinstance(body, Opportunity):
        if lead["etapa"] not in estados.ETAPAS_FUNIL:
            raise ValueError("Oportunidades estão disponíveis no funil comercial.")
        comercial.salvar_oportunidade(
            ident,
            actor,
            list(dict.fromkeys(body.solucoes)),
            body.valor,
            lead["executivo_id"],
            body.previsao.isoformat() if body.previsao else None,
        )
        return {"total": 1}
    if isinstance(body, Handoff):
        if (
            not con.execute(
                "SELECT 1 FROM usuarios WHERE id=? AND papel='executivo' AND ativo=1 AND demonstracao=1",
                (body.executivo,),
            ).fetchone()
            or not set(body.solucoes) <= catalogo.ids()
        ):
            raise ValueError("Selecione um executivo ativo e soluções do catálogo.")
        inicio = horario(body.inicio)
        if con.execute(
            """SELECT 1 FROM agenda_compromissos WHERE responsavel_id=? AND inicio_em=? AND status='Pendente'
            AND tipo IN ('Reunião planejada','Reunião confirmada')""",
            (body.executivo, inicio),
        ).fetchone():
            raise ValueError("O executivo já tem uma reunião nesse horário.")
        comercial.qualificar_e_agendar(
            ident, actor, inicio, body.executivo, list(dict.fromkeys(body.solucoes)), usar_llm=False
        )
        return {"etapa": estados.REUNIAO}
    if isinstance(body, Move):
        if body.etapa not in crm_moves(actor, lead["etapa"]):
            raise ValueError("Transição indisponível nesta etapa ou perfil.")
        if body.etapa == estados.QUALIFICADO and lead["etapa"] == estados.EM_CONTATO:
            return {"etapa": gestao_leads.mudar_status(ident, actor, body.etapa, body.justificativa)}
        if body.etapa in estados.ETAPAS_DE_CONTATO and not lgpd.base_para_contato(con, ident):
            raise ValueError("Avanço bloqueado enquanto a base legal estiver pendente.")
        return {"etapa": comercial.mover_no_funil(ident, actor, body.etapa, body.motivo, body.justificativa)}
    if isinstance(body, Schedule):
        if body.tipo != "Tarefa interna":
            require_contact(con, lead)
        return {
            "compromisso": agenda.agendar(
                ident,
                actor,
                body.tipo,
                body.titulo,
                horario(body.inicio),
                responsavel_id=None if actor["papel"] == "gestor" else actor["id"],
            )
        }
    item = con.execute(
        "SELECT * FROM agenda_compromissos WHERE id=? AND lead_id=?", (body.compromisso, ident)
    ).fetchone()
    if not item or (actor["papel"] != "gestor" and item["responsavel_id"] != actor["id"]):
        raise HTTPException(404, "Compromisso não encontrado.")
    if item["tipo"] != "Tarefa interna" and body.status != "Cancelado":
        require_contact(con, lead)
    if body.inicio is not None:
        agenda.reagendar(body.compromisso, actor, horario(body.inicio))
    else:
        agenda.concluir(body.compromisso, actor, body.status)
    return {"compromisso": body.compromisso}


Command = Annotated[
    Search
    | Import
    | Process
    | Assign
    | Status
    | Review
    | Activity
    | Cadence
    | Bant
    | Return
    | Opportunity
    | Handoff
    | Move
    | Schedule
    | ResolveSchedule,
    Field(discriminator="acao"),
]

MANAGEMENT = {"buscar", "importar", "processar", "revisar", "triagem", "atribuir"}
COMPANY_FIELDS = ("cnpj", "razao_social", "cidade", "uf", "cnae", "data_abertura")


def campaign_data(campaign: prospeccao.Busca) -> dict:
    return {
        "id": campaign.id,
        "tag": campaign.tag,
        "items": [{field: company[field] for field in COMPANY_FIELDS} for company in campaign.empresas],
    }


def simulated_search(body: Search, actor: dict) -> dict:
    """Amostra determinística de CNPJs da base fictícia, sem chamar o fornecedor."""
    filters = cnpja.filtros("Todos", body.uf, body.municipio_ibge, body.ano, body.mes, body.cnae, limite=10)
    municipality = f"Município {body.municipio_ibge}"
    records = [
        {
            "taxId": company["cnpj"],
            "company": {"name": company["razao_social"]},
            "alias": company["nome_fantasia"],
            "address": {"city": municipality, "state": body.uf},
            "mainActivity": {"id": body.cnae, "text": company["setor"]},
            "founded": f"{body.ano:04d}-{body.mes:02d}-01",
        }
        for company in base_ficticia.gerar_empresas()[-10:]
    ]
    result = cnpja.normalizar_resposta({"records": records, "count": len(records)})
    campaign = prospeccao.registrar(
        "cnpja",
        "Todos",
        municipality,
        body.uf,
        body.ano,
        body.mes,
        body.cnae,
        filters,
        result.empresas,
        result.total,
        actor["login"],
    )
    return campaign_data(campaign)


def find_targets(
    con: sqlite3.Connection, actor: dict, body: LeadCommand, *, check_version: bool = True
) -> list[sqlite3.Row]:
    ids = [lead.id for lead in body.leads]
    rows = {
        row["id"]: row
        for row in con.execute(
            f"SELECT * FROM leads WHERE id IN ({','.join('?' for _ in ids)}) AND base_ficticia=1 AND opt_out=0",
            ids,
        )
    }
    if any(
        target.id not in rows
        or (actor["papel"] == "bdr" and rows[target.id]["responsavel_id"] != actor["id"])
        or (actor["papel"] == "executivo" and rows[target.id]["executivo_id"] != actor["id"])
        for target in body.leads
    ):
        raise HTTPException(404, "Um ou mais leads estão fora da carteira disponível.")
    if check_version and any(rows[target.id]["versao"] != target.versao for target in body.leads):
        raise HTTPException(409, "O lead mudou em outra operação. Atualize a ficha antes de repetir.")
    return [rows[target.id] for target in body.leads]


def require_contact(con: sqlite3.Connection, lead: sqlite3.Row) -> None:
    if lead["etapa"] not in estados.ETAPAS_DE_CONTATO or not lgpd.base_para_contato(con, lead["id"]):
        raise ValueError("Contato bloqueado pela etapa ou base legal.")


def require_local_models(con: sqlite3.Connection) -> None:
    # Os serviços treinam automaticamente quando falta um artefato. Isso é
    # reservado ao preparo do sandbox, fora das transações de comando.
    folder = config.pasta_modelos()
    for name in (propensao.NOME, segmentos.NOME):
        active = con.execute(
            "SELECT caminho FROM modelos_registro WHERE nome=? AND ativo=1 ORDER BY id DESC LIMIT 1", (name,)
        ).fetchone()
        if active is None:
            raise HTTPException(503, "Modelos locais indisponíveis. Prepare uma nova base de homologação.")
        artifact = folder / active["caminho"]
        if artifact.parent != folder or artifact.is_symlink() or not artifact.is_file():
            raise HTTPException(503, "Modelos locais indisponíveis. Prepare uma nova base de homologação.")


def apply(con: sqlite3.Connection, actor: dict, body: Command) -> dict:
    if isinstance(body, Search):
        return simulated_search(body, actor)
    if isinstance(body, Import):
        campaign = prospeccao.carregar(body.campanha)
        if campaign is None or campaign.provedor != "cnpja":
            raise HTTPException(404, "Busca de homologação não encontrada.")
        if not set(body.cnpjs) <= ingestao.cnpjs_ficticios():
            raise ValueError("A seleção contém empresa indisponível para importação.")
        for cnpj in set(body.cnpjs):
            found = con.execute("SELECT opt_out,base_ficticia FROM leads WHERE cnpj=?", (cnpj,)).fetchone()
            if found and (found["opt_out"] or not found["base_ficticia"]):
                raise ValueError("A seleção contém empresa indisponível para importação.")
        imported = prospeccao.importar(body.campanha, body.cnpjs, actor["login"], ficticio=True)
        return {
            "criados": len(imported.criados),
            "duplicados": len(imported.duplicados),
            "rejeitados": len(imported.rejeitados),
        }
    rows = find_targets(con, actor, body)
    ids = [row["id"] for row in rows]
    if isinstance(body, Process):
        if any(row["etapa"] not in orquestrador.TRATAVEIS for row in rows):
            raise ValueError("A seleção contém lead fora das etapas de processamento.")
        require_local_models(con)
        result = orquestrador.tratar(ids, actor["login"], usar_llm=False)
        return {"total": result["total"], "destinos": result["destinos"]}
    if isinstance(body, Assign):
        if not con.execute(
            "SELECT 1 FROM usuarios WHERE id=? AND papel='bdr' AND ativo=1 AND demonstracao=1", (body.bdr,)
        ).fetchone():
            raise ValueError("Selecione um BDR ativo da homologação.")
        if body.acao == "triagem":
            triagem.encaminhar(ids, actor, body.bdr, body.motivo)
            return {"total": len(ids)}
        if len(body.motivo) < 10:
            raise ValueError("Justifique a atribuição com pelo menos 10 caracteres.")
        for lead in rows:
            if lead["etapa"] not in comercial.ETAPAS_ATIVAS_BDR:
                raise ValueError("Use a triagem para encaminhar leads fora da fila ativa.")
            if lead["responsavel_id"] != body.bdr:
                comercial.atribuir(con, lead["id"], body.bdr, actor["login"], body.motivo)
        return {"total": len(ids)}
    if isinstance(body, Status):
        for lead in rows:
            gestao_leads.mudar_status(
                lead["id"],
                actor,
                body.etapa,
                body.justificativa,
                motivo=body.motivo,
                canal_contato=body.canal,
                resultado_contato=body.resultado,
            )
        return {"total": len(ids)}

    lead = rows[0]
    ident = lead["id"]
    if body.acao in CRM_ACTIONS or isinstance(body, Handoff):
        return apply_crm(con, actor, lead, body)
    if isinstance(body, Review):
        if body.decisao == "ajustar":
            if body.classificacao not in revisao.CLASSES_REVISAO:
                raise ValueError("Selecione uma classificação válida para o ajuste.")
            if body.solucao and body.solucao not in catalogo.ids():
                raise ValueError("Solução inválida.")
        elif body.classificacao or body.solucao:
            raise ValueError("Forneça ajustes apenas na decisão Ajustar.")
        if body.decisao == "descartar" and body.motivo_descarte not in estados.MOTIVOS:
            raise ValueError("Selecione o motivo do descarte.")
        return {
            "etapa": revisao.resolver(
                ident,
                actor,
                body.decisao,
                body.motivo,
                solucao_id=body.solucao,
                classificacao=body.classificacao,
                motivo_descarte=body.motivo_descarte,
            )
        }
    if isinstance(body, Activity):
        if body.tipo in comercial.TIPOS_CONTATO:
            require_contact(con, lead)
            if body.resultado not in comercial.RESULTADOS:
                raise ValueError("Selecione o resultado real do contato.")
        return {
            "etapa": comercial.registrar_atividade(
                ident,
                actor,
                body.tipo,
                body.resultado,
                body.anotacao,
                proxima_acao=body.proxima_acao or lead["proxima_acao"] or "",
                retorno_em=lead["retorno_em"],
            )
        }
    if isinstance(body, Cadence):
        require_contact(con, lead)
        if not con.execute("SELECT 1 FROM cadencia_passos WHERE id=? AND lead_id=?", (body.passo, ident)).fetchone():
            raise HTTPException(404, "Passo de cadência não encontrado.")
        comercial.marcar_passo(body.passo, body.feito, actor)
        repositorio.auditar(con, actor["login"], "cadencia", "leads", ident, {"passo": body.passo, "feito": body.feito})
    elif isinstance(body, Bant):
        comercial.salvar_bant(ident, actor, body.valores, body.confirmacoes)
    elif isinstance(body, Return):
        require_contact(con, lead)
        inicio = body.inicio if body.inicio.tzinfo else body.inicio.replace(tzinfo=tempo.FUSO)
        return {"compromisso": agenda.agendar(ident, actor, "Retorno", body.titulo, tempo.iso(inicio))}
    return {"total": 1}
