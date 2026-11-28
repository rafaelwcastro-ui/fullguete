"""API autenticada para a homologação local do Fullguete."""

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from collections import deque
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

import catalogo
from banco import prospeccao
from banco.conexao import reutilizar_transacao
from dados import cnpja
from ia import orquestrador
from nucleo import auth, comercial, config, estados, gestao_leads, lgpd, revisao, tempo, triagem
from portal_api.commands import MANAGEMENT, Command, CompanySearch, LeadCommand, apply, campaign_data, find_targets
from portal_api.sandbox import MARKER

SESSION_SECONDS = 1800
MAX_SESSIONS = 256
ROLE_FIELDS = {"bdr": "responsavel_id", "executivo": "executivo_id"}
bearer = HTTPBearer(auto_error=False)
# Não reutilizar o hash de custo baixo usado no fallback de login do Streamlit.
DUMMY_HASH = auth.gerar_hash(secrets.token_urlsafe(32))


class Login(BaseModel):
    login: str = Field(min_length=1, max_length=128)
    senha: str = Field(min_length=1, max_length=512)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def scope(actor: dict) -> tuple[str, list]:
    """Escopo fechado por padrão; nunca aceitar papel ou usuário do cliente."""
    if actor["papel"] == "gestor":
        return "1=1", []
    field = ROLE_FIELDS.get(actor["papel"])
    if field is None:
        raise HTTPException(403, "Perfil não autorizado.")
    return f"l.{field}=?", [actor["id"]]


def public_lead(con, row: sqlite3.Row) -> dict:
    # Projeção explícita: não incluir contatos, observações, payloads ou segredos.
    result = dict(row)
    base_ok = lgpd.base_para_contato(con, row["id"])
    result["base_contato"] = "liberada" if base_ok else "pendente"
    result["contato_autorizado"] = bool(base_ok and row["etapa"] in estados.ETAPAS_DE_CONTATO)
    result["base_ficticia"] = bool(result["base_ficticia"])
    return result


LEAD_COLUMNS = """l.id,l.razao_social,l.nome_fantasia,l.cnpj,l.cidade,l.uf,l.segmento,
l.etapa,l.classificacao,l.nota_final,l.solucao_principal,l.sla_limite,l.retorno_em,
l.responsavel_id,l.executivo_id,l.base_ficticia"""


def create_app(
    db_copy: Path | None = None, *, allow_real_copy: bool = False, write_enabled: bool | None = None
) -> FastAPI:
    # Preparação e migração acontecem exclusivamente no comando de bootstrap.
    if db_copy is None:
        configured = os.environ.get("FULLGUETE_API_DB_COPY")
        if not configured:
            raise RuntimeError("Defina FULLGUETE_API_DB_COPY para uma cópia de homologação.")
        db_copy = Path(configured)
    path = Path(db_copy).resolve(strict=True)
    if not path.is_file():
        raise RuntimeError("O caminho precisa ser um arquivo SQLite.")
    operational_db = config.caminho_banco().resolve()
    if path == operational_db or (operational_db.is_file() and path.samefile(operational_db)):
        raise RuntimeError("A API exige uma cópia separada do banco operacional.")
    writable = os.environ.get("FULLGUETE_API_WRITE_MODE") == "homologacao" if write_enabled is None else write_enabled
    models = path.parent / "modelos"
    original_stat = path.stat()
    if writable:
        if allow_real_copy or config.modo() != "simulado" or models.is_symlink() or not models.is_dir():
            raise RuntimeError("Gravações exigem o ambiente fictício preparado para homologação.")
        if (configured_models := config.ler("FULLGUETE_MODELOS_DIR")) and models.resolve() == (
            config.RAIZ / configured_models
        ).resolve():
            raise RuntimeError("Use modelos separados da operação padrão.")
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as con:
            try:
                marker = con.execute("SELECT marcador FROM portal_homologacao").fetchall()
                con.execute("SELECT chave FROM portal_comandos LIMIT 0")
                mixed = con.execute(
                    """SELECT EXISTS(SELECT 1 FROM leads WHERE base_ficticia IS NOT 1)
                    OR EXISTS(SELECT 1 FROM leads_brutos WHERE base_ficticia IS NOT 1)
                    OR EXISTS(SELECT 1 FROM usuarios WHERE demonstracao IS NOT 1)"""
                ).fetchone()[0]
            except sqlite3.Error as exc:
                raise RuntimeError("Prepare uma base nova com portal_api.sandbox.") from exc
            if marker != [(MARKER,)] or mixed:
                raise RuntimeError("A base contém dados fora do ambiente fictício.")
    app = FastAPI(title="Fullguete API — homologação", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    lock = threading.Lock()
    sessions: dict[str, tuple[int, str, float]] = {}
    attempts: deque[float] = deque()
    last_search = float("-inf")

    @contextmanager
    def connection():
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA query_only=ON")
            con.execute("BEGIN")
            yield con

    def visible(actor: dict) -> tuple[str, list]:
        sql, args = scope(actor)
        # Opt-out nunca aparece em rotas comerciais, nem para gestor.
        sql += " AND l.opt_out=0"
        if not allow_real_copy:
            sql += " AND l.base_ficticia=1"
        return sql, args

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError):
        # Pydantic inclui o valor recebido em erros; credenciais nunca voltam ao cliente.
        return JSONResponse({"detail": "Dados da solicitação inválidos."}, status_code=422)

    def reject() -> HTTPException:
        return HTTPException(401, "Sessão inválida.", headers={"WWW-Authenticate": "Bearer"})

    def auth_key(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> str:
        if credentials is None or len(credentials.credentials) > 256:
            raise reject()
        return digest(credentials.credentials)

    def identity(con, key: str) -> dict:
        with lock:
            current = sessions.get(key)
            if current is None or current[2] <= time.monotonic():
                sessions.pop(key, None)
                raise reject()
        user_id, fingerprint, _ = current
        row = con.execute(
            "SELECT id,login,nome,papel,senha_hash,demonstracao FROM usuarios WHERE id=? AND ativo=1",
            (user_id,),
        ).fetchone()
        if (
            row is None
            or digest(row["senha_hash"]) != fingerprint
            or row["papel"] not in auth.PAPEIS
            or (allow_real_copy and row["demonstracao"])
        ):
            with lock:
                sessions.pop(key, None)
            raise reject()
        return {k: row[k] for k in ("id", "login", "nome", "papel")}

    @app.post("/v1/session")
    def login(body: Login):
        # Limitador global intencional para ambiente local, não adequado a produção.
        now = time.monotonic()
        with lock:
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if len(attempts) >= 20:
                raise HTTPException(429, "Muitas tentativas. Tente novamente em um minuto.")
            attempts.append(now)
        with connection() as con:
            row = con.execute(
                "SELECT id,login,nome,papel,senha_hash,demonstracao FROM usuarios WHERE login=? AND ativo=1",
                (body.login.strip().lower(),),
            ).fetchone()
            password_hash = row["senha_hash"] if row else DUMMY_HASH
            valid = auth.verificar(body.senha, password_hash)
            if not valid or row is None or row["papel"] not in auth.PAPEIS or (allow_real_copy and row["demonstracao"]):
                raise reject()
            token = secrets.token_urlsafe(32)
            with lock:
                expired = [k for k, v in sessions.items() if v[2] <= now]
                for key in expired:
                    del sessions[key]
                if len(sessions) >= MAX_SESSIONS:
                    raise HTTPException(503, "Limite de sessões atingido.")
                sessions[digest(token)] = (row["id"], digest(password_hash), now + SESSION_SECONDS)
            return {
                "access_token": token,
                "token_type": "bearer",
                "expires_in": SESSION_SECONDS,
                "usuario": {k: row[k] for k in ("id", "login", "nome", "papel")},
            }

    @app.delete("/v1/session", status_code=204)
    def logout(key: Annotated[str, Depends(auth_key)]):
        with lock:
            sessions.pop(key, None)

    @app.get("/v1/me")
    def me(key: Annotated[str, Depends(auth_key)]):
        with connection() as con:
            actor = identity(con, key)
            if writable:
                actor["gravacao"] = actor["papel"] in {"gestor", "bdr"}
            return actor

    @app.post("/v1/commands")
    def command(body: Command, key: Annotated[str, Depends(auth_key)], idempotency_key: Annotated[UUID, Header()]):
        if not writable:
            raise HTTPException(403, "Gravação desativada nesta instância.")
        current_stat = path.stat()
        if not os.path.samestat(original_stat, current_stat) or models.is_symlink():
            raise HTTPException(503, "A base de homologação mudou. Reinicie o servidor.")
        fingerprint = digest(json.dumps(body.model_dump(mode="json"), sort_keys=True, ensure_ascii=False))
        try:
            with (
                closing(sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=5)) as con,
                con,
            ):
                con.row_factory = sqlite3.Row
                con.execute("PRAGMA foreign_keys=ON")
                con.execute("BEGIN IMMEDIATE")
                actor = identity(con, key)
                if actor["papel"] not in {"gestor", "bdr"} or (body.acao in MANAGEMENT and actor["papel"] != "gestor"):
                    raise HTTPException(403, "Ação fora das permissões do perfil.")
                if not con.execute("SELECT 1 FROM usuarios WHERE id=? AND demonstracao=1", (actor["id"],)).fetchone():
                    raise HTTPException(403, "Gravações são exclusivas de perfis de demonstração.")
                command_key = str(idempotency_key)
                previous = con.execute(
                    "SELECT pedido,resposta FROM portal_comandos WHERE usuario_id=? AND chave=?",
                    (actor["id"], command_key),
                ).fetchone()
                if previous:
                    if previous["pedido"] != fingerprint:
                        raise HTTPException(409, "Identificador já usado para outro comando.")
                    if isinstance(body, LeadCommand):
                        find_targets(con, actor, body, check_version=False)
                    return json.loads(previous["resposta"])
                with reutilizar_transacao(con), config.usar_modelos_isolados(models):
                    result = apply(con, actor, body)
                if isinstance(body, LeadCommand):
                    con.executemany("UPDATE leads SET versao=versao+1 WHERE id=?", [(lead.id,) for lead in body.leads])
                con.execute(
                    "INSERT INTO portal_comandos VALUES (?,?,?,?)",
                    (actor["id"], command_key, fingerprint, json.dumps(result, ensure_ascii=False)),
                )
                return result
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except sqlite3.OperationalError as exc:
            if getattr(exc, "sqlite_errorcode", 0) & 255 in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                raise HTTPException(
                    503, "Banco ocupado. Repita o mesmo comando.", headers={"Retry-After": "2"}
                ) from exc
            raise

    @app.get("/v1/operation-options")
    def operation_options(key: Annotated[str, Depends(auth_key)]):
        with connection() as con:
            actor = identity(con, key)
            if not writable or actor["papel"] not in {"gestor", "bdr"}:
                raise HTTPException(403, "Gravação indisponível para o perfil.")
            return {
                "estado": gestao_leads.OPCOES,
                "motivos": estados.MOTIVOS,
                "resultados": comercial.RESULTADOS,
                "classificacoes": revisao.CLASSES_REVISAO,
                "solucoes": [{"id": item["id"], "nome": item["nome"]} for item in catalogo.solucoes()]
                if actor["papel"] == "gestor"
                else [],
                "bdrs": [
                    dict(row)
                    for row in con.execute(
                        "SELECT id,nome FROM usuarios WHERE ativo=1 AND papel='bdr' AND demonstracao=1 ORDER BY nome"
                    )
                ]
                if actor["papel"] == "gestor"
                else [],
                "triagem": sorted(triagem.ENCAMINHAVEIS),
                "processaveis": sorted(orquestrador.TRATAVEIS),
            }

    @app.get("/v1/search-history")
    def search_history(
        key: Annotated[str, Depends(auth_key)],
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    ):
        with connection() as con:
            actor = identity(con, key)
            if not writable or actor["papel"] != "gestor":
                raise HTTPException(403, "Histórico de importação restrito ao gestor.")
            return {
                "items": [
                    dict(row)
                    for row in con.execute(
                        "SELECT id,tag,criada_em FROM buscas_prospeccao ORDER BY id DESC LIMIT ? OFFSET ?",
                        (limit, offset),
                    )
                ]
            }

    @app.get("/v1/search-history/{campaign_id}")
    def search_detail(campaign_id: int, key: Annotated[str, Depends(auth_key)]):
        with connection() as con:
            actor = identity(con, key)
            if not writable or actor["papel"] != "gestor":
                raise HTTPException(403, "Histórico de importação restrito ao gestor.")
            with reutilizar_transacao(con):
                campaign = prospeccao.carregar(campaign_id)
            if campaign is None:
                raise HTTPException(404, "Busca não encontrada.")
            return campaign_data(campaign)

    @app.post("/v1/company-search")
    def company_search(body: CompanySearch, key: Annotated[str, Depends(auth_key)]):
        nonlocal last_search
        with connection() as con:
            actor = identity(con, key)
        if actor["papel"] != "gestor":
            raise HTTPException(403, "Busca externa restrita ao gestor.")
        if writable:
            raise HTTPException(403, "Use a busca simulada do ambiente de gravação.")
        provider_key = os.environ.get("FULLGUETE_API_CNPJA_KEY", "").strip()
        if not provider_key:
            raise HTTPException(503, "Busca externa desativada nesta homologação.")
        params = cnpja.filtros("Todos", body.uf, body.municipio_ibge, body.ano, body.mes, body.cnae, limite=10)
        with lock:
            now = time.monotonic()
            if now - last_search < 15:
                raise HTTPException(429, "Aguarde 15 segundos entre pesquisas.")
            last_search = now
        try:
            result = cnpja.pesquisar(provider_key, params)
        except (cnpja.ErroCnpja, ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(502, "A consulta ao provedor não pôde ser concluída.") from exc
        columns = ("cnpj", "razao_social", "cidade", "uf", "cnae", "data_abertura")
        return {"items": [{field: company[field] for field in columns} for company in result.empresas[:10]]}

    @app.get("/v1/leads")
    def leads(
        key: Annotated[str, Depends(auth_key)],
        view: Literal["all", "queue", "triage", "review", "captured"] = "all",
        campaign_id: Annotated[int | None, Query(gt=0)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    ):
        with connection() as con:
            actor = identity(con, key)
            where, params = visible(actor)
            if view == "queue":
                if actor["papel"] == "executivo":
                    raise HTTPException(403, "Fila restrita à equipe BDR e à gestão.")
                stages = comercial.ETAPAS_ATIVAS_BDR
            elif view == "triage":
                if actor["papel"] != "gestor":
                    raise HTTPException(403, "Triagem restrita ao gestor.")
                stages = (estados.TRATADO, estados.REVISAO, estados.NUTRICAO)
            elif view == "captured":
                stages = (estados.CAPTURADO,)
            elif view == "review":
                stages = (estados.REVISAO,)
            else:
                stages = ()
            if stages:
                where += " AND l.etapa IN (" + ",".join("?" for _ in stages) + ")"
                params.extend(stages)
            if campaign_id is not None:
                where += " AND EXISTS(SELECT 1 FROM buscas_leads bl WHERE bl.lead_id=l.id AND bl.busca_id=?)"
                params.append(campaign_id)
            order = "l.nota_final DESC NULLS LAST,l.id"
            if view == "queue":
                order = "l.sla_limite IS NULL,l.sla_limite," + order
            columns = LEAD_COLUMNS + (",l.versao" if writable else "")
            count = con.execute("SELECT COUNT(*) FROM leads l WHERE " + where, params).fetchone()[0]
            rows = con.execute(
                "SELECT " + columns + " FROM leads l WHERE " + where + " ORDER BY " + order + " LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            result = {"items": [public_lead(con, r) for r in rows], "total": count, "limit": limit, "offset": offset}
            if writable:
                result["indicadores"] = dict(
                    con.execute(
                        """SELECT COUNT(CASE WHEN l.etapa=? THEN 1 END) AS revisao,
                    COUNT(CASE WHEN l.etapa IN (?,?,?,?) THEN 1 END) AS fila,
                    COUNT(CASE WHEN l.etapa IN (?,?,?,?) AND l.sla_limite<? THEN 1 END) AS sla_vencido
                    FROM leads l WHERE """
                        + where,
                        [
                            estados.REVISAO,
                            *comercial.ETAPAS_ATIVAS_BDR,
                            *comercial.ETAPAS_ATIVAS_BDR,
                            tempo.iso(),
                            *params,
                        ],
                    ).fetchone()
                )
            return result

    @app.get("/v1/leads/{lead_id}")
    def lead_detail(lead_id: int, key: Annotated[str, Depends(auth_key)]):
        with connection() as con:
            actor = identity(con, key)
            where, params = visible(actor)
            columns = LEAD_COLUMNS + (",l.versao" if writable else "")
            row = con.execute(
                "SELECT " + columns + " FROM leads l WHERE " + where + " AND l.id=?", [*params, lead_id]
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Lead não encontrado.")
            result = public_lead(con, row)
            result["campanhas"] = [
                dict(r)
                for r in con.execute(
                    "SELECT b.id,b.tag FROM buscas_leads bl JOIN buscas_prospeccao b ON b.id=bl.busca_id "
                    "WHERE bl.lead_id=? ORDER BY b.id DESC",
                    (lead_id,),
                )
            ]
            if actor["papel"] in {"bdr", "gestor"}:
                bant = con.execute(
                    "SELECT orcamento,autoridade,necessidade,prazo FROM bant WHERE lead_id=?",
                    (lead_id,),
                ).fetchone()
                confirmations = {
                    item["campo"]: bool(item["confirmado"])
                    for item in con.execute("SELECT campo,confirmado FROM bant_validacoes WHERE lead_id=?", (lead_id,))
                }
                result["bant"] = {
                    field: {
                        "preenchido": bool(bant and (bant[field] or "").strip()),
                        "confirmado": bool(bant and (bant[field] or "").strip() and confirmations.get(field)),
                    }
                    for field in comercial.BANT_CAMPOS
                }
                result["cadencia"] = []
                if result["contato_autorizado"]:
                    result["cadencia"] = [
                        dict(item)
                        for item in con.execute(
                            (
                                ("SELECT id," if writable else "SELECT ")
                                + "dia,canal,previsto_para,feito_em FROM cadencia_passos "
                            )
                            + "WHERE lead_id=? ORDER BY dia,id",
                            (lead_id,),
                        )
                    ]
            if writable and actor["papel"] in {"gestor", "bdr"}:
                scheduled = con.execute(
                    """SELECT inicio_em FROM agenda_compromissos
                    WHERE lead_id=? AND tipo='Retorno' AND status='Pendente'
                    ORDER BY inicio_em,id LIMIT 1""",
                    (lead_id,),
                ).fetchone()
                if scheduled is not None:
                    result["retorno_em"] = scheduled["inicio_em"]
                result["atividades"] = [
                    dict(r)
                    for r in con.execute(
                        "SELECT tipo,resultado,registrada_em FROM atividades WHERE lead_id=? ORDER BY id DESC LIMIT 10",
                        (lead_id,),
                    )
                ]
            # Não retornar roteiro de contato, dados pessoais, texto livre ou dados brutos da IA.
            return result

    @app.get("/v1/campaigns")
    def campaigns(
        key: Annotated[str, Depends(auth_key)],
        limit: Annotated[int, Query(ge=1, le=100)] = 30,
        offset: Annotated[int, Query(ge=0, le=100000)] = 0,
    ):
        with connection() as con:
            actor = identity(con, key)
            where, params = visible(actor)
            # Apenas campanhas com leads visíveis; totais nunca incluem carteiras alheias.
            rows = con.execute(
                """SELECT b.id,b.tag,b.segmento,b.cidade,b.uf,b.ano,b.mes,
                COUNT(DISTINCT l.id) AS importados_visiveis
                FROM buscas_prospeccao b JOIN buscas_leads bl ON bl.busca_id=b.id
                JOIN leads l ON l.id=bl.lead_id WHERE """
                + where
                + " GROUP BY b.id ORDER BY b.id DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
            return {"items": [dict(r) for r in rows], "limit": limit, "offset": offset}

    return app
