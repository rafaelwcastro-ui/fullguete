"""Orquestrador do tratamento: executa os sete agentes em ordem e grava cada etapa.

Ordem: Higienização → Enriquecimento → Risco e conformidade → Qualificação → Recomendador →
Redator → Supervisor. Qualificação, Recomendador e Redator compartilham uma chamada ao LLM
por lote de até 15 leads (cada um com sua parte do prompt e do JSON). Sem chave, ou se o LLM
falhar duas vezes, entra o plano B local.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import Counter
from collections.abc import Callable

import catalogo
import prompts
from banco import repositorio
from banco.conexao import conectar
from dados import ingestao
from nucleo import comercial, config, estados, tempo

from . import agentes, esquemas, grafo, nota, observabilidade, plano_b, propensao, provedor, rag, score_local, segmentos
from .agentes import Contexto

TRATAVEIS = {estados.CAPTURADO, estados.RETIDO, estados.REVISAO, estados.NUTRICAO, estados.DESCARTADO,
             estados.FILA_BDR}  # fmt: skip
Progresso = Callable[[str, float], None]


def _carregar(con, lead_ids: list[int]) -> list[Contexto]:
    marcadores = ",".join("?" * len(lead_ids))
    leads = {r["id"]: dict(r) for r in con.execute(f"SELECT * FROM leads WHERE id IN ({marcadores})", lead_ids)}
    contatos = {r["lead_id"]: dict(r) for r in con.execute(
        f"SELECT * FROM contatos WHERE lead_id IN ({marcadores}) ORDER BY id", lead_ids)}  # fmt: skip
    consent = {r["lead_id"]: dict(r) for r in con.execute(
        f"SELECT * FROM consentimentos WHERE lead_id IN ({marcadores}) ORDER BY id", lead_ids)}  # fmt: skip
    return [Contexto(leads[i], contatos.get(i), consent.get(i)) for i in lead_ids if i in leads]


def _chave_cache(ctx: Contexto, payload: dict, icp_id: int) -> str:
    base = json.dumps({"id_empresa": ctx.lead.get("cnpj") or ctx.lead["chave_dedup"], "payload": payload,
                       "prompt": prompts.VERSAO_ATIVA, "icp": icp_id, "modelo": provedor.modelo()},
                      sort_keys=True, ensure_ascii=False)  # fmt: skip
    return hashlib.sha256(base.encode()).hexdigest()


def _llm_lote(lote: str, grupo: list[Contexto], icp: dict) -> None:
    """Chama o LLM para um grupo de leads. Preenche ctx.resultado; em falha, deixa None para o plano B."""
    payloads = {str(c.lead["id"]): agentes.payload_llm(c, rag.contexto_candidatas(c.candidatas)) for c in grupo}
    pendentes = []
    with conectar() as con:
        for ctx in grupo:
            chave = _chave_cache(ctx, payloads[str(ctx.lead["id"])], icp["id"])
            linha = con.execute("SELECT resposta FROM cache_ia WHERE chave=?", (chave,)).fetchone()
            if linha:
                ctx.resultado = esquemas.ResultadoIA.model_validate_json(linha["resposta"])
                ctx.motor = "gemini"
                observabilidade.registrar("qualificacao+recomendador+redator", provedor.PROVEDOR,
                                          modelo=provedor.modelo(), versao_prompt=prompts.VERSAO_ATIVA,
                                          latencia_ms=0, cache=True, lote=lote, lead_id=ctx.lead["id"])  # fmt: skip
            else:
                pendentes.append((ctx, chave))
    if not pendentes:
        return

    candidatas = {str(c.lead["id"]): {x["solucao_id"] for x in c.candidatas} for c, _ in pendentes}
    usuario = prompts.montar_usuario(icp, [payloads[str(c.lead["id"])] for c, _ in pendentes])
    sistema = prompts.sistema()
    tentativa_msg = ""
    resultados = None
    t_in = t_out = 0
    latencia = 0
    for tentativa in (1, 2):
        try:
            resposta = provedor.chamar(
                sistema, usuario + tentativa_msg, esquema=esquemas.esquema_json(), temperatura=prompts.TEMPERATURA,
                agente="qualificacao+recomendador+redator", versao_prompt=prompts.VERSAO_ATIVA, lote=lote,
            )  # fmt: skip
        except provedor.ErroIA as erro:
            erro_txt = str(erro)
            break
        t_in += resposta.tokens_entrada
        latencia += resposta.latencia_ms
        t_out += resposta.tokens_saida
        try:
            resultados = esquemas.validar_lote(resposta.texto, candidatas)
            break
        except (esquemas.ValidationError, esquemas.ErroValidacao, ValueError) as erro:
            erro_txt = f"JSON inválido na tentativa {tentativa}: {str(erro)[:300]}"
            tentativa_msg = (
                f"\n\nSua resposta anterior falhou na validação: {str(erro)[:600]}\n"
                "Corrija e responda de novo apenas com o JSON completo, usando só ids das candidatas."
            )
    if resultados is None:
        observabilidade.registrar("qualificacao+recomendador+redator", "local", versao_prompt=prompts.VERSAO_ATIVA,
                                  plano_b=True, erro=erro_txt, lote=lote)  # fmt: skip
        for ctx, _ in pendentes:
            ctx.plano_b = True
        return
    custo_lote = observabilidade.custo_estimado(t_in, t_out)
    with conectar() as con:
        for ctx, chave in pendentes:
            ctx.resultado = resultados[str(ctx.lead["id"])]
            ctx.motor = "gemini"
            ctx.custo = custo_lote / len(pendentes)
            ctx.llm_ms = latencia // len(pendentes)
            con.execute(
                "INSERT INTO cache_ia (chave, criado_em, resposta) VALUES (?,?,?) ON CONFLICT(chave) DO NOTHING",
                (chave, tempo.iso(), ctx.resultado.model_dump_json()),
            )


def tratar(lead_ids: list[int], ator: str, usar_llm: bool | None = None,
           progresso: Progresso | None = None) -> dict:  # fmt: skip
    """Trata um lote de leads do começo ao destino. Retorna o resumo do lote."""
    avisar = progresso or (lambda _etapa, _p: None)
    lote = f"lote-{tempo.agora().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}"
    usar_llm = provedor.disponivel() if usar_llm is None else (usar_llm and provedor.disponivel())
    inicio_lote = time.perf_counter()
    icp = repositorio.icp_ativo()
    pesos = repositorio.config("pesos_nota")
    limites = repositorio.config("limites_classificacao")
    conf_min = float(repositorio.config("confianca_minima_fila"))
    sla_horas = repositorio.config("sla_horas")
    tamanho_lote = int(repositorio.config("tamanho_lote_ia") or 15)

    # Abre o tratamento e passa os leads para "Em tratamento".
    with conectar() as con:
        validos = [r["id"] for r in con.execute(
            f"SELECT id, etapa FROM leads WHERE id IN ({','.join('?' * len(lead_ids))})", lead_ids)
            if r["etapa"] in TRATAVEIS]  # fmt: skip
        if not validos:
            return {"lote": lote, "total": 0, "ignorados": len(lead_ids), "destinos": {}, "etapas": []}
        for lead_id in validos:
            estados.mudar(con, lead_id, estados.EM_TRATAMENTO, ator)
        contextos = _carregar(con, validos)
        for ctx in contextos:
            cur = con.execute(
                "INSERT INTO tratamentos (lead_id, lote, iniciado_em, icp_versao_id, motor) VALUES (?,?,?,?,?)",
                (ctx.lead["id"], lote, tempo.iso(), icp["id"], "gemini" if usar_llm else "local"),
            )
            ctx.tratamento_id = int(cur.lastrowid)

    total = len(contextos)
    token = config.token_cnpjws()
    ficticios = ingestao.cnpjs_ficticios()

    # 1 a 3: por lead.
    for i, ctx in enumerate(contextos):
        avisar("Higienização, enriquecimento e risco", (i + 1) / total * 0.4)
        agentes.higienizacao(ctx)
        agentes.enriquecimento(ctx, token, ficticios)
        agentes.risco(ctx)
    ativos = [c for c in contextos if not c.bloqueio]

    # 4. Qualificação (parte local): aderência local, propensão e segmento K-Means.
    avisar("Qualificação: nota local, propensão e segmento", 0.45)
    t = time.perf_counter()
    perfis: dict = {}
    if ativos:
        notas_locais = score_local.aderencia([{**c.lead, "segmento": c.feats["segmento"]} for c in ativos], icp)
        probs, versao_modelo = propensao.prever([c.feats for c in ativos])
        clusters = segmentos.prever([c.feats for c in ativos])
        perfis = segmentos.perfis()
        g = grafo.grafo_atual(perfis)
        for ctx, nl, p, cl in zip(ativos, notas_locais, probs, clusters, strict=True):
            ctx.nota_local, ctx.propensao, ctx.cluster = nl, p, cl
            # 5. Recomendador: o grafo recupera as candidatas (RAG em grafo).
            ctx.candidatas = grafo.candidatas(ctx.feats["segmento"], ctx.feats["sinais"], ctx.lead.get("interesse"),
                                              cl, k=5, g=g)  # fmt: skip
            if not ctx.candidatas:
                ctx.candidatas = [{"solucao_id": "prospeccao_qualificada", "pontos": 0.1, "caminhos": [{
                    "tipo": "padrao", "segmento": ctx.segmento_nome, "sinal": "sem sinais claros",
                    "solucao": catalogo.nome("prospeccao_qualificada"),
                    "frase": "sem sinais claros → precisa entender melhor o cliente → Prospecção Qualificada",
                    "forca": 0.1}]}]  # fmt: skip
    else:
        versao_modelo = ""
    ms_local = int((time.perf_counter() - t) * 1000 / max(len(ativos), 1))

    # 4 a 6 com LLM, em lotes.
    if usar_llm and ativos:
        grupos = [ativos[i : i + tamanho_lote] for i in range(0, len(ativos), tamanho_lote)]
        for n, grupo in enumerate(grupos, start=1):
            avisar(f"IA generativa: lote {n} de {len(grupos)}", 0.5 + 0.35 * n / len(grupos))
            _llm_lote(lote, grupo, icp)

    # Plano B onde não houve resultado do LLM.
    for ctx in ativos:
        if ctx.resultado is None:
            ctx.resultado = plano_b.montar(ctx.lead, ctx.candidatas, ctx.nota_local, ctx.sinais_nomes, ctx.dores,
                                           ctx.segmento_nome, ctx.riscos)  # fmt: skip
            ctx.motor = "local"
            if usar_llm:
                ctx.plano_b = True
            observabilidade.registrar("qualificacao+recomendador+redator", "local", latencia_ms=ms_local,
                                      plano_b=ctx.plano_b, lote=lote, lead_id=ctx.lead["id"])  # fmt: skip
        r = ctx.resultado
        detalhe_motor = "LLM" if ctx.motor == "gemini" else ("plano B local" if ctx.plano_b else "análise local")
        ctx.registrar("qualificacao", "ok",
                      f"Aderência {r.nota_aderencia} ({detalhe_motor}), referência local {ctx.nota_local['nota']}, "
                      f"propensão {ctx.propensao:.0%}, {perfis[ctx.cluster]['nome'] if ctx.cluster in perfis else ''}.",
                      ms_local + ctx.llm_ms // 3)  # fmt: skip
        ctx.registrar("recomendador", "ok",
                      f"{len(ctx.candidatas)} candidatas do grafo; escolhida {catalogo.nome(r.solucao_principal.id)} "
                      f"com confiança {r.solucao_principal.confianca:.2f}.", ctx.llm_ms // 3)  # fmt: skip
        ctx.registrar(
            "redator", "ok", "Perguntas, roteiro por canal e objeções gerados como rascunho.", ctx.llm_ms // 3
        )

    # 7. Supervisor: combina, classifica, decide o destino e distribui.
    avisar("Supervisor: nota final, destino e distribuição", 0.95)
    destinos: Counter = Counter()
    with conectar() as con:
        for ctx in contextos:
            t = time.perf_counter()
            lead_id = ctx.lead["id"]
            if ctx.alteracoes:
                campos = ", ".join(f"{k}=?" for k in ctx.alteracoes)
                con.execute(f"UPDATE leads SET {campos} WHERE id=?", [*ctx.alteracoes.values(), lead_id])
            if ctx.feats:
                con.execute(
                    "INSERT INTO leads_features (lead_id, gerado_em, features, cluster) VALUES (?,?,?,?) "
                    "ON CONFLICT(lead_id) DO UPDATE SET gerado_em=excluded.gerado_em, features=excluded.features, "
                    "cluster=excluded.cluster",
                    (lead_id, tempo.iso(), json.dumps(ctx.feats, ensure_ascii=False), ctx.cluster),
                )
            estados.mudar(con, lead_id, estados.TRATADO, "orquestrador")
            if ctx.bloqueio:
                etapa, explicacao = ctx.bloqueio
                estados.mudar(con, lead_id, etapa, "agente_risco", detalhe=explicacao)
                con.execute(
                    "UPDATE tratamentos SET concluido_em=?, destino=?, decomposicao=?, tempo_ms=? WHERE id=?",
                    (tempo.iso(), etapa, json.dumps({"bloqueio": explicacao}, ensure_ascii=False),
                     int((time.perf_counter() - ctx.inicio) * 1000), ctx.tratamento_id),
                )  # fmt: skip
                ctx.registrar("supervisor", "ok", f"Destino: {etapa}. {explicacao}", 0)
                destinos[etapa] += 1
            else:
                r = ctx.resultado
                conf = r.solucao_principal.confianca
                final, partes = nota.combinar(r.nota_aderencia, ctx.propensao * 100, conf, pesos)
                classe = nota.classificar(final, limites)
                precisa = r.precisa_revisao_humana or bool(ctx.riscos)
                etapa, motivo, explicacao = nota.destino(classe, conf, conf_min, precisa, final)
                etapa, motivo, explicacao = nota.preservar_cnpj_publico(
                    etapa,
                    motivo,
                    explicacao,
                    origem=ctx.lead["origem"],
                    base_ficticia=bool(ctx.lead["base_ficticia"]),
                    opt_out=bool(ctx.lead["opt_out"]),
                    nota_final=final,
                    motor=ctx.motor,
                )
                decomposicao = {
                    "pesos": pesos, "partes": partes, "nota_final": final, "classificacao": classe,
                    "aderencia": r.nota_aderencia, "propensao": round(ctx.propensao * 100, 1), "confianca": conf,
                    "aderencia_local": ctx.nota_local, "explicacao_destino": explicacao,
                    "segmento": ctx.segmento_nome, "cluster": ctx.cluster,
                    "cluster_nome": perfis.get(ctx.cluster, {}).get("nome") if ctx.cluster is not None else None,
                    "sinais": ctx.sinais_nomes, "problemas": ctx.problemas, "riscos": ctx.riscos,
                }  # fmt: skip
                con.execute(
                    """UPDATE tratamentos SET concluido_em=?, motor=?, modelo=?, versao_prompt=?, modelo_propensao=?,
                           nota_aderencia=?, propensao=?, confianca=?, nota_final=?, classificacao=?, destino=?,
                           decomposicao=?, resultado=?, plano_b=?, tempo_ms=?, custo_estimado=? WHERE id=?""",
                    (tempo.iso(), ctx.motor, provedor.modelo() if ctx.motor == "gemini" else "score_local",
                     prompts.VERSAO_ATIVA if ctx.motor == "gemini" else "plano_b_v1", versao_modelo,
                     r.nota_aderencia, round(ctx.propensao, 4), conf, final, classe, etapa,
                     json.dumps(decomposicao, ensure_ascii=False), r.model_dump_json(), int(ctx.plano_b),
                     int((time.perf_counter() - ctx.inicio) * 1000), round(ctx.custo, 6), ctx.tratamento_id),
                )  # fmt: skip
                caminhos = {c["solucao_id"]: c["caminhos"] for c in ctx.candidatas}
                pontos = {c["solucao_id"]: c["pontos"] for c in ctx.candidatas}
                con.execute(
                    "INSERT INTO recomendacoes (tratamento_id, lead_id, solucao_id, tipo, motivo, confianca, "
                    "caminho_grafo) VALUES (?,?,?,?,?,?,?)",
                    (ctx.tratamento_id, lead_id, r.solucao_principal.id, "principal", r.solucao_principal.motivo, conf,
                     json.dumps({"caminhos": caminhos.get(r.solucao_principal.id, []),
                                 "pontos": pontos.get(r.solucao_principal.id),
                                 "subgrafo": grafo.subgrafo(ctx.candidatas)}, ensure_ascii=False)),
                )  # fmt: skip
                for comp in r.solucoes_complementares:
                    con.execute(
                        "INSERT INTO recomendacoes (tratamento_id, lead_id, solucao_id, tipo, motivo, caminho_grafo) "
                        "VALUES (?,?,?,?,?,?)",
                        (ctx.tratamento_id, lead_id, comp.id, "complementar", comp.motivo,
                         json.dumps({"caminhos": caminhos.get(comp.id, [])}, ensure_ascii=False)),
                    )  # fmt: skip
                sla = tempo.daqui(horas=sla_horas.get(classe, 48)) if etapa == estados.FILA_BDR else None
                con.execute(
                    "UPDATE leads SET nota_final=?, classificacao=?, solucao_principal=?, sla_limite=? WHERE id=?",
                    (final, classe, r.solucao_principal.id, sla, lead_id),
                )
                estados.mudar(con, lead_id, etapa, "agente_supervisor", motivo=motivo, detalhe=explicacao)
                if etapa == estados.FILA_BDR:
                    bdr = ctx.lead.get("responsavel_id") or comercial.escolher_bdr(con)
                    if bdr:
                        comercial.atribuir(con, lead_id, bdr, "agente_supervisor", "Menor fila entre os BDRs")
                        from nucleo import lgpd

                        if lgpd.base_para_contato(con, lead_id):
                            comercial.criar_cadencia(con, lead_id)
                repositorio.auditar(con, "agente_supervisor", "decisao_ia", "leads", lead_id,
                                    {"nota_final": final, "classificacao": classe, "destino": etapa,
                                     "solucao": r.solucao_principal.id, "motor": ctx.motor,
                                     "plano_b": ctx.plano_b})  # fmt: skip
                ctx.registrar("supervisor", "ok",
                              f"Nota {final:.0f} ({classe}). {explicacao}", int((time.perf_counter() - t) * 1000))  # fmt: skip
                destinos[etapa] += 1
            for ordem, etapa_reg in enumerate(ctx.etapas, start=1):
                con.execute(
                    "INSERT INTO tratamento_etapas (tratamento_id, lote, ordem, agente, status, iniciado_em, tempo_ms, "
                    "detalhe) VALUES (?,?,?,?,?,?,?,?)",
                    (ctx.tratamento_id, lote, ordem, etapa_reg["agente"], etapa_reg["status"], tempo.iso(),
                     etapa_reg["tempo_ms"], etapa_reg["detalhe"]),
                )  # fmt: skip
        con.execute("UPDATE leads_brutos SET status='Tratado' WHERE lead_id IN "
                    f"({','.join('?' * len(validos))}) AND status!='Rejeitado'", validos)  # fmt: skip
    avisar("Concluído", 1.0)
    return {
        "lote": lote,
        "total": total,
        "ignorados": len(lead_ids) - total,
        "destinos": dict(destinos),
        "motor": "gemini" if usar_llm else "local",
        "planos_b": sum(c.plano_b for c in contextos),
        "tempo_s": round(time.perf_counter() - inicio_lote, 1),
    }


def etapas_do_lote(lote: str) -> list[dict]:
    """Contadores e tempo médio por agente, para a linha de progresso do lote."""
    with conectar() as con:
        linhas = con.execute(
            "SELECT agente, status, COUNT(*) n, AVG(tempo_ms) ms FROM tratamento_etapas WHERE lote=? "
            "GROUP BY agente, status", (lote,),
        ).fetchall()  # fmt: skip
    por_agente: dict[str, dict] = {}
    for r in linhas:
        item = por_agente.setdefault(r["agente"], {"agente": agentes.NOME_AGENTE.get(r["agente"], r["agente"]),
                                                    "total": 0, "status": {}, "ms": 0.0})  # fmt: skip
        item["total"] += r["n"]
        item["status"][r["status"]] = r["n"]
        item["ms"] = max(item["ms"], float(r["ms"] or 0))
    return [por_agente[a] for a, _ in agentes.AGENTES if a in por_agente]
