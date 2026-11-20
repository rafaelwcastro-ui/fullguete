"""Base fictícia de demonstração, gerada com semente fixa.

Tudo aqui é inventado: empresas, CNPJs, pessoas, e-mails (domínio .exemplo) e resultados.
Os CNPJs têm dígitos verificadores válidos, mas carregam origem base_ficticia e nunca
são enviados ao CNPJ.ws.
"""

from __future__ import annotations

import math
import random
import unicodedata

from . import cnpj as cnpj_util
from . import features

SEMENTE = 20261120
SENHA_DEMO = "fullguete-demo"

USUARIOS_DEMO = [
    {"login": "gestor", "nome": "Gestor Demo", "papel": "gestor", "meta_contatos_dia": 0},
    {"login": "bdr.ana", "nome": "Ana Demo", "papel": "bdr", "meta_contatos_dia": 20},
    {"login": "bdr.bruno", "nome": "Bruno Demo", "papel": "bdr", "meta_contatos_dia": 20},
    {"login": "bdr.carla", "nome": "Carla Demo", "papel": "bdr", "meta_contatos_dia": 20},
    {"login": "executivo", "nome": "Executiva Demo", "papel": "executivo", "meta_contatos_dia": 0},
]

ICP_PADRAO = {
    "nome": "ICP inicial",
    "descricao": (
        "Empresas que vendem a prazo, concedem crédito, vendem online ou cobram mensalidades, "
        "com volume suficiente para precisar de decisão de crédito, prevenção a fraude ou cobrança estruturada."
    ),
    "setores": [
        "Atacado",
        "Distribuição",
        "Indústria",
        "Varejo com crediário",
        "E-commerce",
        "Financeiras",
        "Fintechs",
        "Educação",
        "Saúde",
    ],
    "portes": ["EPP", "Média", "Grande"],
    "palavras_chave": [
        "a prazo",
        "crediário",
        "boleto",
        "e-commerce",
        "inadimplência",
        "chargeback",
        "empréstimo",
        "mensalidade",
    ],
}

# Frases usadas nas descrições. Cada uma contém palavras que os detectores reconhecem.
FRASE_SINAL = {
    "vende_prazo_pj": "Vende para outras empresas com boleto a prazo de 30 a 60 dias.",
    "crediario_pf": "Oferece crediário próprio e carnê para clientes pessoa física.",
    "recorrencia_pf": "Cobra mensalidades dos clientes todos os meses.",
    "concede_credito": "Concede empréstimo pessoal e financiamento pelo celular.",
    "credito_pme": "Atende pequenas empresas com capital de giro e prazo estendido.",
    "time_dados": "Tem um time de dados que desenvolve modelos próprios de risco.",
    "alto_volume_decisoes": "Analisa milhares de propostas por dia numa esteira de crédito.",
    "pre_aprovacao": "Planeja campanhas de crédito pré aprovado para a base.",
    "baixo_volume": "Comércio local com poucas vendas a prazo, quase sempre fiado para clientes conhecidos.",
    "carteira_pj": "Atende uma carteira de clientes ativos com contratos recorrentes.",
    "risco_carteira": "Quer fazer revisão de limites e acompanhar o risco da carteira.",
    "rentabilidade_carteira": "Busca mais rentabilidade com venda cruzada para quem já é cliente.",
    "ecommerce_volume": "Vende pela loja virtual e recebe muitos pedidos online por dia.",
    "chargeback": "Reclama de chargeback e contestações de compras no cartão.",
    "onboarding_digital": "Faz cadastro online e abertura de conta pelo celular.",
    "app_marketplace": "Opera um marketplace com cupons e programa de fidelidade.",
    "pix_p2p": "Oferece conta digital com Pix e transferências entre pessoas.",
    "instituicao_regulada": "É instituição de pagamento autorizada pelo Banco Central.",
    "inadimplencia": "Vem sofrendo com inadimplência e atrasos em contas a receber.",
    "titulos_vencidos": "Acumula duplicatas e boletos vencidos de clientes empresa.",
    "contato_devedor": "Tem dificuldade de localizar devedor e montar uma régua de cobrança.",
    "expansao_comercial": "Está em expansão e o time comercial busca novos clientes.",
    "base_desatualizada": "O cadastro de clientes está desatualizado, com dados incompletos.",
    "campanhas_marketing": "Investe em campanhas de marketing digital e mídia.",
}

FRASES_NEUTRAS = [
    "Empresa familiar com equipe enxuta.",
    "Atua há mais de dez anos no mercado.",
    "Tem sede própria e atendimento presencial.",
    "Busca melhorar processos internos.",
]

# segmento: (quantidade, palavras do nome, [(cnae, setor)], pesos de porte MEI..Grande)
PERFIS = {
    "atacado_distribuicao": (
        18,
        ["Distribuidora", "Atacadista", "Comercial Atacadista"],
        [
            ("4639701", "Comércio atacadista de produtos alimentícios em geral"),
            ("4649499", "Comércio atacadista de artigos de uso doméstico"),
            ("4691500", "Comércio atacadista de mercadorias em geral"),
        ],
        [0, 1, 4, 4, 2],
    ),
    "industria": (
        15,
        ["Indústria", "Fábrica", "Industrial"],
        [
            ("1091102", "Fabricação de produtos de panificação"),
            ("2229399", "Fabricação de artefatos de material plástico"),
            ("1412601", "Confecção de peças do vestuário"),
        ],
        [0, 1, 3, 4, 2],
    ),
    "varejo_crediario": (
        15,
        ["Móveis", "Magazine", "Calçados"],
        [
            ("4754701", "Comércio varejista de móveis"),
            ("4753900", "Comércio varejista de eletrodomésticos"),
            ("4782201", "Comércio varejista de calçados"),
        ],
        [0, 2, 4, 3, 1],
    ),
    "varejo": (
        10,
        ["Supermercados", "Farma", "Empório"],
        [
            ("4711302", "Supermercados"),
            ("4771701", "Comércio varejista de produtos farmacêuticos"),
            ("4721102", "Padaria e confeitaria"),
        ],
        [1, 4, 3, 2, 1],
    ),
    "ecommerce": (
        15,
        ["Store", "Shop", "Loja Online"],
        [
            ("4781400", "Comércio varejista de artigos do vestuário"),
            ("4763602", "Comércio varejista de artigos esportivos"),
            ("4752100", "Comércio varejista de equipamentos de telefonia"),
        ],
        [0, 2, 4, 3, 1],
    ),
    "financeira_fintech": (
        14,
        ["Crédito", "Fintech", "Financeira"],
        [
            ("6436100", "Sociedades de crédito, financiamento e investimento"),
            ("6499999", "Outras atividades de serviços financeiros"),
        ],
        [0, 1, 3, 4, 2],
    ),
    "meios_pagamento": (
        8,
        ["Pay", "Pagamentos", "Wallet"],
        [("6619399", "Outras atividades auxiliares dos serviços financeiros")],
        [0, 1, 3, 3, 1],
    ),
    "educacao": (
        12,
        ["Colégio", "Faculdade", "Escola de Idiomas"],
        [("8513900", "Ensino fundamental"), ("8532500", "Educação superior"), ("8593700", "Ensino de idiomas")],
        [0, 2, 4, 3, 1],
    ),
    "saude": (
        10,
        ["Clínica", "Laboratório", "Odonto"],
        [
            ("8630503", "Atividade médica ambulatorial"),
            ("8640202", "Laboratórios clínicos"),
            ("8630504", "Atividade odontológica"),
        ],
        [0, 3, 4, 2, 1],
    ),
    "servicos_b2b": (
        12,
        ["Serviços", "Consultoria", "Facilities"],
        [
            ("8211300", "Serviços combinados de escritório e apoio administrativo"),
            ("7020400", "Atividades de consultoria em gestão empresarial"),
            ("8121400", "Limpeza em prédios e em domicílios"),
        ],
        [1, 3, 4, 2, 1],
    ),
    "locacao_imoveis": (
        7,
        ["Imóveis", "Locadora", "Administradora"],
        [
            ("6822600", "Gestão e administração da propriedade imobiliária"),
            ("7711000", "Locação de automóveis sem condutor"),
        ],
        [0, 2, 4, 2, 1],
    ),
    "tecnologia_saas": (
        6,
        ["Tech", "Software", "Sistemas"],
        [("6203100", "Desenvolvimento de programas de computador"), ("6311900", "Tratamento de dados e hospedagem")],
        [0, 2, 4, 2, 1],
    ),
    "telecom_energia": (
        5,
        ["Telecom", "Fibra", "Energia"],
        [("6190601", "Provedores de acesso às redes de comunicações"), ("3514000", "Distribuição de energia elétrica")],
        [0, 1, 3, 3, 2],
    ),
    "cobranca_recuperacao": (
        3,
        ["Cobranças", "Recuperadora", "Assessoria de Crédito"],
        [("8291100", "Atividades de cobranças e informações cadastrais")],
        [0, 2, 4, 2, 0],
    ),
}

# Uma frase de contexto por segmento, para o texto soar natural.
CONTEXTO = {
    "atacado_distribuicao": "Distribuidora que abastece mercados e lojas da região.",
    "industria": "Indústria que vende para revendedores e redes.",
    "varejo_crediario": "Rede de lojas de bairro com venda parcelada no carnê.",
    "varejo": "Comércio de bairro com clientela fiel.",
    "ecommerce": "Marca nascida no e-commerce, com loja virtual própria.",
    "financeira_fintech": "Fintech de crédito ao consumidor.",
    "meios_pagamento": "Empresa de pagamentos digitais.",
    "educacao": "Instituição de ensino privada.",
    "saude": "Rede de atendimento em saúde.",
    "servicos_b2b": "Prestadora de serviços para empresas.",
    "locacao_imoveis": "Empresa de locação com contratos mensais.",
    "tecnologia_saas": "Empresa de software vendido por assinatura.",
    "telecom_energia": "Provedor regional com milhares de assinantes.",
    "cobranca_recuperacao": "Assessoria de cobrança para varejo e serviços.",
}

RAIZES = [
    "Auri",
    "Belo",
    "Cora",
    "Dora",
    "Esta",
    "Flora",
    "Grana",
    "Ita",
    "Jaci",
    "Lumi",
    "Mira",
    "Nova",
    "Ori",
    "Pira",
    "Quina",
    "Rio",
    "Sola",
    "Tava",
    "Uba",
    "Vera",
    "Xana",
    "Zeni",
]
SUFIXOS = ["vale", "monte", "luz", "mar", "sul", "norte", "verde", "prata", "serra", "lago"]
CIDADES = [
    ("São Paulo", "SP"),
    ("Campinas", "SP"),
    ("Rio de Janeiro", "RJ"),
    ("Belo Horizonte", "MG"),
    ("Curitiba", "PR"),
    ("Porto Alegre", "RS"),
    ("Florianópolis", "SC"),
    ("Goiânia", "GO"),
    ("Brasília", "DF"),
    ("Salvador", "BA"),
    ("Recife", "PE"),
    ("Fortaleza", "CE"),
    ("Belém", "PA"),
    ("Manaus", "AM"),
    ("Vitória", "ES"),
    ("Campo Grande", "MS"),
]
NOMES = ["Lia", "Davi", "Iara", "Caio", "Nina", "Theo", "Maia", "Enzo", "Lara", "Raul", "Alice", "Igor"]
SOBRENOMES = ["Ficticio", "Exemplar", "Modelo", "Teste", "Demonstra", "Simulado"]
CARGOS = [
    "Diretor financeiro",
    "Gerente de crédito",
    "Gerente comercial",
    "Sócio",
    "Coordenador de risco",
    "Head de fraude",
    "Gerente de cobrança",
    "Analista financeiro",
]
ORIGENS_PESOS = [("site", 35), ("evento", 15), ("indicacao", 15), ("linkedin", 20), ("planilha", 15)]
LINHA_PARA_INTERESSE = {
    "credito_decisao": "Crédito",
    "monitoramento": "Crédito",
    "fraude": "Antifraude",
    "cobranca": "Cobrança",
    "prospeccao": "Prospecção",
}
FUNCIONARIOS = {"MEI": (1, 1), "ME": (2, 9), "EPP": (10, 49), "Média": (50, 249), "Grande": (250, 3000)}


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return "".join(c if c.isalnum() else "-" for c in texto).strip("-").replace("--", "-")


def _escolher_pesado(rng: random.Random, pares: list[tuple]) -> object:
    itens, pesos = zip(*pares, strict=True)
    return rng.choices(itens, weights=pesos, k=1)[0]


def _sinais_do_segmento(rng: random.Random, segmento: str, regras: dict, fraco: bool) -> list[str]:
    arestas = [(a["para"], a["peso"]) for a in regras["segmento_sinal"] if a["de"] == segmento]
    if fraco or not arestas:
        return [rng.choice(list(FRASE_SINAL))] if rng.random() < 0.4 else []
    quantos = rng.choice([1, 2, 2, 3, 3])
    escolhidos: list[str] = []
    while arestas and len(escolhidos) < quantos:
        sinal = _escolher_pesado(rng, arestas)
        escolhidos.append(sinal)
        arestas = [a for a in arestas if a[0] != sinal]
    return escolhidos


def _empresa(rng: random.Random, indice: int, segmento: str, regras: dict, nomes_usados: set[str]) -> dict:
    _, palavras, cnaes, pesos_porte = PERFIS[segmento]
    while True:
        raiz = rng.choice(RAIZES) + rng.choice(SUFIXOS)
        nome = f"{raiz} {rng.choice(palavras)}"
        if nome not in nomes_usados:
            nomes_usados.add(nome)
            break
    cnae, setor = rng.choice(cnaes)
    porte = rng.choices(features.PORTES, weights=pesos_porte, k=1)[0]
    lo, hi = FUNCIONARIOS[porte]
    cidade, uf = rng.choice(CIDADES)
    fraco = rng.random() < 0.15
    sinais = _sinais_do_segmento(rng, segmento, regras, fraco)

    frases = [CONTEXTO[segmento]] + [FRASE_SINAL[s] for s in sinais]
    if fraco or rng.random() < 0.3:
        frases.append(rng.choice(FRASES_NEUTRAS))
    simulados = {}
    for sinal in regras["sinais"]:
        chave = sinal.get("sinal_simulado")
        if chave:
            simulados[chave] = sinal["id"] in sinais and rng.random() < 0.8
    if simulados.get("tem_ecommerce"):
        simulados["volume_pedidos_online_mes"] = rng.randint(2, 80) * 1000

    arestas = [a for a in regras["sinal_solucao"] if a["de"] in sinais]
    interesse = "Não sei"
    if arestas and rng.random() < 0.7:
        melhor = max(arestas, key=lambda a: a["peso"])
        interesse = LINHA_PARA_INTERESSE.get(_linha_da_solucao(melhor["para"]), "Não sei")

    sorteio_lgpd = rng.random()
    base_legal = (
        "consentimento" if sorteio_lgpd < 0.82 else "legitimo_interesse" if sorteio_lgpd < 0.965 else "sem_base"
    )
    contato_nome = f"{rng.choice(NOMES)} {rng.choice(SOBRENOMES)}"
    dominio = f"{_slug(raiz)}.exemplo"
    return {
        "indice": indice,
        "cnpj": cnpj_util.completar(f"9{indice:07d}0001"[:12]),
        "razao_social": f"{nome} Ltda",
        "nome_fantasia": nome,
        "cnae": cnae,
        "setor": setor,
        "porte": porte,
        "funcionarios": rng.randint(lo, hi),
        "cidade": cidade,
        "uf": uf,
        "site": f"www.{dominio}",
        "descricao": " ".join(frases),
        "situacao_cadastral": "Ativa" if rng.random() < 0.95 else rng.choice(["Baixada", "Inapta"]),
        "interesse": interesse,
        "origem": _escolher_pesado(rng, ORIGENS_PESOS),
        "observacao": "",
        "sinais_simulados": simulados,
        "segmento_gerado": segmento,
        "contato": {
            "nome": contato_nome,
            "cargo": rng.choice(CARGOS),
            "email": f"{_slug(contato_nome).replace('-', '.')}@{dominio}",
            "telefone": f"(11) 9{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}",
        },
        "base_legal": base_legal,
        "consentiu": base_legal == "consentimento",
        "opt_out": rng.random() < 0.03,
        "base_ficticia": True,
    }


def _linha_da_solucao(solucao_id: str) -> str:
    import catalogo

    return catalogo.por_id()[solucao_id]["linha"]


def gerar_empresas(n: int | None = None, semente: int = SEMENTE) -> list[dict]:
    """Cerca de 150 empresas fictícias variadas, sempre as mesmas para a mesma semente."""
    import catalogo

    regras = catalogo.carregar_regras()
    rng = random.Random(semente)
    plano = [seg for seg, perfil in PERFIS.items() for _ in range(perfil[0])]
    rng.shuffle(plano)
    if n is not None:
        plano = (plano * (n // len(plano) + 1))[:n]
    usados: set[str] = set()
    return [_empresa(rng, i + 1, seg, regras, usados) for i, seg in enumerate(plano)]


# Efeitos usados para gerar o resultado histórico. São regras plausíveis com ruído.
_EFEITO_SEGMENTO = {
    "financeira_fintech": 0.5,
    "atacado_distribuicao": 0.4,
    "ecommerce": 0.4,
    "meios_pagamento": 0.3,
    "industria": 0.2,
    "varejo_crediario": 0.2,
    "educacao": 0.0,
    "saude": -0.1,
    "servicos_b2b": -0.1,
    "varejo": -0.3,
    "outros": -0.5,
}
_EFEITO_ORIGEM = {
    "indicacao": 0.6,
    "evento": 0.3,
    "site": 0.1,
    "linkedin": 0.0,
    "planilha": -0.4,
    "formulario": 0.1,
    "cnpj_lista": -0.2,
}
_EFEITO_PORTE = [-1.0, -0.4, 0.3, 0.5, 0.2]
MOTIVOS_PERDA = ["Sem orçamento", "Já é cliente de concorrente", "Sem fit", "Sem resposta"]


def gerar_historico(n: int = 500, semente: int = SEMENTE + 1) -> list[dict]:
    """Leads históricos com resultado (ganho ou perdido) para treinar a propensão.

    O resultado nasce de uma regra com ruído: mais sinais, interesse alinhado, origem por
    indicação e porte médio aumentam a chance de ganho.
    """
    import catalogo

    regras = catalogo.carregar_regras()
    rng = random.Random(semente)
    empresas = gerar_empresas(n, semente=semente)
    historico = []
    for emp in empresas:
        f = features.calcular(emp, regras)
        logit = (
            -3.8
            + 0.6 * f["n_sinais"]
            + 1.2 * f["interesse_alinhado"]
            + 0.6 * f["forca_segmento"]
            + _EFEITO_SEGMENTO.get(f["segmento"], 0.0)
            + _EFEITO_ORIGEM.get(f["origem"], 0.0)
            + _EFEITO_PORTE[f["porte_ordem"]]
            - 1.2 * (1 - f["empresa_ativa"])
            + rng.gauss(0, 0.6)
        )
        ganho = rng.random() < 1 / (1 + math.exp(-logit))
        candidatas = [a for a in regras["sinal_solucao"] if a["de"] in f["sinais"]]
        solucao = max(candidatas, key=lambda a: a["peso"])["para"] if candidatas else "prospeccao_qualificada"
        historico.append(
            {
                "features": {k: f[k] for k in features.FEATURES},
                "resultado": int(ganho),
                "motivo": None if ganho else rng.choice(MOTIVOS_PERDA),
                "solucao_id": solucao,
                "valor_mensal": round(rng.uniform(1.5, 25) * 1000, -2) if ganho else None,
                "dias_atras": rng.randint(15, 540),
            }
        )
    return historico
