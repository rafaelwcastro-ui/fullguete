"""Leitura, padronização e limpeza da planilha de leads."""
from __future__ import annotations

import re
import unicodedata
from typing import IO

import pandas as pd

# Colunas padrão do sistema -> nomes aceitos na planilha (já normalizados).
ALIASES: dict[str, list[str]] = {
    "empresa": ["empresa", "nome", "razao_social", "nome_fantasia", "company", "nome_empresa"],
    "cnpj": ["cnpj", "documento"],
    "setor": ["setor", "segmento", "ramo", "industria", "cnae", "atividade", "nicho"],
    "porte": ["porte", "tamanho", "porte_empresa", "size"],
    "cidade": ["cidade", "municipio", "city"],
    "uf": ["uf", "estado", "state"],
    "descricao": ["descricao", "sobre", "description", "resumo", "observacoes", "obs"],
    "site": ["site", "website", "url"],
    "email": ["email", "e_mail", "contato_email"],
    "telefone": ["telefone", "fone", "celular", "whatsapp", "phone"],
    "funcionarios": ["funcionarios", "colaboradores", "num_funcionarios", "employees"],
}
COLUNAS = list(ALIASES)

_MAPA_PORTE = {
    "mei": "MEI",
    "microempreendedor": "MEI",
    "me": "ME",
    "micro": "ME",
    "microempresa": "ME",
    "epp": "EPP",
    "pequena": "EPP",
    "pequeno": "EPP",
    "media": "Média",
    "medio": "Média",
    "grande": "Grande",
}


def _normaliza(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", texto.lower()).strip("_")


def identidade_empresa(empresa: str, cidade: str, uf: str) -> str:
    return "|".join(map(_normaliza, (empresa, cidade, uf)))


def ler_planilha(arquivo: IO[bytes] | str, nome: str | None = None) -> pd.DataFrame:
    nome = (nome or getattr(arquivo, "name", "") or str(arquivo)).lower()
    if nome.endswith((".xlsx", ".xls")):
        return pd.read_excel(arquivo, dtype=str)
    # CSV: detecta separador (vírgula ou ponto e vírgula) e tenta UTF-8, depois Latin-1.
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            if hasattr(arquivo, "seek"):
                arquivo.seek(0)
            return pd.read_csv(arquivo, dtype=str, sep=None, engine="python", encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Não foi possível ler o CSV. Salve-o em UTF-8.")


def _porte_padrao(valor: str, funcionarios: str) -> str:
    chave = _normaliza(valor).split("_")[0] if valor else ""
    if chave in _MAPA_PORTE:
        return _MAPA_PORTE[chave]
    try:
        n = int(re.sub(r"\D", "", funcionarios or ""))
    except ValueError:
        return valor.strip() if valor else ""
    if n <= 9:
        return "ME"
    if n <= 49:
        return "EPP"
    if n <= 249:
        return "Média"
    return "Grande"


def limpar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Padroniza colunas, limpa valores e remove duplicatas.

    Retorna o DataFrame limpo e um relatório com o que foi feito.
    """
    original = len(df)
    colunas_norm = {_normaliza(c): c for c in df.columns}
    renomear = {}
    for padrao, aliases in ALIASES.items():
        for alias in aliases:
            if alias in colunas_norm and colunas_norm[alias] not in renomear:
                renomear[colunas_norm[alias]] = padrao
                break
    df = df.rename(columns=renomear)
    if "empresa" not in df.columns:
        raise ValueError(
            "A planilha precisa de uma coluna com o nome da empresa "
            "(ex.: 'empresa', 'nome' ou 'razao_social')."
        )
    for col in COLUNAS:
        if col not in df.columns:
            df[col] = ""
    df = df[COLUNAS].fillna("").astype(str)
    for col in COLUNAS:
        df[col] = df[col].str.strip().str.replace(r"\s+", " ", regex=True)

    df["cnpj"] = df["cnpj"].str.replace(r"\D", "", regex=True)
    df["email"] = df["email"].str.lower()
    df["uf"] = df["uf"].str.upper().str[:2]
    df["site"] = df["site"].str.lower().str.replace(r"^https?://(www\.)?", "", regex=True).str.rstrip("/")
    df["porte"] = [_porte_padrao(p, f) for p, f in zip(df["porte"], df["funcionarios"])]

    df = df[df["empresa"] != ""]
    sem_nome = original - len(df)

    # CNPJs distintos identificam estabelecimentos distintos, mesmo quando têm o mesmo nome.
    antes = len(df)
    df = df.assign(_preenchidos=(df[COLUNAS] != "").sum(axis=1)).sort_values("_preenchidos", ascending=False, kind="stable")
    tem_cnpj = df["cnpj"].str.len().eq(14)
    df = df[~(tem_cnpj & df["cnpj"].duplicated())]
    tem_cnpj = df["cnpj"].str.len().eq(14)
    nome_local = df["empresa"].map(_normaliza) + "|" + df["cidade"].map(_normaliza) + "|" + df["uf"].map(_normaliza)
    sem_cnpj_unico = ~nome_local.isin(nome_local[tem_cnpj]) & ~nome_local.duplicated()
    df = df[tem_cnpj | sem_cnpj_unico].sort_index().drop(columns="_preenchidos").reset_index(drop=True)
    duplicadas = antes - len(df)

    df.insert(0, "id", range(1, len(df) + 1))
    relatorio = {
        "linhas_lidas": original,
        "sem_nome": sem_nome,
        "duplicadas": duplicadas,
        "leads_validos": len(df),
        "colunas_reconhecidas": sorted(set(renomear.values())),
    }
    return df, relatorio
