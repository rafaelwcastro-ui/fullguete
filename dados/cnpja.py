"""CNPJá Comercial: pesquisa de estabelecimentos reais por filtros documentados.

Autenticação sem prefixo Bearer, segundo exemplos do SDK oficial CNPJá.
A pesquisa consome créditos; /credit é grátis. Não salva chave nem dados de sócios.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass

import requests

BASE = "https://api.cnpja.com"
IBGE = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
SEGMENTOS = {
    "Todos": (),
    "Varejo": ("4711302", "4712100", "4721102", "4751201", "4781400"),
    "Atacado": ("4639701", "4691500", "4693100"),
    "Tecnologia": ("6201501", "6202300", "6204000", "6311900"),
    "Alimentação": ("5611201", "5611203", "5620104"),
    "Transporte": ("4930201", "4930202", "5320202"),
}
MESES = (
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)


class ErroCnpja(RuntimeError):
    def __init__(self, mensagem: str, status: int | None = None):
        super().__init__(mensagem)
        self.status = status


@dataclass
class Resultado:
    empresas: list[dict]
    recebidas: int
    rejeitadas: int
    total: int
    next_token: str | None


def _normalizar(s: str) -> str:
    texto = "".join(ch for ch in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", texto).strip().upper()


def _obter(url: str, chave: str | None = None, params: dict | None = None) -> dict | list:
    headers = {"Authorization": chave.strip()} if chave else {}
    try:
        resposta = requests.get(url, headers=headers, params=params, timeout=(5, 22), allow_redirects=False)
    except requests.RequestException as erro:
        raise ErroCnpja("Não foi possível acessar o serviço. Verifique a rede e tente novamente.") from erro
    mensagens = {
        400: "Parâmetros rejeitados pela CNPJá. Confira os filtros da pesquisa.",
        401: "A chave CNPJá foi rejeitada. Confira se copiou a chave completa.",
        403: "Esta conta não tem permissão para utilizar este recurso.",
        429: "Créditos insuficientes ou limite de consultas da CNPJá atingido.",
        500: "Falha interna do serviço CNPJá.",
        503: "CNPJá temporariamente indisponível nesta operação.",
    }
    if resposta.status_code != 200:
        raise ErroCnpja(
            mensagens.get(resposta.status_code, f"Erro do serviço HTTP {resposta.status_code}."),
            status=resposta.status_code,
        )
    try:
        return resposta.json()
    except ValueError as erro:
        raise ErroCnpja("O serviço retornou um JSON inválido.") from erro


def saldo(chave: str) -> dict:
    """Consulta grátis; não consumimos créditos aqui."""
    if not chave.strip():
        raise ErroCnpja("Informe sua chave da CNPJá.")
    dados = _obter(f"{BASE}/credit", chave)
    if not isinstance(dados, dict):
        raise ErroCnpja("Formato de saldo inesperado.")
    return {"transient": dados.get("transient"), "perpetual": dados.get("perpetual")}


def municipio_ibge(cidade: str, uf: str) -> int:
    """Resolve o município por nome via fonte pública IBGE, sem a chave da CNPJá."""
    if not cidade.strip():
        raise ErroCnpja("Informe a cidade para pesquisar empresas.")
    dados = _obter(IBGE.format(uf=uf.upper()))
    if not isinstance(dados, list):
        raise ErroCnpja("O IBGE retornou um formato de municípios inesperado.")
    normal = _normalizar(cidade)
    encontrados = [
        cidade_ibge
        for cidade_ibge in dados
        if isinstance(cidade_ibge, dict) and _normalizar(str(cidade_ibge.get("nome", ""))) == normal
    ]
    if not encontrados:
        raise ErroCnpja(f"Município {cidade}/{uf} não encontrado no IBGE.")
    return int(encontrados[0]["id"])


def filtros(
    segmento: str,
    uf: str,
    codigo_ibge: int,
    ano: int,
    mes: int,
    cnae: str = "",
    limite: int = 10,
) -> dict:
    """Usa nomes de filtros da API comercial CNPJá, sem parâmetros inventados."""
    if segmento not in SEGMENTOS:
        raise ValueError("Segmento inválido.")
    if not re.fullmatch(r"[A-Z]{2}", uf):
        raise ValueError("UF inválida.")
    if not 1000000 <= int(codigo_ibge) <= 9999999:
        raise ValueError("Código IBGE inválido.")
    if not 2000 <= ano <= 2100 or not 1 <= mes <= 12:
        raise ValueError("Data inválida.")
    if not 1 <= limite <= 100:
        raise ValueError("Use entre 1 e 100 resultados por página.")
    params = {
        "limit": limite,
        "address.state.in": uf,
        "address.municipality.in": str(codigo_ibge),
        "status.id.in": "2",
        "founded.gte": f"{ano:04d}-{mes:02d}-01",
        "founded.lte": f"{ano:04d}-{mes:02d}-{calendar.monthrange(ano, mes)[1]:02d}",
    }
    if cnae.strip():
        codigos = [re.sub(r"\D", "", parte) for parte in cnae.split(",")]
        if not codigos or any(len(codigo) != 7 for codigo in codigos):
            raise ValueError("Informe CNAE de 7 dígitos, separando múltiplos por vírgula.")
        params["mainActivity.id.in"] = ",".join(codigos)
    elif SEGMENTOS[segmento]:
        params["mainActivity.id.in"] = ",".join(SEGMENTOS[segmento])
    return params


def _registro(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    cnpj = re.sub(r"\D", "", str(item.get("taxId") or ""))
    empresa = item.get("company") or {}
    address = item.get("address") or {}
    atividade = item.get("mainActivity") or {}
    razao = str(empresa.get("name") or "").strip()
    if len(cnpj) != 14 or not razao:
        return None
    abertura = str(item.get("founded") or "")
    porte = empresa.get("size") or {}
    nomes_porte = {1: "ME", 3: "EPP"}
    return {
        "cnpj": cnpj,
        "razao_social": razao[:150],
        "nome_fantasia": str(item.get("alias") or "")[:150],
        "cnae": re.sub(r"\D", "", str(atividade.get("id") or "")),
        "setor": str(atividade.get("text") or "")[:150],
        "descricao": str(atividade.get("text") or "")[:150],
        "porte": nomes_porte.get(porte.get("id"), ""),
        "cidade": str(address.get("city") or "")[:80],
        "uf": str(address.get("state") or "").upper()[:2],
        "data_abertura": abertura[8:10] + "/" + abertura[5:7] + "/" + abertura[:4]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", abertura)
        else "",
        "situacao_cadastral": "Ativa",
        "origem": "cnpja",
        "observacao": f"Fonte: CNPJá Comercial; abertura {abertura}.",
        "consentimento": "",
        "base_legal": "sem_base",
    }


def pesquisar(chave: str, params: dict) -> Resultado:
    if not chave.strip():
        raise ErroCnpja("Informe sua chave da CNPJá.")
    return normalizar_resposta(_obter(f"{BASE}/office", chave, params=params))


def normalizar_resposta(dados: dict | list) -> Resultado:
    """Traduz o contrato do fornecedor para registros cadastrais do Fullguete."""
    if not isinstance(dados, dict) or not isinstance(dados.get("records"), list):
        campos = list(dados) if isinstance(dados, dict) else []
        raise ErroCnpja(
            "Resposta da CNPJá diferente do formato documentado. Campos recebidos: "
            + ", ".join(str(c) for c in campos[:10])
        )
    normalizados = [_registro(item) for item in dados["records"]]
    empresas = [registro for registro in normalizados if registro is not None]
    return Resultado(
        empresas=empresas,
        recebidas=len(normalizados),
        rejeitadas=len(normalizados) - len(empresas),
        total=int(dados.get("count") or 0),
        next_token=str(dados.get("next")) if dados.get("next") else None,
    )
