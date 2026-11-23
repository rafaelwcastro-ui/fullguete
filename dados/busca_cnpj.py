"""Descoberta de CNPJs reais por cidade, atividade e data de abertura.

LocalizaCNPJ: plano Free exige chave individual. Não envia dados de sócios,
contatos nem documentos pessoais ao pipeline do Fullguete.
"""

from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass

import requests

URL = "https://api.localizacnpj.com.br/busca/filtros"
URL_CONTA = "https://api.localizacnpj.com.br/auth/me"
SEGMENTOS = {
    "Varejo": "VAREJISTA",
    "Atacado": "ATACADISTA",
    "Indústria": "FABRIC",
    "Transporte": "TRANSPORTE",
    "Tecnologia": "SOFTWARE",
    "Alimentação": "RESTAURANTE",
    "Todos": "",
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
PORTES = {"01": "ME", "03": "EPP"}


class ErroBusca(RuntimeError):
    """Erro esperado da API, seguro para apresentação no portal."""


@dataclass
class PaginaEmpresas:
    registros: list[dict]
    has_more: bool
    next_cursor: str | None
    snapshot: str | None
    total_api: int = 0
    descartados: int = 0


def normalizar_cidade(cidade: str) -> str:
    """A Receita guarda nomes de município sem acentos (ex.: SAO PAULO).

    A API pesquisa prefixos sem remover diacríticos automaticamente.
    """
    ascii_cidade = "".join(
        letra for letra in unicodedata.normalize("NFKD", cidade.strip()) if not unicodedata.combining(letra)
    )
    return re.sub(r"\s+", " ", ascii_cidade).upper()


def verificar_conexao(token: str) -> dict:
    """Testa o acesso sem buscar CNPJs ou expor dados da conta."""
    if not token.strip():
        raise ErroBusca("Informe a chave da LocalizaCNPJ antes de testar a conexão.")
    try:
        resposta = requests.get(
            URL_CONTA,
            headers={"Authorization": f"Bearer {token.strip()}"},
            timeout=(5, 12),
            allow_redirects=False,
        )
    except requests.RequestException as erro:
        raise ErroBusca("Não foi possível conectar à LocalizaCNPJ.") from erro
    if resposta.status_code != 200:
        raise ErroBusca(
            "Chave inválida ou acesso indisponível."
            if resposta.status_code in (401, 403)
            else f"Não foi possível verificar a chave (HTTP {resposta.status_code})."
        )
    try:
        dados = resposta.json()
    except ValueError as erro:
        raise ErroBusca("A autenticação retornou um formato inválido.") from erro
    if not isinstance(dados, dict):
        raise ErroBusca("A autenticação retornou um formato inválido.")
    return {"plano": str(dados.get("plan") or "não informado"), "ativa": dados.get("active") is True}


def parametros(
    segmento: str,
    cidade: str,
    uf: str,
    ano: int,
    mes: int,
    cnae: str = "",
    limite: int = 25,
    cursor: str | None = None,
) -> dict:
    """Constrói filtros remotos: a data é aplicada pela API, não após paginação."""
    if segmento not in SEGMENTOS:
        raise ValueError("Segmento inválido.")
    if not cidade.strip() or len(cidade.strip()) < 2 or len(cidade) > 100:
        raise ValueError("Informe uma cidade com pelo menos dois caracteres.")
    if not re.fullmatch(r"[A-Z]{2}", uf):
        raise ValueError("Selecione uma UF válida.")
    if not 2000 <= ano <= 2100 or not 1 <= mes <= 12:
        raise ValueError("Mês ou ano inválido.")
    if not 1 <= limite <= 100:
        raise ValueError("Quantidade por página inválida.")
    codigo = re.sub(r"\D", "", cnae)
    if cnae.strip() and len(codigo) != 7:
        raise ValueError("Informe um CNAE de sete dígitos ou deixe o campo vazio.")
    fim = calendar.monthrange(ano, mes)[1]
    filtros = {
        "cidade": normalizar_cidade(cidade),
        "uf": uf,
        "abertura_de": f"{ano:04d}-{mes:02d}-01",
        "abertura_ate": f"{ano:04d}-{mes:02d}-{fim:02d}",
        "situacao": "02",
        "limit": limite,
    }
    if codigo:
        filtros["cnae"] = codigo
    elif SEGMENTOS[segmento]:
        filtros["atividade"] = SEGMENTOS[segmento]
    if cursor:
        filtros["cursor"] = cursor
    return filtros


def _data(valor: str | None) -> str:
    numero = re.sub(r"\D", "", valor or "")
    if len(numero) == 8:
        return f"{numero[6:8]}/{numero[4:6]}/{numero[0:4]}"
    return ""


def normalizar_empresa(item: dict, snapshot: str | None) -> dict | None:
    """Somente dados cadastrais de empresa: sem sócios ou dados pessoais do contato."""
    if not isinstance(item, dict):
        return None
    cnpj = re.sub(r"\D", "", str(item.get("cnpj_completo") or ""))
    razao = str(item.get("razao_social") or (item.get("empresa") or {}).get("razao_social") or "").strip()
    if len(cnpj) != 14 or not razao:
        return None
    porte = str(item.get("porte") or (item.get("empresa") or {}).get("porte_empresa") or "")
    abertura = _data(item.get("data_abertura") or item.get("data_inicio_atividade"))
    atividade = str(item.get("cnae_descricao") or "").strip()[:150]
    return {
        "cnpj": cnpj,
        "razao_social": razao[:150],
        "nome_fantasia": str(item.get("nome_fantasia") or "")[:150],
        "cnae": str(item.get("cnae_principal") or item.get("cnae_fiscal_principal") or ""),
        "setor": atividade,
        "porte": PORTES.get(porte, ""),
        "cidade": str(item.get("municipio") or "").strip()[:80],
        "uf": str(item.get("uf") or "").upper()[:2],
        "descricao": atividade,
        "data_abertura": abertura,
        "situacao_cadastral": "Ativa" if str(item.get("situacao") or "") == "02" else "",
        "origem": "busca_cnpj",
        "observacao": f"Fonte: LocalizaCNPJ / Receita Federal; base {snapshot or 'não informada'}; abertura {abertura}.",
        "base_legal": "sem_base",
        "consentimento": "",
    }


def buscar(token: str, filtros: dict) -> PaginaEmpresas:
    """Consulta paginada com chave apenas no backend. Nenhuma resposta sintética."""
    if not token.strip():
        raise ErroBusca("Configure LOCALIZA_CNPJ_TOKEN ou informe uma chave gratuita nesta tela.")
    try:
        resposta = requests.get(
            URL,
            headers={"Authorization": f"Bearer {token.strip()}"},
            params=filtros,
            timeout=(5, 25),
            allow_redirects=False,
        )
    except requests.RequestException as erro:
        raise ErroBusca("Não foi possível conectar à base de CNPJs. Tente novamente.") from erro

    erros = {
        401: "Chave de API inválida ou não autorizada.",
        403: "Esta conta não tem acesso à busca por filtros.",
        409: "A base de empresas foi atualizada. Refaça a consulta desde a primeira página.",
        429: "Cota ou limite de requisições atingido. Confira o consumo da chave.",
        503: "O provedor está indisponível ou a consulta é muito ampla. Refine os filtros.",
    }
    if resposta.status_code != 200:
        raise ErroBusca(erros.get(resposta.status_code, f"Erro do provedor (HTTP {resposta.status_code})."))
    try:
        dados = resposta.json()
    except ValueError as erro:
        raise ErroBusca("A API retornou uma resposta inválida.") from erro
    if not isinstance(dados, dict) or not isinstance(dados.get("resultados"), list):
        raise ErroBusca("O provedor retornou um formato inesperado. Não foram importados dados.")
    snapshot = dados.get("snapshot")
    registros = [normalizar_empresa(item, snapshot) for item in dados["resultados"]]
    validos = [item for item in registros if item is not None]
    return PaginaEmpresas(
        registros=validos,
        has_more=bool(dados.get("has_more")),
        next_cursor=dados.get("next_cursor"),
        snapshot=str(snapshot) if snapshot else None,
        total_api=len(registros),
        descartados=len(registros) - len(validos),
    )
