"""Cenário de demonstração: um mês fictício de operação, para o Dashboard e os Indicadores terem vida.

Captura cerca de 100 empresas da base fictícia, trata todas com a análise local e espalha as datas
pelos últimos 30 dias. Depois simula o trabalho dos BDRs: primeiros contatos, BANT, reuniões,
propostas, ganhos e perdas (com rótulos de treino), correções da IA e alguns SLAs estourados.
Tudo marcado como base fictícia. As empresas restantes ficam livres para a captura ao vivo.
"""

from __future__ import annotations

import json
import random
from datetime import timedelta

from banco import repositorio
from banco.conexao import conectar
from nucleo import comercial, estados, tempo

from . import base_ficticia, ingestao

CHAVE = "cenario_demo_montado"
QUANTIDADE = 100
SEMENTE = 99
CANAL_POR_ORIGEM = {"site": "webhook_site", "planilha": "planilha", "linkedin": "formulario", "evento": "formulario",
                    "indicacao": "formulario"}  # fmt: skip


def montado() -> bool:
    return bool(repositorio.config(CHAVE))


def _deslocar(con, lead_id: int, base) -> None:
    """Reescreve as datas de um lead a partir de 'base' (captura no passado)."""
    hist = con.execute("SELECT id FROM etapas_historico WHERE lead_id=? ORDER BY id", (lead_id,)).fetchall()
    for i, h in enumerate(hist):
        con.execute("UPDATE etapas_historico SET registrado_em=? WHERE id=?",
                    (tempo.iso(base + timedelta(minutes=2 * i)), h["id"]))  # fmt: skip
    instante = tempo.iso(base)
    depois = tempo.iso(base + timedelta(minutes=3))
    con.execute("UPDATE leads SET criado_em=?, atualizado_em=? WHERE id=?", (instante, depois, lead_id))
    con.execute("UPDATE leads_brutos SET recebido_em=? WHERE lead_id=?", (instante, lead_id))
    con.execute("UPDATE consentimentos SET registrado_em=? WHERE lead_id=?", (instante, lead_id))
    con.execute("UPDATE contatos SET criado_em=? WHERE lead_id=?", (instante, lead_id))
    con.execute("UPDATE tratamentos SET iniciado_em=?, concluido_em=? WHERE lead_id=?", (instante, depois, lead_id))
    con.execute("UPDATE tratamento_etapas SET iniciado_em=? WHERE tratamento_id IN "
                "(SELECT id FROM tratamentos WHERE lead_id=?)", (depois, lead_id))  # fmt: skip
    con.execute("UPDATE eventos_ia SET ocorrido_em=? WHERE lead_id=?", (depois, lead_id))
    con.execute("UPDATE atribuicoes SET atribuido_em=? WHERE lead_id=?", (depois, lead_id))
    con.execute("UPDATE leads_features SET gerado_em=? WHERE lead_id=?", (depois, lead_id))
    linha = con.execute("SELECT classificacao FROM leads WHERE id=?", (lead_id,)).fetchone()
    sla = repositorio.config("sla_horas") or {}
    con.execute("UPDATE leads SET sla_limite=? WHERE id=? AND sla_limite IS NOT NULL",
                (tempo.iso(base + timedelta(hours=sla.get(linha["classificacao"], 24))), lead_id))  # fmt: skip
    passos = con.execute("SELECT id, dia FROM cadencia_passos WHERE lead_id=?", (lead_id,)).fetchall()
    for p in passos:
        con.execute("UPDATE cadencia_passos SET previsto_para=? WHERE id=?",
                    (tempo.iso(base + timedelta(days=p["dia"])), p["id"]))  # fmt: skip


def _atividade(con, lead_id, usuario_id, momento, tipo, resultado, anotacao="", retorno=None) -> None:
    con.execute(
        "INSERT INTO atividades (lead_id, usuario_id, registrada_em, tipo, resultado, anotacao, proxima_acao, "
        "retorno_em) VALUES (?,?,?,?,?,?,?,?)",
        (lead_id, usuario_id, tempo.iso(momento), tipo, resultado, anotacao, "", tempo.iso(retorno) if retorno else None),
    )  # fmt: skip
    if tipo in comercial.TIPOS_CONTATO:
        passo = con.execute("SELECT id FROM cadencia_passos WHERE lead_id=? AND canal=? AND feito_em IS NULL "
                            "ORDER BY dia LIMIT 1", (lead_id, tipo)).fetchone()  # fmt: skip
        if passo:
            con.execute("UPDATE cadencia_passos SET feito_em=? WHERE id=?", (tempo.iso(momento), passo["id"]))


def montar(ator: str = "cenario_demo") -> dict:
    """Monta o cenário uma única vez. Retorna um resumo."""
    from ia import orquestrador

    if montado():
        return {"ja_montado": True}
    rng = random.Random(SEMENTE)
    empresas = ingestao.ficticias_disponiveis()[:QUANTIDADE]
    por_canal: dict[str, list[dict]] = {}
    for e in empresas:
        por_canal.setdefault(CANAL_POR_ORIGEM.get(e["origem"], "formulario"), []).append(ingestao.registro_ficticio(e))
    ids: list[int] = []
    for canal, registros in por_canal.items():
        ids += ingestao.receber(registros, canal, ator, ficticio=True).criados
    orquestrador.tratar(ids, ator, usar_llm=False)

    agora = tempo.agora()
    bdrs = {u["id"]: u for u in repositorio.usuarios("bdr")}
    execs = repositorio.usuarios("executivo")
    resumo = {"leads": len(ids), "contatados": 0, "reunioes": 0, "ganhos": 0, "perdidos": 0}
    with conectar() as con:
        # Distribui as datas: mais leads recentes, alguns antigos.
        datas = {i: agora - timedelta(days=rng.choice([1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 18, 21, 25, 28]),
                                       hours=rng.randint(0, 10)) for i in ids}  # fmt: skip
        for lead_id, base in datas.items():
            _deslocar(con, lead_id, base)

        leads = con.execute(
            f"SELECT l.id, l.etapa, l.classificacao, l.responsavel_id, l.solucao_principal, t.propensao FROM leads l "
            f"JOIN tratamentos t ON t.lead_id=l.id WHERE l.id IN ({','.join('?' * len(ids))})", ids,
        ).fetchall()  # fmt: skip
        for lead in leads:
            if lead["etapa"] != estados.FILA_BDR or lead["responsavel_id"] not in bdrs:
                continue
            base = datas[lead["id"]]
            dias = (agora - base).days
            if dias < 2:
                continue  # leads recentes ficam na fila para o BDR trabalhar na demonstração
            quente = lead["classificacao"] == "Quente"
            if rng.random() > (0.88 if quente else 0.7):
                continue  # sem contato: SLA estourado (gera alerta no Dashboard)
            bdr = lead["responsavel_id"]
            primeiro = base + timedelta(hours=rng.uniform(0.5, 6) if quente else rng.uniform(3, 52))
            if primeiro > agora:
                continue
            ator_bdr = bdrs[bdr]["login"]
            lead_id = lead["id"]
            _atividade(con, lead_id, bdr, primeiro, "Ligação", rng.choice(["Falou com o decisor", "Pediu retorno",
                                                                             "Interessado"]))  # fmt: skip
            con.execute("UPDATE leads SET primeiro_contato_em=? WHERE id=?", (tempo.iso(primeiro), lead_id))
            estados.mudar(
                con, lead_id, estados.EM_CONTATO, ator_bdr, detalhe="Primeira ligação", momento=tempo.iso(primeiro)
            )
            resumo["contatados"] += 1
            if rng.random() < 0.7:
                concorda = rng.random() < 0.82
                con.execute(
                    "INSERT INTO correcoes_ia (lead_id, usuario_id, campo, valor_ia, valor_correto, concorda, motivo, "
                    "registrada_em) VALUES (?,?,?,?,?,?,?,?)",
                    (lead_id, bdr, "solucao", lead["solucao_principal"],
                     lead["solucao_principal"] if concorda else "negativacao", int(concorda),
                     "Sugestão confere com a conversa." if concorda else "Cliente falou mais de cobrança.",
                     tempo.iso(primeiro + timedelta(minutes=5))),
                )  # fmt: skip
            chance = min(0.9, 0.25 + (lead["propensao"] or 0.3))
            momento = primeiro
            if rng.random() > chance or dias < 4:
                if rng.random() < 0.3 and dias >= 6:
                    momento += timedelta(days=rng.randint(2, 5))
                    _atividade(con, lead_id, bdr, momento, "WhatsApp", "Sem resposta")
                    estados.mudar(
                        con, lead_id, estados.PERDIDO, ator_bdr, motivo="Sem resposta", momento=tempo.iso(momento)
                    )
                    comercial.registrar_rotulo(
                        con, lead_id, False, "Sem resposta", lead["solucao_principal"], tempo.iso(momento)
                    )
                    resumo["perdidos"] += 1
                continue
            momento += timedelta(days=rng.randint(1, 3))
            con.execute(
                "INSERT INTO bant (lead_id, orcamento, autoridade, necessidade, prazo, atualizado_em, usuario_id) "
                "VALUES (?,?,?,?,?,?,?)",
                (lead_id, "Tem verba no trimestre", "Diretor financeiro", "Reduzir risco e inadimplência",
                 "Próximos 60 dias", tempo.iso(momento), bdr),
            )  # fmt: skip
            estados.mudar(
                con, lead_id, estados.QUALIFICADO, ator_bdr, detalhe="BANT preenchido", momento=tempo.iso(momento)
            )
            executivo = rng.choice(execs)["id"] if execs else None
            reuniao = momento + timedelta(days=rng.randint(1, 4))
            estados.mudar(
                con, lead_id, estados.REUNIAO, ator_bdr, detalhe="Reunião agendada", momento=tempo.iso(momento)
            )
            _atividade(con, lead_id, bdr, momento, "Reunião", "Reunião marcada", retorno=reuniao)
            valor = round(rng.uniform(1.5, 25) * 1000, -2)
            con.execute(
                "INSERT INTO oportunidades (lead_id, solucoes, valor_mensal, executivo_id, previsao_fechamento, "
                "resumo_passagem, criada_em, atualizada_em) VALUES (?,?,?,?,?,?,?,?)",
                (lead_id, json.dumps([lead["solucao_principal"]]), valor, executivo,
                 (reuniao + timedelta(days=20)).date().isoformat(),
                 "Resumo gerado no cenário de demonstração.", tempo.iso(momento), tempo.iso(momento)),
            )  # fmt: skip
            con.execute(
                "UPDATE leads SET executivo_id=?, retorno_em=? WHERE id=?", (executivo, tempo.iso(reuniao), lead_id)
            )
            resumo["reunioes"] += 1
            if reuniao > agora or dias < 9:
                continue
            momento = reuniao + timedelta(days=rng.randint(1, 3))
            estados.mudar(
                con, lead_id, estados.PROPOSTA, "executivo", detalhe="Proposta enviada", momento=tempo.iso(momento)
            )
            if dias < 14:
                continue
            momento += timedelta(days=rng.randint(2, 6))
            if momento > agora:
                continue
            ganhou = rng.random() < min(0.85, 0.3 + (lead["propensao"] or 0.3))
            if ganhou:
                estados.mudar(
                    con, lead_id, estados.GANHO, "executivo", detalhe="Contrato assinado", momento=tempo.iso(momento)
                )
                resumo["ganhos"] += 1
            else:
                motivo = rng.choice(["Sem orçamento", "Já é cliente de concorrente", "Sem fit"])
                estados.mudar(con, lead_id, estados.PERDIDO, "executivo", motivo=motivo, momento=tempo.iso(momento))
                resumo["perdidos"] += 1
            comercial.registrar_rotulo(con, lead_id, ganhou, None if ganhou else motivo, lead["solucao_principal"],
                                       tempo.iso(momento))  # fmt: skip
        repositorio.salvar_config(CHAVE, True, ator, "cenário de demonstração montado", con=con)
        repositorio.auditar(con, ator, "cenario_demo", "leads", None, resumo)
    return resumo


def reiniciar(ator: str) -> dict:
    """Apaga o banco de demonstração e remonta do zero. Só existe no modo simulado."""
    from nucleo import config

    if not config.simulado():
        raise PermissionError("A base só pode ser reiniciada no modo simulado.")
    caminho = config.caminho_banco()
    from banco import conexao, semente

    conexao._migrados.discard(str(caminho.resolve()))
    caminho.unlink(missing_ok=True)
    semente.garantir_base(True, config.usuarios_secrets())
    return montar(ator)


__all__ = ["base_ficticia", "montado", "montar", "reiniciar"]
