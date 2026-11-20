"""Integração real com o CNPJ.ws (a única API externa de dados do projeto).

Evolução do captura.py da v1: agora com cache por CNPJ, controle do limite da API pública
(3 consultas por minuto) e bloqueio dos CNPJs da base fictícia.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from datetime import timedelta

import requests

from banco.conexao import conectar
from nucleo import tempo

from . import cnpj as cnpj_util

PUBLICA = "https://publica.cnpj.ws"
COMERCIAL = "https://comercial.cnpj.ws"
LIMITE_PUBLICA_POR_MINUTO = 3
MAX_LISTA_PUBLICA = 3
MAX_LISTA_COMERCIAL = 25
VALIDADE_CACHE = timedelta(days=30)

UF_IBGE = dict(zip(
    ["RO", "AC", "AM", "RR", "PA", "AP", "TO", "MA", "PI", "CE", "RN", "PB", "PE", "AL", "SE", "BA", "MG", "ES", "RJ", "SP", "PR", "SC", "RS", "MS", "MT", "GO", "DF"],
    (11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53),
    strict=True,
))  # fmt: skip

_chamadas_publicas: deque[float] = deque()
_trava = threading.Lock()


class ErroCaptura(RuntimeError):
    """Falha que pode ser mostrada na tela."""


def _liberar_publica() -> None:
    with _trava:
        agora = time.monotonic()
        while _chamadas_publicas and agora - _chamadas_publicas[0] > 60:
            _chamadas_publicas.popleft()
        if len(_chamadas_publicas) >= LIMITE_PUBLICA_POR_MINUTO:
            espera = int(60 - (agora - _chamadas_publicas[0])) + 1
            raise ErroCaptura(f"A API pública do CNPJ.ws aceita 3 consultas por minuto. Aguarde {espera} segundos.")
        _chamadas_publicas.append(agora)


def _get(url: str, token: str = "", params: dict | None = None) -> dict | None:
    cabecalhos = {"x_api_token": token} if token else {}
    try:
        resposta = requests.get(url, params=params, headers=cabecalhos, timeout=(4, 12), allow_redirects=False)
    except requests.RequestException as erro:
        raise ErroCaptura("Não foi possível conectar ao CNPJ.ws.") from erro
    if resposta.status_code == 404:
        return None
    if resposta.status_code in (401, 403):
        raise ErroCaptura("O CNPJ.ws recusou o acesso. Confira o token e o plano.")
    if resposta.status_code == 429:
        raise ErroCaptura("O CNPJ.ws atingiu o limite de consultas. Aguarde um minuto.")
    if resposta.status_code != 200:
        raise ErroCaptura(f"O CNPJ.ws devolveu um erro ({resposta.status_code}).")
    try:
        dados = resposta.json()
    except ValueError as erro:
        raise ErroCaptura("O CNPJ.ws devolveu dados fora do formato esperado.") from erro
    if not isinstance(dados, dict):
        raise ErroCaptura("O CNPJ.ws devolveu dados fora do formato esperado.")
    return dados


def para_registro(dados: dict, cnpj: str) -> dict:
    """Converte a resposta do CNPJ.ws para os campos padrão do Fullguete."""
    unidade = dados.get("estabelecimento") or {}
    atividade = unidade.get("atividade_principal") or {}
    porte = dados.get("porte") or {}
    simples = dados.get("simples") or {}
    telefone = ""
    for sufixo in ("1", "2"):
        if numero := unidade.get(f"telefone{sufixo}"):
            telefone = f"{unidade.get(f'ddd{sufixo}') or ''}{numero}"
            break
    porte_desc = str(porte.get("descricao") or "")
    if simples.get("mei") == "Sim":
        porte_padrao = "MEI"
    else:
        porte_padrao = {"01": "ME", "03": "EPP"}.get(str(porte.get("id") or "").zfill(2), "")
        if not porte_padrao and "demais" in porte_desc.lower():
            porte_padrao = "Média"
    return {
        "razao_social": dados.get("razao_social") or "",
        "nome_fantasia": unidade.get("nome_fantasia") or "",
        "cnpj": cnpj,
        "cnae": str(atividade.get("subclasse") or atividade.get("id") or ""),
        "setor": str(atividade.get("descricao") or ""),
        "porte": porte_padrao,
        "cidade": (unidade.get("cidade") or {}).get("nome") or "",
        "uf": (unidade.get("estado") or {}).get("sigla") or "",
        "situacao_cadastral": unidade.get("situacao_cadastral") or "",
        "email": unidade.get("email") or "",
        "telefone": telefone,
        "dados_cnpjws": {
            "fonte": "CNPJ.ws",
            "situacao_cadastral": unidade.get("situacao_cadastral"),
            "data_inicio_atividade": unidade.get("data_inicio_atividade"),
            "atividade_principal": atividade.get("descricao"),
            "porte": porte_desc,
            "capital_social": dados.get("capital_social"),
            "natureza_juridica": (dados.get("natureza_juridica") or {}).get("descricao"),
        },
    }


def _ler_cache(cnpj: str) -> dict | None:
    with conectar() as con:
        linha = con.execute("SELECT consultado_em, dados FROM cache_cnpj WHERE cnpj=?", (cnpj,)).fetchone()
    if not linha:
        return None
    consultado = tempo.ler(linha["consultado_em"])
    if consultado and tempo.agora() - consultado > VALIDADE_CACHE:
        return None
    return json.loads(linha["dados"])


def _gravar_cache(cnpj: str, dados: dict) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO cache_cnpj (cnpj, consultado_em, dados) VALUES (?,?,?) "
            "ON CONFLICT(cnpj) DO UPDATE SET consultado_em=excluded.consultado_em, dados=excluded.dados",
            (cnpj, tempo.iso(), json.dumps(dados, ensure_ascii=False)),
        )


def consultar(cnpj: str, token: str = "", ficticios: set[str] | None = None) -> tuple[dict | None, bool]:
    """Consulta um CNPJ. Retorna (registro ou None se não existir, veio_do_cache)."""
    cnpj = cnpj_util.so_digitos(cnpj)
    if not cnpj_util.valido(cnpj):
        raise ValueError("CNPJ inválido. Confira os 14 dígitos.")
    if ficticios and cnpj in ficticios:
        raise ErroCaptura("Este CNPJ é da base fictícia e não é enviado ao CNPJ.ws.")
    if (cache := _ler_cache(cnpj)) is not None:
        return cache, True
    if not token:
        _liberar_publica()
    dados = _get(f"{COMERCIAL if token else PUBLICA}/cnpj/{cnpj}", token)
    if dados is None:
        return None, False
    registro = para_registro(dados, cnpj)
    _gravar_cache(cnpj, registro)
    return registro, False


def separar_lista(texto: str) -> list[str]:
    partes = re.split(r"[,;\s]+", texto.strip())
    return list(dict.fromkeys(cnpj_util.so_digitos(p) for p in partes if p))


def consultar_lista(texto: str, token: str = "", ficticios: set[str] | None = None) -> dict:
    """Consulta uma lista curta. Devolve encontrados, não encontrados e erros por CNPJ."""
    cnpjs = separar_lista(texto)
    limite = MAX_LISTA_COMERCIAL if token else MAX_LISTA_PUBLICA
    if not cnpjs:
        raise ValueError("Informe ao menos um CNPJ.")
    if len(cnpjs) > limite and not token:
        # Os que já estão no cache não gastam consulta; o limite vale para os novos.
        novos = [c for c in cnpjs if _ler_cache(c) is None]
        if len(novos) > limite:
            raise ValueError(f"Sem token, informe até {limite} CNPJs novos por vez (limite da API pública).")
    saida = {"encontrados": [], "nao_encontrados": [], "erros": []}
    for numero in cnpjs:
        try:
            registro, _ = consultar(numero, token, ficticios)
        except (ValueError, ErroCaptura) as erro:
            saida["erros"].append((cnpj_util.formatar(numero), str(erro)))
            continue
        if registro is None:
            saida["nao_encontrados"].append(cnpj_util.formatar(numero))
        else:
            saida["encontrados"].append(registro)
    return saida


def pesquisar(token: str, *, cnae: str = "", uf: str = "", limite: int = 10) -> list[str]:
    """Busca CNPJs ativos por CNAE e, opcionalmente, UF (filtro, não critério de nota). Exige token comercial."""
    if not token:
        raise ValueError("A busca por filtros exige CNPJ_WS_TOKEN com acesso à pesquisa comercial.")
    cnae = re.sub(r"\D", "", cnae)
    if not re.fullmatch(r"\d{7}", cnae):
        raise ValueError("Informe um código CNAE de 7 dígitos.")
    filtros: dict = {"atividade_principal_id": cnae, "situacao_cadastral": "Ativa", "limite": limite}
    if uf:
        filtros["estado_id"] = UF_IBGE[uf]
    dados = _get(f"{COMERCIAL}/v2/pesquisa", token, filtros)
    valores = (dados or {}).get("data")
    if not isinstance(valores, list):
        raise ErroCaptura("A pesquisa do CNPJ.ws devolveu dados fora do formato esperado.")
    return [str(v) for v in valores if re.fullmatch(r"\d{14}", str(v))][:limite]
