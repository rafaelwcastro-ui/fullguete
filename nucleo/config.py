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


def logins_demo() -> bool:
    """Botões de login dos perfis fictícios. 'auto': só aparecem quando não há usuários nos Secrets."""
    valor = ler("FULLGUETE_LOGINS_DEMO", "auto").lower()
    if valor in ("sim", "1", "true"):
        return simulado()
    if valor in ("nao", "não", "0", "false"):
        return False
    return simulado() and not usuarios_secrets()


def cenario_demo_automatico() -> bool:
    """No modo simulado, monta um mês fictício de operação na primeira abertura (desligue com 'nao')."""
    return ler("FULLGUETE_CENARIO_DEMO", "sim").lower() not in ("nao", "não", "0", "false")


def chave_gemini() -> str:
    return ler("GEMINI_API_KEY")


def modelo_gemini() -> str:
    return ler("GEMINI_MODEL", MODELO_GEMINI_PADRAO)


def token_cnpjws() -> str:
    return ler("CNPJ_WS_TOKEN")


def token_localizacnpj() -> str:
    """Chave da busca avançada. Nunca exposta em código ou commit."""
    return ler("LOCALIZA_CNPJ_TOKEN")


def caminho_banco() -> Path:
    caminho = Path(ler("FULLGUETE_DB_PATH", "data/fullguete_v2.db"))
    return caminho if caminho.is_absolute() else RAIZ / caminho


def pasta_modelos() -> Path:
    caminho = Path(ler("FULLGUETE_MODELOS_DIR", "modelos"))
    caminho = caminho if caminho.is_absolute() else RAIZ / caminho
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def sufixo_banco() -> str:
    """Identificador curto do banco em uso, para arquivos de modelo de bancos diferentes não colidirem."""
    import hashlib

    return hashlib.sha1(str(caminho_banco().resolve()).encode()).hexdigest()[:6]


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
