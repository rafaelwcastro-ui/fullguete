"""Primeiro incremento: API autenticada de leitura para homologação local."""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import threading
import time
from collections import deque
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from nucleo import auth, comercial, estados, lgpd

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


def create_app(db_copy: Path | None = None, *, allow_real_copy: bool = False) -> FastAPI:
    # Esta fábrica exige uma cópia explicitamente indicada. Não chama conectar(),
    # migrar(), semente ou qualquer serviço que possa modificar o SQLite.
    if db_copy is None:
        configured = os.environ.get("FULLGUETE_API_DB_COPY")
        if not configured:
            raise RuntimeError("Defina FULLGUETE_API_DB_COPY para uma cópia de homologação.")
        db_copy = Path(configured)
    path = Path(db_copy).resolve(strict=True)
    if not path.is_file():
        raise RuntimeError("O caminho precisa ser um arquivo SQLite.")
    app = FastAPI(title="Fullguete API — homologação", version="0.1.0",
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    lock = threading.Lock()
    sessions: dict[str, tuple[int, str, float]] = {}
    attempts: deque[float] = deque()

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
        if (row is None or digest(row["senha_hash"]) != fingerprint
                or row["papel"] not in auth.PAPEIS
                or (allow_real_copy and row["demonstracao"])):
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
            if (not valid or row is None or row["papel"] not in auth.PAPEIS
                    or (allow_real_copy and row["demonstracao"])):
                raise reject()
            token = secrets.token_urlsafe(32)
            with lock:
                expired = [k for k, v in sessions.items() if v[2] <= now]
                for key in expired:
                    del sessions[key]
                if len(sessions) >= MAX_SESSIONS:
                    raise HTTPException(503, "Limite de sessões atingido.")
                sessions[digest(token)] = (row["id"], digest(password_hash), now + SESSION_SECONDS)
            return {"access_token": token, "token_type": "bearer", "expires_in": SESSION_SECONDS,
                    "usuario": {k: row[k] for k in ("id", "login", "nome", "papel")}}

    @app.delete("/v1/session", status_code=204)
    def logout(key: Annotated[str, Depends(auth_key)]):
        with lock:
            sessions.pop(key, None)

    @app.get("/v1/me")
    def me(key: Annotated[str, Depends(auth_key)]):
        with connection() as con:
            return identity(con, key)

    @app.get("/v1/leads")
    def leads(key: Annotated[str, Depends(auth_key)],
              view: Literal["all", "queue", "triage", "review"] = "all",
              campaign_id: Annotated[int | None, Query(gt=0)] = None,
              limit: Annotated[int, Query(ge=1, le=100)] = 30,
              offset: Annotated[int, Query(ge=0, le=100000)] = 0):
        with connection() as con:
            actor = identity(con, key)
            where, params = visible(actor)
            if view == "queue":
                stages = comercial.ETAPAS_ATIVAS_BDR
            elif view == "triage":
                if actor["papel"] != "gestor":
                    raise HTTPException(403, "Triagem restrita ao gestor.")
                stages = (estados.TRATADO, estados.REVISAO, estados.NUTRICAO)
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
            count = con.execute("SELECT COUNT(*) FROM leads l WHERE " + where, params).fetchone()[0]
            rows = con.execute(
                "SELECT " + LEAD_COLUMNS + " FROM leads l WHERE " + where
                + " ORDER BY l.nota_final DESC NULLS LAST,l.id LIMIT ? OFFSET ?", [*params, limit, offset]
            ).fetchall()
            return {"items": [public_lead(con, r) for r in rows], "total": count,
                    "limit": limit, "offset": offset}

    @app.get("/v1/leads/{lead_id}")
    def lead_detail(lead_id: int, key: Annotated[str, Depends(auth_key)]):
        with connection() as con:
            actor = identity(con, key)
            where, params = visible(actor)
            row = con.execute("SELECT " + LEAD_COLUMNS + " FROM leads l WHERE " + where + " AND l.id=?",
                              [*params, lead_id]).fetchone()
            if row is None:
                raise HTTPException(404, "Lead não encontrado.")
            result = public_lead(con, row)
            result["campanhas"] = [dict(r) for r in con.execute(
                "SELECT b.id,b.tag FROM buscas_leads bl JOIN buscas_prospeccao b ON b.id=bl.busca_id "
                "WHERE bl.lead_id=? ORDER BY b.id DESC", (lead_id,))]
            # Não retornar roteiro de contato, dados pessoais, texto livre ou dados brutos da IA.
            return result

    @app.get("/v1/campaigns")
    def campaigns(key: Annotated[str, Depends(auth_key)],
                  limit: Annotated[int, Query(ge=1, le=100)] = 30,
                  offset: Annotated[int, Query(ge=0, le=100000)] = 0):
        with connection() as con:
            actor = identity(con, key)
            where, params = visible(actor)
            # Apenas campanhas com leads visíveis; totais nunca incluem carteiras alheias.
            rows = con.execute(
                """SELECT b.id,b.tag,b.segmento,b.cidade,b.uf,b.ano,b.mes,
                COUNT(DISTINCT l.id) AS importados_visiveis
                FROM buscas_prospeccao b JOIN buscas_leads bl ON bl.busca_id=b.id
                JOIN leads l ON l.id=bl.lead_id WHERE """ + where
                + " GROUP BY b.id ORDER BY b.id DESC LIMIT ? OFFSET ?", [*params, limit, offset]
            ).fetchall()
            return {"items": [dict(r) for r in rows], "limit": limit, "offset": offset}

    return app
