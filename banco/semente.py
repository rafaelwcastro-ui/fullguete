"""Carga inicial: configurações, ICP, usuários e histórico fictício de treino.

É idempotente: pode rodar a cada início do app sem duplicar nada.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from dados import base_ficticia
from nucleo import auth

from . import repositorio
from .conexao import agora, conectar

# Hash mais leve só para os logins de demonstração, que já são públicos no modo simulado.
ITERACOES_DEMO = 120_000


def _garantir_usuario(con, login: str, nome: str, papel: str, senha_hash: str, meta: int, demo: bool) -> bool:
    existe = con.execute("SELECT id FROM usuarios WHERE login=?", (login,)).fetchone()
    if existe:
        con.execute(
            "UPDATE usuarios SET nome=?, papel=?, senha_hash=?, ativo=1 WHERE id=?",
            (nome, papel, senha_hash, existe["id"]),
        )
        return False
    con.execute(
        "INSERT INTO usuarios (login, nome, papel, senha_hash, meta_contatos_dia, demonstracao, criado_em) "
        "VALUES (?,?,?,?,?,?,?)",
        (login, nome, papel, senha_hash, meta, int(demo), agora()),
    )
    return True


def garantir_base(simulado: bool, usuarios_secrets: dict[str, dict] | None = None, logins_demo: bool = True) -> dict:
    """logins_demo=False mantém os perfis fictícios (a fila precisa de BDRs), mas sem senha utilizável."""
    resumo = {"usuarios_novos": 0, "historico_novo": 0}
    with conectar() as con:
        for chave, valor in repositorio.CONFIG_PADRAO.items():
            if not con.execute("SELECT 1 FROM configuracoes WHERE chave=?", (chave,)).fetchone():
                repositorio.salvar_config(chave, valor, "sistema", "valor inicial", con=con)

        if not con.execute("SELECT 1 FROM icp_versoes").fetchone():
            repositorio.salvar_icp(base_ficticia.ICP_PADRAO, "sistema", con=con)

        if simulado:
            for u in base_ficticia.USUARIOS_DEMO:
                linha = con.execute("SELECT senha_hash FROM usuarios WHERE login=?", (u["login"],)).fetchone()
                if not logins_demo:
                    # Portal público: ninguém entra pelos perfis fictícios. A senha vira um valor aleatório.
                    trancada = auth.gerar_hash(secrets.token_urlsafe(24), ITERACOES_DEMO)
                    resumo["usuarios_novos"] += _garantir_usuario(
                        con, u["login"], u["nome"], u["papel"], trancada, u["meta_contatos_dia"], True
                    )
                    continue
                if linha and auth.verificar(base_ficticia.SENHA_DEMO, linha["senha_hash"]):
                    con.execute("UPDATE usuarios SET ativo=1 WHERE login=?", (u["login"],))
                    continue
                senha_hash = auth.gerar_hash(base_ficticia.SENHA_DEMO, ITERACOES_DEMO)
                resumo["usuarios_novos"] += _garantir_usuario(
                    con, u["login"], u["nome"], u["papel"], senha_hash, u["meta_contatos_dia"], True
                )
        else:
            # No modo real os logins de demonstração ficam desativados.
            con.execute("UPDATE usuarios SET ativo=0 WHERE demonstracao=1")

        for login, dados in (usuarios_secrets or {}).items():
            papel = dados.get("papel", "gestor")
            if papel not in auth.PAPEIS:
                papel = "gestor"
            resumo["usuarios_novos"] += _garantir_usuario(
                con, login, dados.get("nome") or login, papel, dados["senha_hash"], 20, False
            )

        if not con.execute("SELECT 1 FROM rotulos_treino WHERE fonte='base_ficticia'").fetchone():
            hoje = datetime.now(UTC)
            linhas = [
                (
                    None,
                    "base_ficticia",
                    (hoje - timedelta(days=h["dias_atras"])).isoformat(timespec="seconds"),
                    repositorio._json(h["features"]),
                    h["resultado"],
                    h["motivo"],
                    h["solucao_id"],
                    h["valor_mensal"],
                )
                for h in base_ficticia.gerar_historico()
            ]
            con.executemany(
                "INSERT INTO rotulos_treino (lead_id, fonte, registrado_em, features, resultado, motivo, solucao_id, "
                "valor_mensal) VALUES (?,?,?,?,?,?,?,?)",
                linhas,
            )
            resumo["historico_novo"] = len(linhas)
            repositorio.auditar(
                con, "sistema", "historico_ficticio_carregado", "rotulos_treino", None, {"linhas": len(linhas)}
            )
    return resumo


def usuarios_demonstracao() -> list[dict]:
    ordem = {u["login"]: i for i, u in enumerate(base_ficticia.USUARIOS_DEMO)}
    demo = [u for u in repositorio.usuarios() if u["demonstracao"]]
    return sorted(demo, key=lambda u: ordem.get(u["login"], 99))
