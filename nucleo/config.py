"""Leitura das variáveis de ambiente.

Ordem de busca: variável de ambiente, arquivo .env (local) e Secrets do Streamlit (nuvem).
Nenhuma chave fica no código. Sem chave, o sistema roda em modo local e simulado.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env", override=False)

MODELO_GEMINI_PADRAO = "gemini-3.1-flash-lite"


def ler(nome: str, padrao: str = "") -> str:
    valor = os.environ.get(nome, "")
    if not valor:
        try:
            import streamlit as st

            valor = str(st.secrets.get(nome, "") or "")
        except Exception:  # sem secrets.toml ou fora do Streamlit
            valor = ""
    return valor.strip() or padrao


def modo() -> str:
    """'simulado' (padrão) ou 'real'."""
    return "real" if ler("FULLGUETE_MODO", "simulado").lower() == "real" else "simulado"


def simulado() -> bool:
    return modo() == "simulado"


def chave_gemini() -> str:
    return ler("GEMINI_API_KEY")


def modelo_gemini() -> str:
    return ler("GEMINI_MODEL", MODELO_GEMINI_PADRAO)


def token_cnpjws() -> str:
    return ler("CNPJ_WS_TOKEN")


def caminho_banco() -> Path:
    caminho = Path(ler("FULLGUETE_DB_PATH", "data/fullguete_v2.db"))
    return caminho if caminho.is_absolute() else RAIZ / caminho


def usuarios_secrets() -> dict[str, dict]:
    """Usuários definidos em [usuarios.<login>] nos Secrets (modo real)."""
    try:
        import streamlit as st

        bruto = st.secrets.get("usuarios", {})
    except Exception:
        return {}
    saida = {}
    for login, dados in bruto.items():
        try:
            dados = dict(dados)
        except (TypeError, ValueError):
            continue
        if dados.get("senha_hash"):
            saida[str(login).lower()] = dados
    return saida
