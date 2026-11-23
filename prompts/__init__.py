"""Prompts versionados. Cada resultado da IA guarda a versão usada.

Para criar uma versão nova, copie a pasta v1 para v2, ajuste e troque VERSAO_ATIVA.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PASTA = Path(__file__).resolve().parent
VERSAO_ATIVA = "v2"
TEMPERATURA = 0.2


@lru_cache(maxsize=8)
def sistema(versao: str = VERSAO_ATIVA) -> str:
    return (PASTA / versao / "sistema.md").read_text(encoding="utf-8")


@lru_cache(maxsize=8)
def exemplos(versao: str = VERSAO_ATIVA) -> dict:
    return json.loads((PASTA / versao / "exemplos.json").read_text(encoding="utf-8"))


def montar_usuario(icp: dict, leads: list[dict], versao: str = VERSAO_ATIVA) -> str:
    """Mensagem do usuário: exemplo fixo (few shot), ICP e o lote de empresas."""
    ex = exemplos(versao)
    icp_txt = {
        "descricao": icp.get("descricao", ""),
        "setores_alvo": icp.get("setores", []),
        "portes_alvo": icp.get("portes", []),
        "palavras_chave": icp.get("palavras_chave", []),
    }
    return (
        "<exemplo>\n"
        f"Entrada: {json.dumps(ex['entrada'], ensure_ascii=False)}\n"
        f"Saída esperada: {json.dumps(ex['saida'], ensure_ascii=False)}\n"
        "</exemplo>\n\n"
        f"<perfil_cliente_ideal>\n{json.dumps(icp_txt, ensure_ascii=False, indent=1)}\n</perfil_cliente_ideal>\n\n"
        f"<empresas>\n{json.dumps(leads, ensure_ascii=False, indent=1)}\n</empresas>"
    )
