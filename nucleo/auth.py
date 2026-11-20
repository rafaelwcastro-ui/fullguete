"""Login com usuário e senha guardada só como hash PBKDF2.

No modo simulado existem logins de demonstração (gestor, BDRs e executivo).
No modo real só entram usuários cadastrados nos Secrets:

    [usuarios.maria]
    nome = "Maria"
    papel = "gestor"            # bdr, gestor ou executivo
    senha_hash = "pbkdf2_sha256$600000$<salt>$<hash>"

Para gerar um hash:  python -m nucleo.auth
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

ALGORITMO = "pbkdf2_sha256"
ITERACOES = 600_000
MAX_TENTATIVAS = 5
BLOQUEIO_SEGUNDOS = 60

PAPEIS = {"bdr": "BDR", "gestor": "Gestor", "executivo": "Executivo de contas"}


def gerar_hash(senha: str, iteracoes: int = ITERACOES) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, iteracoes)
    return f"{ALGORITMO}${iteracoes}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verificar(senha: str, senha_hash: str) -> bool:
    try:
        algoritmo, iteracoes, salt, esperado = senha_hash.split("$")
        if algoritmo != ALGORITMO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), base64.b64decode(salt), int(iteracoes))
        return hmac.compare_digest(dk, base64.b64decode(esperado))
    except (ValueError, TypeError):
        return False


_HASH_FALSO = gerar_hash(secrets.token_urlsafe(16), 1_000)


def autenticar(usuarios: dict[str, dict], login: str, senha: str) -> dict | None:
    dados = usuarios.get(login.strip().lower())
    if not dados:
        verificar(senha, _HASH_FALSO)  # tempo parecido para não revelar se o usuário existe
        return None
    return dados if verificar(senha, dados["senha_hash"]) else None


def _entrar(usuario: dict) -> None:
    import streamlit as st

    st.session_state["usuario"] = {k: usuario[k] for k in ("id", "login", "nome", "papel")}
    st.session_state.pop("login_tentativas", None)


def exigir_login(usuarios: dict[str, dict], demonstracao: list[dict], logo: str | None = None) -> dict:
    """Mostra a tela de login e para a página até alguém entrar. Retorna o usuário da sessão."""
    import streamlit as st

    from . import ui

    if st.session_state.get("usuario"):
        return st.session_state["usuario"]

    _, centro, _ = st.columns([1, 1.3, 1])
    with centro:
        st.write("")
        if logo:
            st.image(logo, width="stretch")
        ui.rotulo("Acesso")
        st.markdown("### Entrar no Fullguete")

        restante = int(st.session_state.get("login_bloqueado_ate", 0) - time.time())
        if restante > 0:
            st.error(f"Muitas tentativas erradas. Tente de novo em {restante} segundos.")
            st.stop()

        if demonstracao:
            st.caption("Modo simulado: escolha um perfil de demonstração.")
            for usuario in demonstracao:
                rotulo = f"{PAPEIS[usuario['papel']]}: {usuario['nome']}"
                if st.button(rotulo, key=f"demo_{usuario['login']}", width="stretch"):
                    _entrar(usuario)
                    st.rerun()
            st.caption("Ou entre com usuário e senha.")

        if not usuarios:
            st.error("Nenhum usuário configurado. Adicione a seção [usuarios] nos Secrets do app.")
            st.stop()

        with st.form("login"):
            login = st.text_input("Usuário", autocomplete="username")
            senha = st.text_input("Senha", type="password", autocomplete="current-password")
            entrar = st.form_submit_button("Entrar", type="primary", width="stretch")
        if entrar:
            usuario = autenticar(usuarios, login, senha)
            if usuario:
                _entrar(usuario)
                st.rerun()
            tentativas = st.session_state.get("login_tentativas", 0) + 1
            st.session_state["login_tentativas"] = tentativas
            if tentativas >= MAX_TENTATIVAS:
                st.session_state["login_tentativas"] = 0
                st.session_state["login_bloqueado_ate"] = time.time() + BLOQUEIO_SEGUNDOS
            st.error("Usuário ou senha incorretos.")
    ui.rodape()
    st.stop()


def sair() -> None:
    import streamlit as st

    st.session_state.clear()


if __name__ == "__main__":
    import getpass

    senha = getpass.getpass("Senha para gerar o hash: ")
    print(gerar_hash(senha))
