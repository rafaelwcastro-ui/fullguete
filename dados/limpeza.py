"""Transformação: reconhecimento de colunas, padronização e chave de deduplicação.

Evolução do dados.py da v1. Cada registro sai com a lista de problemas encontrados,
para a tela mostrar antes de importar.
"""

from __future__ import annotations

import re
from typing import IO

import pandas as pd

from . import cnpj as cnpj_util
from .features import INTERESSES, PORTES, normalizar

UFS = set(
    [
        "AC",
        "AL",
        "AP",
        "AM",
        "BA",
        "CE",
        "DF",
        "ES",
        "GO",
        "MA",
        "MT",
        "MS",
        "MG",
        "PA",
        "PB",
        "PR",
        "PE",
        "PI",
        "RJ",
        "RN",
        "RS",
        "RO",
        "RR",
        "SC",
        "SP",
        "SE",
        "TO",
    ]
)

# Campo padrão -> nomes aceitos na planilha (já normalizados com normalizar()).
ALIASES: dict[str, list[str]] = {
    "razao_social": ["razao social", "empresa", "nome", "nome empresa", "company", "razao"],
    "nome_fantasia": ["nome fantasia", "fantasia"],
    "cnpj": ["cnpj", "documento", "cnpj empresa"],
    "cnae": ["cnae", "cnae principal", "codigo cnae"],
    "setor": ["setor", "segmento", "ramo", "industria", "atividade", "nicho"],
    "porte": ["porte", "tamanho", "porte empresa", "size"],
    "funcionarios": ["funcionarios", "colaboradores", "num funcionarios", "employees"],
    "cidade": ["cidade", "municipio", "city"],
    "uf": ["uf", "estado", "state"],
    "site": ["site", "website", "url"],
    "descricao": ["descricao", "sobre", "description", "resumo", "observacoes", "obs"],
    "interesse": ["interesse", "interesse declarado", "produto interesse"],
    "origem": ["origem", "fonte", "canal"],
    "contato_nome": ["contato", "nome contato", "responsavel", "pessoa contato"],
    "cargo": ["cargo", "funcao"],
    "email": ["email", "e mail", "contato email"],
    "telefone": ["telefone", "fone", "celular", "whatsapp", "phone"],
    "base_legal": ["base legal"],
    "consentimento": ["consentimento", "opt in", "aceite"],
}
CAMPOS = list(ALIASES)
CAMPOS_EMPRESA = ["razao_social", "nome_fantasia", "cnpj", "cnae", "setor", "porte", "funcionarios", "cidade",
                  "uf", "site", "descricao", "interesse", "origem"]  # fmt: skip
CAMPOS_CONTATO = ["contato_nome", "cargo", "email", "telefone"]

_MAPA_PORTE = {"mei": "MEI", "microempreendedor": "MEI", "me": "ME", "micro": "ME", "microempresa": "ME",
               "epp": "EPP", "pequena": "EPP", "pequeno": "EPP", "media": "Média", "medio": "Média",
               "grande": "Grande"}  # fmt: skip
_ORIGENS = {"site": "site", "formulario": "formulario", "evento": "evento", "indicacao": "indicacao",
            "linkedin": "linkedin", "planilha": "planilha", "cnpj": "cnpj_lista",
            "busca_cnpj": "busca_cnpj", "cnpja": "cnpja"}  # fmt: skip
_SIM = {"sim", "s", "true", "1", "x", "yes", "y", "aceito", "consentiu"}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$")


def ler_planilha(arquivo: IO[bytes] | str, nome: str | None = None) -> pd.DataFrame:
    nome = (nome or getattr(arquivo, "name", "") or str(arquivo)).lower()
    if nome.endswith((".xlsx", ".xls")):
        return pd.read_excel(arquivo, dtype=str)
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            if hasattr(arquivo, "seek"):
                arquivo.seek(0)
            return pd.read_csv(arquivo, dtype=str, sep=None, engine="python", encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Não foi possível ler o CSV. Salve o arquivo em UTF-8.")


def reconhecer_colunas(colunas: list[str]) -> dict[str, str]:
    """Coluna original -> campo padrão. A primeira coluna que bater com cada campo vence."""
    normais = {normalizar(c): c for c in colunas}
    mapa: dict[str, str] = {}
    for campo, aliases in ALIASES.items():
        for alias in aliases:
            original = normais.get(alias)
            if original and original not in mapa:
                mapa[original] = campo
                break
    return mapa


def _texto(valor: object) -> str:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    return re.sub(r"\s+", " ", str(valor)).strip()


def padronizar_porte(valor: str, funcionarios: str = "") -> str:
    chave = normalizar(valor).split(" ")[0] if valor else ""
    if chave in _MAPA_PORTE:
        return _MAPA_PORTE[chave]
    if valor in PORTES:
        return valor
    digitos = re.sub(r"\D", "", funcionarios or "")
    if not digitos:
        return ""
    n = int(digitos)
    return "ME" if n <= 9 else "EPP" if n <= 49 else "Média" if n <= 249 else "Grande"


def padronizar_telefone(valor: str) -> tuple[str, bool]:
    digitos = re.sub(r"\D", "", valor or "")
    if digitos.startswith("55") and len(digitos) in (12, 13):
        digitos = digitos[2:]
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}", True
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}", True
    return (valor or "").strip(), not digitos


def padronizar_interesse(valor: str) -> str:
    alvo = normalizar(valor)
    for opcao in INTERESSES:
        n = normalizar(opcao)
        if alvo and (alvo == n or alvo.startswith(n[:5])):
            return opcao
    if "fraude" in alvo:
        return "Antifraude"
    return "Não sei"


def padronizar(registro: dict) -> tuple[dict, list[str]]:
    """Recebe um registro bruto (campos padrão) e devolve o registro limpo e os problemas."""
    r = {campo: _texto(registro.get(campo)) for campo in CAMPOS}
    problemas: list[str] = []

    r["razao_social"] = r["razao_social"] or r["nome_fantasia"]
    digitos = cnpj_util.so_digitos(r["cnpj"])
    r["cnpj"] = digitos
    if digitos and not cnpj_util.valido(digitos):
        problemas.append("CNPJ com dígito verificador inválido")
    r["cnae"] = re.sub(r"\D", "", r["cnae"])
    r["email"] = r["email"].lower()
    if r["email"] and not _EMAIL.match(r["email"]):
        problemas.append("E-mail inválido")
    r["telefone"], ok = padronizar_telefone(r["telefone"])
    if not ok:
        problemas.append("Telefone fora do padrão")
    r["uf"] = r["uf"].upper()[:2]
    if r["uf"] and r["uf"] not in UFS:
        problemas.append(f"UF desconhecida: {r['uf']}")
        r["uf"] = ""
    r["site"] = re.sub(r"^https?://", "", r["site"].lower()).rstrip("/")
    r["porte"] = padronizar_porte(r["porte"], r["funcionarios"])
    r["funcionarios"] = re.sub(r"\D", "", r["funcionarios"])
    r["interesse"] = padronizar_interesse(r["interesse"])
    r["origem"] = _ORIGENS.get(normalizar(r["origem"]).split(" ")[0], "") if r["origem"] else ""

    consentiu = normalizar(r["consentimento"]) in _SIM
    base = normalizar(r["base_legal"])
    if consentiu or base.startswith("consent"):
        r["base_legal"], consentiu = "consentimento", True
    elif base.startswith("legitimo"):
        r["base_legal"] = "legitimo_interesse"
    else:
        r["base_legal"] = "sem_base"
        problemas.append("Sem consentimento nem base legal")
    r["consentimento"] = consentiu

    if not r["razao_social"] and not cnpj_util.valido(digitos):
        problemas.append("Sem nome da empresa nem CNPJ válido")
    return r, problemas


def chave_dedup(registro: dict) -> str:
    """CNPJ válido identifica a empresa. Sem ele, nome + cidade + UF normalizados."""
    if cnpj_util.valido(registro.get("cnpj")):
        return f"cnpj:{cnpj_util.so_digitos(registro['cnpj'])}"
    partes = (registro.get("razao_social", ""), registro.get("cidade", ""), registro.get("uf", ""))
    return "nome:" + "|".join(normalizar(p) for p in partes)


def preparar_planilha(df: pd.DataFrame) -> tuple[list[dict], pd.DataFrame, dict]:
    """Renomeia colunas, padroniza cada linha e marca duplicados dentro do próprio arquivo.

    Retorna os registros limpos, uma prévia com a coluna de problemas e um relatório.
    """
    mapa = reconhecer_colunas(list(df.columns))
    if "razao_social" not in mapa.values() and "nome_fantasia" not in mapa.values() and "cnpj" not in mapa.values():
        raise ValueError("A planilha precisa de uma coluna com o nome da empresa ou o CNPJ.")
    dados = df.rename(columns=mapa)
    registros, previa, vistos = [], [], set()
    for bruto in dados.to_dict("records"):
        limpo, problemas = padronizar(bruto)
        chave = chave_dedup(limpo)
        if chave in vistos:
            problemas.append("Duplicado no arquivo")
        vistos.add(chave)
        limpo["_bruto"] = {k: _texto(v) for k, v in bruto.items()}
        registros.append(limpo)
        previa.append({"empresa": limpo["razao_social"], "cnpj": cnpj_util.formatar(limpo["cnpj"]),
                       "uf": limpo["uf"], "base_legal": limpo["base_legal"],
                       "problemas": "; ".join(problemas) or "Sem problemas"})  # fmt: skip
    relatorio = {
        "linhas": len(df),
        "colunas_reconhecidas": sorted(set(mapa.values())),
        "colunas_ignoradas": sorted(set(df.columns) - set(mapa)),
        "com_problemas": sum(p["problemas"] != "Sem problemas" for p in previa),
    }
    return registros, pd.DataFrame(previa), relatorio


def separar_contato(registro: dict) -> tuple[dict, dict]:
    """Dados da empresa de um lado, dados pessoais do contato do outro."""
    empresa = {k: registro.get(k, "") for k in CAMPOS_EMPRESA}
    contato = {
        "nome": registro.get("contato_nome", ""),
        "cargo": registro.get("cargo", ""),
        "email": registro.get("email", ""),
        "telefone": registro.get("telefone", ""),
    }
    return empresa, contato


_PADRAO_EMAIL_TEXTO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PADRAO_FONE_TEXTO = re.compile(r"\(?\b\d{2}\)?\s?9?\d{4}[\s.-]?\d{4}\b")


def remover_dados_pessoais(texto: str) -> str:
    """Tira e-mails e telefones que alguém tenha escrito em campos livres da empresa."""
    texto = _PADRAO_EMAIL_TEXTO.sub("[e-mail removido]", texto or "")
    return _PADRAO_FONE_TEXTO.sub("[telefone removido]", texto)
