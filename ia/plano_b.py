"""Plano B: monta o resultado completo (mesmo esquema do LLM) com regras e modelos de texto.

Usado no modo sem chave e quando o LLM falha duas vezes. Sempre escolhe entre as candidatas do grafo.
"""

from __future__ import annotations

import catalogo

from .esquemas import ResultadoIA

TEMA = {
    "credito_decisao": "análise de crédito",
    "monitoramento": "gestão da carteira de clientes",
    "fraude": "prevenção a fraude",
    "cobranca": "recuperação de crédito",
    "prospeccao": "conquista de novos clientes",
}
OBJECOES = {
    "credito_decisao": [
        (
            "Já conhecemos nossos clientes.",
            "Para os antigos, sim. A consulta ajuda nos clientes novos e nos que mudaram de comportamento.",
        ),
        (
            "Não temos orçamento agora.",
            "Dá para começar pelas aprovações de maior valor, onde um único atraso evitado já paga a consulta.",
        ),
    ],
    "monitoramento": [
        (
            "Nossa carteira está estável.",
            "O acompanhamento mostra mudanças antes do atraso, quando ainda dá para agir.",
        ),
        (
            "Não temos equipe para acompanhar alertas.",
            "Os alertas são priorizados, então o time olha só o que muda o risco.",
        ),
    ],
    "fraude": [
        (
            "Nossa taxa de fraude é baixa.",
            "Ótimo. O ganho costuma vir de aprovar mais pedidos bons, não só de barrar fraude.",
        ),
        (
            "Já usamos uma ferramenta.",
            "Podemos comparar em um piloto curto com os mesmos pedidos e medir aprovação e chargeback.",
        ),
    ],
    "cobranca": [
        (
            "Negativar pode afastar o cliente.",
            "A comunicação digital vem antes da negativação e muitos pagam já no primeiro aviso.",
        ),
        ("O valor em atraso é pequeno.", "Somado ao longo do ano costuma surpreender. Vale medir com uma amostra."),
    ],
    "prospeccao": [
        (
            "Já temos lista de prospects.",
            "A ideia é priorizar quem tem potencial real e atualizar os contatos que não respondem.",
        ),
        (
            "O time comercial já está cheio.",
            "Por isso mesmo: com lista melhor, o time gasta tempo só com quem tem chance de fechar.",
        ),
    ],
}


def _minusculo_inicio(texto: str) -> str:
    return texto[:1].lower() + texto[1:] if texto else texto


def confianca(candidatas: list[dict], n_sinais: int) -> float:
    if not candidatas:
        return 0.2
    topo = candidatas[0]
    segundo = candidatas[1]["pontos"] if len(candidatas) > 1 else 0.0
    detectado = any(c["tipo"] == "sinal_detectado" for c in topo["caminhos"])
    valor = 0.30 + 0.45 * topo["pontos"] + 0.08 * min(n_sinais, 3)
    if not detectado:
        valor -= 0.15
    if topo["pontos"] - segundo < 0.05:
        valor -= 0.08
    return round(max(0.15, min(valor, 0.95)), 2)


def montar(
    lead: dict,
    candidatas: list[dict],
    nota_local: dict,
    sinais_nomes: list[str],
    dores: list[str],
    segmento_nome: str,
    riscos: list[str],
) -> ResultadoIA:
    por_id = catalogo.por_id()
    principal = por_id[candidatas[0]["solucao_id"]]
    conf = confianca(candidatas, len(sinais_nomes))
    nome = lead.get("nome_fantasia") or lead.get("razao_social") or "a empresa"
    linha = principal["linha"]

    complementares = []
    for cand in candidatas[1:]:
        if len(complementares) == 2:
            break
        sol = por_id[cand["solucao_id"]]
        if sol["id"] in principal["complementares"] or sol["linha"] != linha:
            frase = cand["caminhos"][0]["frase"]
            complementares.append({"id": sol["id"], "motivo": frase[:1].upper() + frase[1:]})

    gancho = _minusculo_inicio(sinais_nomes[0]) if sinais_nomes else f"atua em {segmento_nome.lower() or 'seu setor'}"
    resolve = _minusculo_inicio(principal["o_que_resolve"])
    dor = dores[0] if dores else f"empresas como a {nome} buscam mais segurança em {TEMA[linha]}"
    razoes = "; ".join(nota_local["razoes"])
    justificativa = f"Análise local: {razoes}."
    if sinais_nomes:
        justificativa += f" Sinais encontrados: {', '.join(s.lower() for s in sinais_nomes[:3])}."
    precisa = conf < 0.6 or bool(riscos)

    return ResultadoIA(
        lead_id=str(lead["id"]),
        resumo_empresa=f"{nome}, {segmento_nome.lower() or 'segmento não identificado'}, porte {lead.get('porte') or 'não informado'}.",
        dores_provaveis=[d[:1].upper() + d[1:] for d in dores[:3]] or ["Dor ainda não identificada nos dados"],
        nota_aderencia=max(0, min(100, int(nota_local["nota"]))),
        justificativa=justificativa,
        solucao_principal={"id": principal["id"], "motivo": candidatas[0]["caminhos"][0]["frase"], "confianca": conf},
        solucoes_complementares=complementares,
        perguntas_descoberta=principal["perguntas_descoberta"],
        roteiro={
            "ligacao": (
                f"Olá, aqui é do time comercial. Vi que a {nome} {gancho}. "
                f"Empresas parecidas usam o {principal['nome']}, que {resolve} "
                "Posso te mostrar em 15 minutos como funciona?"
            ),
            "email_assunto": f"{TEMA[linha].capitalize()} para a {nome}",
            "email_corpo": (
                f"Olá. Muitas empresas do seu setor nos contam que {dor}. O {principal['nome']} {resolve} "
                "Faz sentido conversarmos 15 minutos nesta semana?"
            ),
            "whatsapp": f"Olá, tudo bem? Tenho uma ideia rápida sobre {TEMA[linha]} para a {nome}. Podemos falar 15 minutos?",
        },
        objecoes=[{"objecao": o, "resposta": r} for o, r in OBJECOES[linha]],
        sinais_risco=riscos,
        precisa_revisao_humana=precisa,
        motivo_revisao=("; ".join(riscos) if riscos else "Confiança baixa na recomendação") if precisa else "",
    )
