"""Captura dados empresariais pela API CNPJ.ws."""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd
import requests

PUBLICA = "https://publica.cnpj.ws"
COMERCIAL = "https://comercial.cnpj.ws"
MAX_PUBLICA = 3
MAX_PESQUISA = 25

UF_IBGE = dict(zip(
    "RO AC AM RR PA AP TO MA PI CE RN PB PE AL SE BA MG ES RJ SP PR SC RS MS MT GO DF".split(),
    (11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53),
    strict=True,
))


class ErroCaptura(RuntimeError):
    """Falha que pode ser exibida no portal sem dados da autenticação."""


@dataclass
class ResultadoCaptura:
    empresas: pd.DataFrame
    nao_encontrados: int
    aviso: str = ""


def _get(sessao: requests.Session, url: str, params: dict | None = None) -> dict | None:
    try:
        resposta = sessao.get(url, params=params, timeout=(4, 12), allow_redirects=False)
    except requests.RequestException as erro:
        raise ErroCaptura("Não foi possível conectar à API de CNPJ.") from erro
    if resposta.status_code == 404:
        return None
    if resposta.status_code in (401, 403):
        raise ErroCaptura("O CNPJ.ws recusou o acesso. Confira o token e a permissão do plano.")
    if resposta.status_code == 429:
        raise ErroCaptura("A API de CNPJ atingiu o limite de consultas. Aguarde e tente novamente.")
    if resposta.status_code != 200:
        raise ErroCaptura(f"A API de CNPJ devolveu um erro ({resposta.status_code}).")
    try:
        dados = resposta.json()
    except ValueError as erro:
        raise ErroCaptura("A API de CNPJ devolveu dados fora do formato esperado.") from erro
    if not isinstance(dados, dict):
        raise ErroCaptura("A API de CNPJ devolveu dados fora do formato esperado.")
    return dados


def _registro(dados: dict, cnpj: str) -> dict:
    unidade = dados.get("estabelecimento") or {}
    atividade = unidade.get("atividade_principal") or {}
    cidade = unidade.get("cidade") or {}
    estado = unidade.get("estado") or {}
    porte = dados.get("porte") or {}
    simples = dados.get("simples") or {}
    cadastro = unidade.get("situacao_cadastral")
    descricao = str(atividade.get("descricao") or "")
    complemento = []
    if cadastro:
        complemento.append(f"Situação cadastral: {cadastro}.")
    if unidade.get("data_inicio_atividade"):
        complemento.append(f"Início da atividade: {unidade['data_inicio_atividade']}.")
    telefone = ""
    for sufixo in ("1", "2"):
        if numero := unidade.get(f"telefone{sufixo}"):
            telefone = f"{unidade.get(f'ddd{sufixo}') or ''} {numero}".strip()
            break
    return {
        "empresa": unidade.get("nome_fantasia") or dados.get("razao_social") or "",
        "cnpj": cnpj,
        "setor": descricao,
        "porte": {"01": "ME", "03": "EPP"}.get(str(porte.get("id") or "").zfill(2), "")
        if simples.get("mei") != "Sim" else "MEI",
        "cidade": cidade.get("nome") or "",
        "uf": estado.get("sigla") or "",
        "descricao": " ".join([descricao, *complemento]).strip(),
        "email": unidade.get("email") or "",
        "telefone": telefone,
    }


def _consultar(sessao: requests.Session, base: str, cnpjs: list[str]) -> ResultadoCaptura:
    registros = []
    nao_encontrados = 0
    aviso = ""
    for cnpj in cnpjs:
        try:
            dados = _get(sessao, f"{base}/cnpj/{cnpj}")
        except ErroCaptura as erro:
            if not registros:
                raise
            aviso = f"Mesmo com a busca interrompida, {len(registros)} cadastro(s) foram carregados. {erro}"
            break
        if dados is None:
            nao_encontrados += 1
        else:
            registros.append(_registro(dados, cnpj))
    return ResultadoCaptura(pd.DataFrame(registros), nao_encontrados, aviso)


def consultar_cnpjs(entrada: str, token: str = "") -> ResultadoCaptura:
    """Consulta uma lista curta de CNPJs informados no portal."""
    partes = re.split(r"[,;\s]+", entrada.strip())
    cnpjs = list(dict.fromkeys(re.sub(r"[./-]", "", parte) for parte in partes if parte))
    limite = MAX_PESQUISA if token else MAX_PUBLICA
    if not cnpjs or any(not re.fullmatch(r"[0-9]{14}", cnpj) for cnpj in cnpjs):
        raise ValueError("Informe CNPJs de 14 dígitos, um por linha ou separados por vírgula.")
    if len(cnpjs) > limite:
        raise ValueError(f"Informe até {limite} CNPJs por consulta.")
    with requests.Session() as sessao:
        if token:
            sessao.headers["x_api_token"] = token
        return _consultar(sessao, COMERCIAL if token else PUBLICA, cnpjs)


def pesquisar(
    token: str, *, cnae: str = "", uf: str = "", cidade_ibge: str = "", limite: int = 10,
) -> ResultadoCaptura:
    """Descobre empresas ativas por CNAE e região, depois consulta os cadastros."""
    if not token:
        raise ValueError("Configure CNPJ_WS_TOKEN com acesso à pesquisa comercial.")
    cnae = re.sub(r"[./\-\s]", "", cnae)
    cidade_ibge = cidade_ibge.strip()
    if cnae and not re.fullmatch(r"[0-9]{7}", cnae):
        raise ValueError("Informe um código CNAE de 7 dígitos.")
    if cidade_ibge and not re.fullmatch(r"[0-9]{7}", cidade_ibge):
        raise ValueError("Informe o código IBGE do município com 7 dígitos.")
    if uf and uf not in UF_IBGE:
        raise ValueError("Selecione uma UF válida.")
    filtros = {"atividade_principal_id": cnae, "estado_id": UF_IBGE.get(uf), "cidade_id": cidade_ibge}
    filtros = {nome: valor for nome, valor in filtros.items() if valor}
    if not filtros:
        raise ValueError("Preencha pelo menos um filtro de CNAE, UF ou município.")
    if not 1 <= limite <= MAX_PESQUISA:
        raise ValueError(f"A pesquisa aceita de 1 a {MAX_PESQUISA} resultados.")

    with requests.Session() as sessao:
        sessao.headers["x_api_token"] = token
        dados = _get(sessao, f"{COMERCIAL}/v2/pesquisa", {
            **filtros, "limite": limite, "situacao_cadastral": "Ativa",
        })
        valores = (dados or {}).get("data")
        if dados is None:
            raise ErroCaptura("O endpoint de busca comercial do CNPJ.ws não foi encontrado.")
        if not isinstance(valores, list) or any(not re.fullmatch(r"[0-9]{14}", str(c)) for c in valores):
            raise ErroCaptura("A pesquisa por CNPJ devolveu dados fora do formato esperado.")
        cnpjs = list(dict.fromkeys(map(str, valores)))[:limite]
        return _consultar(sessao, COMERCIAL, cnpjs)
