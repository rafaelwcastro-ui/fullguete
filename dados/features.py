"""Engenharia de variáveis (camada ouro).

As mesmas funções geram as variáveis dos leads novos e do histórico de treino,
para que o modelo de propensão veja sempre o mesmo formato.
UF e município ficam de fora de propósito: localização não entra na nota.
"""

from __future__ import annotations

import math
import re
import unicodedata
from functools import lru_cache

import catalogo

PORTES = ["MEI", "ME", "EPP", "Média", "Grande"]
ORIGENS = ["site", "formulario", "evento", "indicacao", "linkedin", "planilha", "cnpj_lista"]
INTERESSES = ["Crédito", "Antifraude", "Cobrança", "Prospecção", "Não sei"]

FEATURES_NUMERICAS = [
    "porte_ordem",
    "log_funcionarios",
    "n_sinais",
    "forca_segmento",
    "interesse_declarado",
    "interesse_alinhado",
    "empresa_ativa",
    "tem_site",
]
FEATURES_CATEGORICAS = ["segmento", "origem"]
FEATURES = FEATURES_NUMERICAS + FEATURES_CATEGORICAS


def normalizar(texto: object) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", texto)).strip()


@lru_cache(maxsize=4096)
def _padrao(termo: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z0-9]){re.escape(normalizar(termo))}(?![a-z0-9])")


def _contem(texto_norm: str, termo: str) -> bool:
    return bool(_padrao(termo).search(texto_norm))


def detectar_segmento(cnae: str, texto: str, regras: dict | None = None) -> str:
    """Escolhe o segmento pelo texto (peso 2 por palavra) e pelo prefixo do CNAE (peso 1)."""
    regras = regras or catalogo.carregar_regras()
    texto_norm = normalizar(texto)
    cnae = re.sub(r"\D", "", str(cnae or ""))
    melhor, melhor_pontos = "outros", 0.0
    for seg in regras["segmentos"]:
        pontos = 2.0 * sum(_contem(texto_norm, p) for p in seg["palavras_chave"])
        prefixos = [p for p in seg["cnae_prefixos"] if cnae.startswith(p)]
        if prefixos:
            pontos += 1.0 + 0.01 * max(len(p) for p in prefixos)
        if pontos > melhor_pontos:
            melhor, melhor_pontos = seg["id"], pontos
    return melhor


def detectar_sinais(texto: str, sinais_simulados: dict | None = None, regras: dict | None = None) -> list[str]:
    """Sinais encontrados no texto da empresa ou marcados nos dados simulados."""
    regras = regras or catalogo.carregar_regras()
    texto_norm = normalizar(texto)
    simulados = sinais_simulados or {}
    achados = []
    for sinal in regras["sinais"]:
        no_texto = any(_contem(texto_norm, p) for p in sinal["palavras_chave"])
        chave_sim = sinal.get("sinal_simulado")
        no_simulado = bool(chave_sim and simulados.get(chave_sim))
        if no_texto or no_simulado:
            achados.append(sinal["id"])
    return achados


def _linhas_dos_sinais(sinais: list[str], regras: dict) -> set[str]:
    por_id = catalogo.por_id()
    return {por_id[a["para"]]["linha"] for a in regras["sinal_solucao"] if a["de"] in sinais and a["para"] in por_id}


def texto_empresa(lead: dict) -> str:
    """Só dados da empresa. Nome, e-mail e telefone do contato nunca entram aqui."""
    partes = [lead.get("razao_social"), lead.get("nome_fantasia"), lead.get("setor"), lead.get("descricao")]
    return " ".join(str(p) for p in partes if p)


def calcular(lead: dict, regras: dict | None = None) -> dict:
    """Devolve as variáveis do lead e os sinais/segmento detectados."""
    regras = regras or catalogo.carregar_regras()
    texto = texto_empresa(lead)
    segmento = lead.get("segmento") or detectar_segmento(lead.get("cnae", ""), texto, regras)
    sinais = detectar_sinais(texto, lead.get("sinais_simulados") or {}, regras)
    pesos_seg = {a["para"]: a["peso"] for a in regras["segmento_sinal"] if a["de"] == segmento}
    forca = max((pesos_seg.get(s, 0.0) for s in sinais), default=0.0)

    interesse = lead.get("interesse") or "Não sei"
    linha_interesse = regras.get("interesse_linha", {}).get(interesse)
    alinhado = int(bool(linha_interesse) and linha_interesse in _linhas_dos_sinais(sinais, regras))

    porte = lead.get("porte") or ""
    try:
        funcionarios = max(int(lead.get("funcionarios") or 0), 0)
    except (TypeError, ValueError):
        funcionarios = 0
    situacao = normalizar(lead.get("situacao_cadastral") or "ativa")
    origem = lead.get("origem") or "formulario"

    return {
        "segmento": segmento,
        "origem": origem if origem in ORIGENS else "formulario",
        "porte_ordem": PORTES.index(porte) if porte in PORTES else 2,
        "log_funcionarios": round(math.log1p(funcionarios), 3),
        "n_sinais": len(sinais),
        "forca_segmento": round(forca, 3),
        "interesse_declarado": int(interesse in INTERESSES[:4]),
        "interesse_alinhado": alinhado,
        "empresa_ativa": int(situacao in ("ativa", "")),
        "tem_site": int(bool(lead.get("site"))),
        "sinais": sinais,
    }
