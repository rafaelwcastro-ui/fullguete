"""Única porta de saída para o LLM. Trocar de provedor é trocar este arquivo.

Hoje: Google Gemini (google-genai). Modelo leve por padrão (GEMINI_MODEL).
Nada aqui recebe dados pessoais do contato: quem monta a mensagem só usa dados da empresa.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass

from nucleo import config

from . import observabilidade

PROVEDOR = "gemini"


class ErroIA(RuntimeError):
    """Falha do LLM. Quem chama decide cair no plano B."""


@dataclass
class Resposta:
    texto: str
    tokens_entrada: int
    tokens_saida: int
    latencia_ms: int
    modelo: str


def disponivel() -> bool:
    return bool(config.chave_gemini())


def modelo() -> str:
    return config.modelo_gemini()


def _sem_refs(esquema: dict) -> dict:
    """Expande $defs/$ref, porque a saída estruturada aceita melhor um esquema plano."""
    esquema = copy.deepcopy(esquema)
    defs = esquema.pop("$defs", {})

    def resolver(no):
        if isinstance(no, dict):
            if "$ref" in no:
                nome = no["$ref"].split("/")[-1]
                return resolver(copy.deepcopy(defs[nome]))
            return {k: resolver(v) for k, v in no.items() if k not in ("title",)}
        if isinstance(no, list):
            return [resolver(v) for v in no]
        return no

    return resolver(esquema)


_clientes: dict[str, object] = {}


def _cliente():
    """Um cliente por chave, reaproveitado. Criar e descartar a cada chamada fecha a conexão antes do envio."""
    from google import genai

    chave = config.chave_gemini()
    if chave not in _clientes:
        _clientes.clear()
        _clientes[chave] = genai.Client(api_key=chave)
    return _clientes[chave]


def chamar(
    sistema: str,
    usuario: str,
    *,
    esquema: dict | None = None,
    temperatura: float = 0.2,
    max_tokens: int = 24_000,
    agente: str = "",
    versao_prompt: str | None = None,
    lote: str | None = None,
    lead_id: int | None = None,
) -> Resposta:
    """Faz uma chamada e registra o evento. Lança ErroIA em qualquer falha."""
    if not disponivel():
        raise ErroIA("Nenhuma chave de IA configurada.")
    from google.genai import errors as genai_errors
    from google.genai import types

    cfg = types.GenerateContentConfig(
        system_instruction=sistema,
        temperature=temperatura,
        max_output_tokens=max_tokens,
        **({"response_mime_type": "application/json", "response_json_schema": _sem_refs(esquema)} if esquema else {}),
    )
    nome_modelo = modelo()
    inicio = time.perf_counter()
    try:
        resposta = _cliente().models.generate_content(model=nome_modelo, contents=usuario, config=cfg)
    except genai_errors.APIError as e:
        mensagens = {
            400: "Requisição recusada pelo Gemini. Confira a chave e o modelo.",
            401: "Chave do Gemini inválida.",
            403: "A chave do Gemini não tem permissão para este modelo.",
            404: f"Modelo {nome_modelo} não encontrado. Ajuste GEMINI_MODEL.",
            429: "Limite de uso do Gemini atingido.",
        }
        erro = mensagens.get(e.code, f"Erro do Gemini ({e.code}).")
        observabilidade.registrar(agente, PROVEDOR, modelo=nome_modelo, versao_prompt=versao_prompt,
                                  latencia_ms=int((time.perf_counter() - inicio) * 1000), erro=erro, lote=lote,
                                  lead_id=lead_id)  # fmt: skip
        raise ErroIA(erro) from e
    except Exception as e:  # rede, timeout, transporte do SDK
        observabilidade.registrar(agente, PROVEDOR, modelo=nome_modelo, versao_prompt=versao_prompt,
                                  erro=f"Falha de conexão: {type(e).__name__}", lote=lote, lead_id=lead_id)  # fmt: skip
        raise ErroIA("Não foi possível conectar ao Gemini.") from e

    latencia = int((time.perf_counter() - inicio) * 1000)
    uso = getattr(resposta, "usage_metadata", None)
    t_in = int(getattr(uso, "prompt_token_count", 0) or 0)
    t_out = int(getattr(uso, "candidates_token_count", 0) or 0) + int(getattr(uso, "thoughts_token_count", 0) or 0)
    candidato = (resposta.candidates or [None])[0]
    motivo = str(getattr(candidato, "finish_reason", "") or "")
    erro = None
    if "MAX_TOKENS" in motivo:
        erro = "Resposta cortada por limite de tokens."
    elif not resposta.text:
        erro = f"Resposta vazia ({motivo or 'bloqueio'})."
    observabilidade.registrar(agente, PROVEDOR, modelo=nome_modelo, versao_prompt=versao_prompt,
                              latencia_ms=latencia, tokens_entrada=t_in, tokens_saida=t_out, erro=erro, lote=lote,
                              lead_id=lead_id)  # fmt: skip
    if erro:
        raise ErroIA(erro)
    return Resposta(resposta.text, t_in, t_out, latencia, nome_modelo)
