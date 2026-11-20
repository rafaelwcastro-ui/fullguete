"""Saída estruturada da IA (seção 7.5), validada com Pydantic.

Um resultado só é aceito se passar no esquema e se todas as soluções citadas estiverem
entre as candidatas que o RAG enviou para aquele lead.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

__all__ = ["ErroValidacao", "LoteIA", "ResultadoIA", "ValidationError", "validar_lote"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class SolucaoPrincipal(_Base):
    id: str
    motivo: str = Field(min_length=3)
    confianca: float = Field(ge=0, le=1)


class SolucaoComplementar(_Base):
    id: str
    motivo: str = Field(min_length=3)


class Roteiro(_Base):
    ligacao: str = Field(min_length=10)
    email_assunto: str = Field(min_length=3)
    email_corpo: str = Field(min_length=10)
    whatsapp: str = Field(min_length=5)


class Objecao(_Base):
    objecao: str = Field(min_length=3)
    resposta: str = Field(min_length=3)


class ResultadoIA(_Base):
    lead_id: str
    resumo_empresa: str = Field(min_length=3, max_length=400)
    dores_provaveis: list[str] = Field(min_length=1, max_length=5)
    nota_aderencia: int = Field(ge=0, le=100)
    justificativa: str = Field(min_length=10, max_length=600)
    solucao_principal: SolucaoPrincipal
    solucoes_complementares: list[SolucaoComplementar] = Field(default_factory=list, max_length=3)
    perguntas_descoberta: list[str] = Field(min_length=3, max_length=3)
    roteiro: Roteiro
    objecoes: list[Objecao] = Field(min_length=1, max_length=4)
    sinais_risco: list[str] = Field(default_factory=list)
    precisa_revisao_humana: bool = False
    motivo_revisao: str = ""

    @field_validator("justificativa")
    @classmethod
    def ate_tres_frases(cls, texto: str) -> str:
        frases = [f for f in re.split(r"(?<=[.!?])\s+", texto.strip()) if f]
        if len(frases) > 3:
            raise ValueError("a justificativa deve ter até 3 frases")
        return texto


class LoteIA(_Base):
    resultados: list[ResultadoIA]


class ErroValidacao(ValueError):
    """O JSON da IA passou no esquema, mas quebrou uma regra de negócio."""


def validar_ids(resultado: ResultadoIA, candidatas: set[str]) -> ResultadoIA:
    """Rejeita qualquer solução fora da lista de candidatas (e, portanto, fora do catálogo)."""
    citadas = [resultado.solucao_principal.id, *(c.id for c in resultado.solucoes_complementares)]
    fora = [c for c in citadas if c not in candidatas]
    if fora:
        raise ErroValidacao(f"Soluções fora das candidatas do lead {resultado.lead_id}: {', '.join(fora)}.")
    if resultado.solucao_principal.id in {c.id for c in resultado.solucoes_complementares}:
        raise ErroValidacao(f"A solução principal do lead {resultado.lead_id} se repete nas complementares.")
    return resultado


def validar_lote(texto: str, candidatas_por_lead: dict[str, set[str]]) -> dict[str, ResultadoIA]:
    """Valida o JSON do lote inteiro. Lança ValidationError ou ErroValidacao."""
    lote = LoteIA.model_validate_json(texto)
    saida: dict[str, ResultadoIA] = {}
    for resultado in lote.resultados:
        if resultado.lead_id not in candidatas_por_lead:
            raise ErroValidacao(f"A IA devolveu um lead que não estava no lote: {resultado.lead_id}.")
        if resultado.lead_id in saida:
            raise ErroValidacao(f"A IA repetiu o lead {resultado.lead_id}.")
        saida[resultado.lead_id] = validar_ids(resultado, candidatas_por_lead[resultado.lead_id])
    faltando = set(candidatas_por_lead) - set(saida)
    if faltando:
        raise ErroValidacao(f"A IA deixou de fora os leads: {', '.join(sorted(faltando))}.")
    return saida


def esquema_json() -> dict:
    """Esquema enviado ao Gemini para forçar a saída estruturada."""
    return LoteIA.model_json_schema()
