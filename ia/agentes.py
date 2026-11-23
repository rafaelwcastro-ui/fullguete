"""Os sete agentes do tratamento. Cada um tem um papel e registra o que fez.

Nenhum agente envia mensagem nem muda etapa por conta própria: quem grava o destino é o
Supervisor, por regras, e tudo que sai para o cliente passa pelo BDR.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field

import catalogo
from dados import cnpj as cnpj_util
from dados import cnpjws, features, limpeza
from nucleo import estados

from .esquemas import ResultadoIA

AGENTES = [
    ("higienizacao", "Higienização"),
    ("enriquecimento", "Enriquecimento"),
    ("risco", "Risco e conformidade"),
    ("qualificacao", "Qualificação"),
    ("recomendador", "Recomendador"),
    ("redator", "Redator"),
    ("supervisor", "Supervisor"),
]
NOME_AGENTE = dict(AGENTES)


@dataclass
class Contexto:
    lead: dict
    contato: dict | None
    consentimento: dict | None
    tratamento_id: int = 0
    problemas: list[str] = field(default_factory=list)
    feats: dict = field(default_factory=dict)
    sinais_nomes: list[str] = field(default_factory=list)
    dores: list[str] = field(default_factory=list)
    segmento_nome: str = ""
    nota_local: dict = field(default_factory=dict)
    propensao: float = 0.0
    cluster: int | None = None
    candidatas: list[dict] = field(default_factory=list)
    resultado: ResultadoIA | None = None
    motor: str = "local"
    plano_b: bool = False
    riscos: list[str] = field(default_factory=list)
    bloqueio: tuple[str, str] | None = None  # (etapa, explicação)
    etapas: list[dict] = field(default_factory=list)
    alteracoes: dict = field(default_factory=dict)  # campos do lead a gravar
    custo: float = 0.0
    llm_ms: int = 0  # parte do tempo da chamada ao LLM atribuída a este lead
    inicio: float = field(default_factory=time.perf_counter)

    def registrar(self, agente: str, status: str, detalhe: str, ms: int) -> None:
        self.etapas.append({"agente": agente, "status": status, "detalhe": detalhe, "tempo_ms": ms})


def _cronometro():
    inicio = time.perf_counter()
    return lambda: int((time.perf_counter() - inicio) * 1000)


# ---------- 1. Higienização ----------
def higienizacao(ctx: Contexto) -> None:
    ms = _cronometro()
    lead = ctx.lead
    if lead.get("cnpj") and not cnpj_util.valido(lead["cnpj"]):
        ctx.problemas.append("CNPJ com dígito verificador inválido")
    if lead.get("uf") and lead["uf"] not in limpeza.UFS:
        ctx.alteracoes["uf"] = None
        ctx.problemas.append("UF inválida removida")
    for campo in ("descricao", "observacao"):
        original = lead.get(campo) or ""
        limpo = limpeza.remover_dados_pessoais(original)
        if limpo != original:
            ctx.alteracoes[campo] = limpo
            lead[campo] = limpo
            ctx.problemas.append(f"Dados pessoais removidos do campo {campo}")
    if ctx.contato:
        email = ctx.contato.get("email") or ""
        if email and not limpeza._EMAIL.match(email):
            ctx.problemas.append("E-mail do contato inválido")
        _, ok = limpeza.padronizar_telefone(ctx.contato.get("telefone") or "")
        if not ok:
            ctx.problemas.append("Telefone do contato fora do padrão")
    else:
        ctx.problemas.append("Sem dados de contato")
    detalhe = "Dados padronizados. Contato pessoal separado da empresa."
    if ctx.problemas:
        detalhe += " Problemas: " + "; ".join(ctx.problemas) + "."
    ctx.registrar("higienizacao", "alerta" if ctx.problemas else "ok", detalhe, ms())


# ---------- 2. Enriquecimento ----------
def _sinais_simulados(lead: dict, sinais_texto: list[str], segmento: str) -> dict:
    """Sinais que, na vida real, viriam de bases da Equifax. Aqui são simulados e rotulados como tal.

    A simulação é determinística (semente pelo CNPJ ou nome) e coerente com o texto e o segmento.
    """
    semente = int(hashlib.sha1((lead.get("cnpj") or lead["razao_social"]).encode()).hexdigest()[:8], 16)
    rng = random.Random(semente)
    regras = catalogo.carregar_regras()
    tipicos = {a["para"] for a in regras["segmento_sinal"] if a["de"] == segmento and a["peso"] >= 0.6}
    saida = {}
    for sinal in regras["sinais"]:
        chave = sinal.get("sinal_simulado")
        if not chave:
            continue
        chance = 0.85 if sinal["id"] in sinais_texto else 0.45 if sinal["id"] in tipicos else 0.05
        saida[chave] = rng.random() < chance
    if saida.get("tem_ecommerce"):
        saida["volume_pedidos_online_mes"] = rng.randint(2, 80) * 1000
    saida["_simulado"] = True
    return saida


def enriquecimento(ctx: Contexto, token: str, ficticios: set[str]) -> None:
    ms = _cronometro()
    lead = ctx.lead
    notas = []
    real = json.loads(lead["dados_cnpjws"]) if lead.get("dados_cnpjws") else None
    if not lead["base_ficticia"] and cnpj_util.valido(lead.get("cnpj")) and real is None:
        try:
            registro, do_cache = cnpjws.consultar(lead["cnpj"], token, ficticios)
        except (ValueError, cnpjws.ErroCaptura) as erro:
            notas.append(f"CNPJ.ws indisponível: {erro}")
        else:
            if registro:
                real = registro["dados_cnpjws"]
                ctx.alteracoes["dados_cnpjws"] = json.dumps(real, ensure_ascii=False)
                for campo in ("setor", "cnae", "porte", "situacao_cadastral", "cidade", "uf"):
                    if registro.get(campo) and not lead.get(campo):
                        lead[campo] = registro[campo]
                        ctx.alteracoes[campo] = registro[campo]
                notas.append("Dados reais do CNPJ.ws" + (" (cache)" if do_cache else "") + ".")
    elif lead["base_ficticia"]:
        notas.append("Base fictícia: CNPJ não consultado na API.")
    elif real:
        notas.append("Dados reais do CNPJ.ws já presentes.")

    texto = features.texto_empresa(lead)
    segmento = features.detectar_segmento(lead.get("cnae", ""), texto)
    simulados = json.loads(lead.get("sinais_simulados") or "{}")
    if not lead["base_ficticia"]:
        if simulados:
            ctx.alteracoes["sinais_simulados"] = "{}"
        simulados = {}
        notas.append("Empresa real: sem sinais comportamentais simulados. Apenas cadastro e texto informado.")
    elif not simulados:
        simulados = _sinais_simulados(lead, features.detectar_sinais(texto, {}), segmento)
        ctx.alteracoes["sinais_simulados"] = json.dumps(simulados, ensure_ascii=False)
        notas.append("Sinais fictícios de demonstração adicionados.")
    lead["sinais_simulados"] = simulados
    lead["segmento"] = segmento
    ctx.feats = features.calcular(lead)
    ctx.alteracoes["segmento"] = segmento
    regras = catalogo.carregar_regras()
    sinais = {s["id"]: s for s in regras["sinais"]}
    ctx.sinais_nomes = [sinais[s]["nome"] for s in ctx.feats["sinais"]]
    ctx.dores = [sinais[s]["dor"] for s in ctx.feats["sinais"]]
    ctx.segmento_nome = {s["id"]: s["nome"] for s in regras["segmentos"]}.get(segmento, "Outros")
    notas.append(f"Segmento {ctx.segmento_nome}; {len(ctx.sinais_nomes)} sinal(is) encontrados.")
    ctx.registrar("enriquecimento", "ok", " ".join(notas), ms())


# ---------- 3. Risco e conformidade ----------
def risco(ctx: Contexto) -> None:
    ms = _cronometro()
    lead, consent = ctx.lead, ctx.consentimento or {}
    if lead.get("opt_out") or consent.get("opt_out_em"):
        ctx.bloqueio = (estados.RETIDO, "O titular pediu opt-out. Sem contato até regularizar.")
    elif consent.get("base_legal", "sem_base") == "sem_base":
        ctx.bloqueio = (estados.RETIDO, "Sem base legal válida para contato.")
    situacao = features.normalizar(lead.get("situacao_cadastral") or "ativa")
    if situacao not in ("ativa", ""):
        ctx.riscos.append(f"Empresa com situação cadastral {lead['situacao_cadastral']}")
    if not (lead.get("descricao") or lead.get("setor") or lead.get("cnae")):
        ctx.riscos.append("Dados insuficientes para avaliar a empresa")
    if "CNPJ com dígito verificador inválido" in ctx.problemas:
        ctx.riscos.append("CNPJ inválido")
    if ctx.bloqueio:
        ctx.registrar("risco", "bloqueado", ctx.bloqueio[1] + " A IA não é chamada para este lead.", ms())
    elif ctx.riscos:
        ctx.registrar("risco", "alerta", "Vai para revisão humana: " + "; ".join(ctx.riscos) + ".", ms())
    else:
        ctx.registrar("risco", "ok", "Base legal válida, sem opt-out, empresa ativa.", ms())


# ---------- 4 a 6: payload enviado ao LLM ----------
def payload_llm(ctx: Contexto, contexto_candidatas: list[dict]) -> dict:
    """Só dados da empresa. Nome, e-mail e telefone do contato nunca entram. Localização também não."""
    lead = ctx.lead
    simulados = {k: v for k, v in (lead.get("sinais_simulados") or {}).items() if not k.startswith("_") and v}
    return {
        "lead_id": str(lead["id"]),
        "empresa": {
            "nome": lead.get("nome_fantasia") or lead["razao_social"],
            "setor": lead.get("setor") or "",
            "cnae": lead.get("cnae") or "",
            "porte": lead.get("porte") or "",
            "funcionarios": lead.get("funcionarios"),
            "descricao": lead.get("descricao") or "",
            "interesse_declarado": lead.get("interesse") or "Não sei",
            "situacao_cadastral": lead.get("situacao_cadastral") or "",
        },
        "segmento": ctx.segmento_nome,
        "sinais": ctx.sinais_nomes,
        "sinais_de_mercado_simulados": simulados if lead["base_ficticia"] else {},
        "origem_evidencia": "ficticia" if lead["base_ficticia"] else "dados_cadastrais_publicos",
        "limites_evidencia": (
            "CNAE, atividade e descrição NÃO provam inadimplência, faturamento, cobrança, fraude ou venda a prazo."
        ),
        "riscos_ja_identificados": ctx.riscos,
        "candidatas": contexto_candidatas,
    }
