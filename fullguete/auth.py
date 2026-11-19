"""Login com usuário e senha.

As senhas nunca ficam em texto puro: os Secrets guardam só o hash PBKDF2-SHA256.

    [usuarios.admin]
    nome = "Administrador"
    senha_hash = "pbkdf2_sha256$600000$<salt>$<hash>"

Para criar ou trocar um usuário:  python -m fullguete.auth <usuario> ["Nome de exibição"]
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


def gerar_hash(senha: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, ITERACOES)
    return f"{ALGORITMO}${ITERACOES}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verificar(senha: str, senha_hash: str) -> bool:
    try:
        algoritmo, iteracoes, salt, esperado = senha_hash.split("$")
        if algoritmo != ALGORITMO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), base64.b64decode(salt), int(iteracoes))
        return hmac.compare_digest(dk, base64.b64decode(esperado))
    except (ValueError, TypeError):
        return False


def exigir_login(usuarios: dict, logo: str | None = None) -> dict:
    """Mostra a tela de login e interrompe o app até o usuário entrar. Retorna o usuário logado."""
    import streamlit as st

    if st.session_state.get("usuario"):
        return st.session_state["usuario"]

    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        st.write("")
        if logo:
            st.image(logo, width="stretch")
        st.markdown("### Acesso ao portal")
        if not usuarios:
            st.error("Nenhum usuário configurado. Adicione a seção `[usuarios]` nos Secrets do app.")
            st.stop()

        bloqueado_ate = st.session_state.get("login_bloqueado_ate", 0)
        restante = int(bloqueado_ate - time.time())
        if restante > 0:
            st.error(f"Muitas tentativas erradas. Tente novamente em {restante} segundos.")
            st.stop()

        with st.form("login"):
            login = st.text_input("Usuário", autocomplete="username")
            senha = st.text_input("Senha", type="password", autocomplete="current-password")
            entrar = st.form_submit_button("Entrar", type="primary", width="stretch")

        if entrar:
            dados = usuarios.get(login.strip().lower())
            # Sem usuário, verifica um hash falso para o tempo de resposta não revelar se ele existe.
            ok = verificar(senha, dados["senha_hash"]) if dados else (verificar(senha, _HASH_FALSO) and False)
            if ok:
                st.session_state.pop("login_tentativas", None)
                st.session_state["usuario"] = {"login": login.strip().lower(), "nome": dados.get("nome") or login}
                st.rerun()
            tentativas = st.session_state.get("login_tentativas", 0) + 1
            st.session_state["login_tentativas"] = tentativas
            if tentativas >= MAX_TENTATIVAS:
                st.session_state["login_tentativas"] = 0
                st.session_state["login_bloqueado_ate"] = time.time() + BLOQUEIO_SEGUNDOS
            st.error("Usuário ou senha incorretos.")
    st.stop()


def sair() -> None:
    import streamlit as st

    st.session_state.pop("usuario", None)


_HASH_FALSO = gerar_hash(secrets.token_urlsafe(16))


if __name__ == "__main__":
    # Gera (ou troca) um usuário em .streamlit/secrets.toml com uma senha aleatória.
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        sys.exit('Uso: python -m fullguete.auth <usuario> ["Nome de exibição"]')
    usuario = sys.argv[1].strip().lower()
    nome = sys.argv[2] if len(sys.argv) > 2 else usuario.capitalize()
    senha = secrets.token_urlsafe(12)

    pasta = Path(__file__).resolve().parent.parent / ".streamlit"
    arq = pasta / "secrets.toml"
    texto = arq.read_text() if arq.exists() else ""
    secao = f"[usuarios.{usuario}]"
    if secao in texto:  # remove a versão anterior do usuário
        inicio = texto.index(secao)
        fim = texto.find("\n[", inicio + 1)
        texto = texto[:inicio] + (texto[fim + 1 :] if fim != -1 else "")
    texto = texto.rstrip() + f'\n\n{secao}\nnome = "{nome}"\nsenha_hash = "{gerar_hash(senha)}"\n'
    arq.write_text(texto.lstrip())

    credenciais = pasta / "credenciais_locais.txt"
    with credenciais.open("a") as f:
        f.write(f"usuario: {usuario}\nsenha: {senha}\n\n")
    print(f"Usuário '{usuario}' gravado em {arq}.")
    print(f"Senha gerada salva em {credenciais} (fora do git). Apague o arquivo depois de anotar a senha.")
