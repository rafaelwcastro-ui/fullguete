"""Histórico de pesquisas de CNPJs, tags e vínculo permanente com os leads.

As campanhas guardam apenas campos cadastrais normalizados, nunca a chave de API,
cursor da API, informações de sócios ou outros dados pessoais da resposta bruta.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass

import pandas as pd

from banco.conexao import conectar
from nucleo import tempo


@dataclass
class Busca:
    id: int
    tag: str
    provedor: str
    segmento: str
    cidade: str
    uf: str
    ano: int
    mes: int
    cnaes: str
    filtros: dict
    empresas: list[dict]
    total_fonte: int


def _slug(valor: str) -> str:
    sem_acentos = "".join(c for c in unicodedata.normalize("NFKD", valor.lower()) if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", sem_acentos)).strip("-")[:64]


def _tag(con, segmento: str, cidade: str, ano: int, mes: int, personalizada: str = "") -> str:
    base = _slug(personalizada) if personalizada.strip() else _slug(f"{segmento}-{cidade}-{ano:04d}{mes:02d}")
    base = base or f"busca-{ano:04d}{mes:02d}"
    indice = 1
    while True:
        tag = f"#{base}-{indice:02d}"
        if con.execute("SELECT 1 FROM buscas_prospeccao WHERE tag=?", (tag,)).fetchone() is None:
            return tag
        indice += 1


def _sanitizar(registros: list[dict]) -> list[dict]:
    """Whitelist de atributos públicos B2B; guarda apenas o necessário para reabrir a pesquisa."""
    campos = (
        "cnpj",
        "razao_social",
        "nome_fantasia",
        "cidade",
        "uf",
        "cnae",
        "setor",
        "porte",
        "descricao",
        "data_abertura",
        "situacao_cadastral",
        "origem",
    )
    empresas = {}
    for original in registros:
        if not isinstance(original, dict):
            continue
        cnpj = re.sub(r"\D", "", str(original.get("cnpj") or ""))
        if len(cnpj) != 14:
            continue
        empresas[cnpj] = {chave: str(original.get(chave) or "")[:180] for chave in campos}
        empresas[cnpj]["base_legal"] = "sem_base"
        empresas[cnpj]["consentimento"] = ""
    return list(empresas.values())


def registrar(
    provedor: str,
    segmento: str,
    cidade: str,
    uf: str,
    ano: int,
    mes: int,
    cnaes: str,
    filtros: dict,
    empresas: list[dict],
    total_fonte: int,
    ator: str,
    tag_preferida: str = "",
) -> Busca:
    """Cada consulta bem-sucedida gera uma nova campanha. Salva a amostra recuperada."""
    normalizadas = _sanitizar(empresas)
    agora = tempo.iso()
    # Somente os critérios de pesquisa são mantidos. Tokens de paginação são eliminados.
    permitidos = {
        "limit",
        "address.state.in",
        "address.municipality.in",
        "status.id.in",
        "founded.gte",
        "founded.lte",
        "mainActivity.id.in",
    }
    filtros_salvos = {k: v for k, v in filtros.items() if k in permitidos}
    with conectar() as con:
        tag = _tag(con, segmento, cidade, ano, mes, tag_preferida)
        cur = con.execute(
            """INSERT INTO buscas_prospeccao
               (tag, provedor, segmento, cidade, uf, ano, mes, cnaes, filtros_json,
                resultados_json, total_fonte, criada_em, atualizada_em, criada_por)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                tag,
                provedor,
                segmento,
                cidade,
                uf,
                ano,
                mes,
                cnaes,
                json.dumps(filtros_salvos, ensure_ascii=False),
                json.dumps(normalizadas, ensure_ascii=False),
                int(total_fonte),
                agora,
                agora,
                ator,
            ),
        )
        identificador = int(cur.lastrowid)
    return Busca(
        identificador,
        tag,
        provedor,
        segmento,
        cidade,
        uf,
        ano,
        mes,
        cnaes,
        filtros_salvos,
        normalizadas,
        int(total_fonte),
    )


def carregar(busca_id: int) -> Busca | None:
    with conectar() as con:
        r = con.execute("SELECT * FROM buscas_prospeccao WHERE id=?", (busca_id,)).fetchone()
        if r is None:
            return None
        return Busca(
            r["id"],
            r["tag"],
            r["provedor"],
            r["segmento"],
            r["cidade"],
            r["uf"],
            r["ano"],
            r["mes"],
            r["cnaes"],
            json.loads(r["filtros_json"]),
            json.loads(r["resultados_json"]),
            r["total_fonte"],
        )


def acrescentar(busca_id: int, empresas: list[dict], total_fonte: int) -> Busca:
    """Agrega páginas sem apagar empresas importadas e sem gravar os tokens do provedor."""
    with conectar() as con:
        r = con.execute("SELECT resultados_json FROM buscas_prospeccao WHERE id=?", (busca_id,)).fetchone()
        if r is None:
            raise ValueError("Pesquisa salva não encontrada.")
        anteriores = json.loads(r["resultados_json"])
        por_cnpj = {r["cnpj"]: r for r in anteriores}
        por_cnpj.update({r["cnpj"]: r for r in _sanitizar(empresas)})
        con.execute(
            "UPDATE buscas_prospeccao SET resultados_json=?, total_fonte=?, atualizada_em=? WHERE id=?",
            (json.dumps(list(por_cnpj.values()), ensure_ascii=False), int(total_fonte), tempo.iso(), busca_id),
        )
    return carregar(busca_id)


def importar(busca_id: int, cnpjs: list[str], ator: str, *, ficticio: bool = False):
    """Importa com atomicidade e associa também registros já existentes (deduplicados)."""
    from dados import ingestao

    busca = carregar(busca_id)
    if busca is None:
        raise ValueError("Pesquisa não encontrada.")
    selecionados = set(cnpjs)
    registros = [r for r in busca.empresas if r["cnpj"] in selecionados]
    if len(registros) != len(selecionados):
        raise ValueError("Um ou mais CNPJs não pertencem à pesquisa salva.")
    if not registros:
        raise ValueError("Selecione pelo menos uma empresa.")
    with conectar() as con:
        resultado = ingestao.receber(registros, busca.provedor, ator, ficticio=ficticio, con=con)
        for registro in registros:
            # A própria ingestão garante deduplicação por CNPJ.
            linha = con.execute("SELECT id FROM leads WHERE cnpj=?", (registro["cnpj"],)).fetchone()
            if linha:
                con.execute(
                    "INSERT OR IGNORE INTO buscas_leads (busca_id, lead_id, associado_em) VALUES (?,?,?)",
                    (busca_id, linha["id"], tempo.iso()),
                )
    return resultado


def listar(limite: int = 200) -> list[dict]:
    with conectar() as con:
        return [
            dict(r)
            for r in con.execute(
                """SELECT b.id, b.tag, b.provedor, b.segmento, b.cidade, b.uf, b.ano, b.mes,
                          b.total_fonte, b.criada_em, b.criada_por,
                          json_array_length(b.resultados_json) encontrados,
                          COUNT(DISTINCT bl.lead_id) importados,
                          SUM(CASE WHEN l.etapa='Retido LGPD' THEN 1 ELSE 0 END) retidos,
                          SUM(CASE WHEN l.etapa='Na fila do BDR' THEN 1 ELSE 0 END) na_fila
                   FROM buscas_prospeccao b
                   LEFT JOIN buscas_leads bl ON bl.busca_id=b.id
                   LEFT JOIN leads l ON l.id=bl.lead_id
                   GROUP BY b.id ORDER BY b.id DESC LIMIT ?""",
                (limite,),
            )
        ]


def ids_leads(busca_id: int) -> set[int]:
    with conectar() as con:
        return {int(r[0]) for r in con.execute("SELECT lead_id FROM buscas_leads WHERE busca_id=?", (busca_id,))}


def etiquetas_por_lead(lead_ids: list[int]) -> dict[int, str]:
    if not lead_ids:
        return {}
    with conectar() as con:
        linhas = con.execute(
            f"""SELECT bl.lead_id, GROUP_CONCAT(b.tag, ', ') tags
                FROM buscas_leads bl JOIN buscas_prospeccao b ON b.id=bl.busca_id
                WHERE bl.lead_id IN ({",".join("?" for _ in lead_ids)})
                GROUP BY bl.lead_id""",
            lead_ids,
        ).fetchall()
    return {int(r["lead_id"]): r["tags"] for r in linhas}


def filtrar_dataframe(df: pd.DataFrame, busca_id: int | None, coluna: str = "id") -> pd.DataFrame:
    """Filtra somente entre os registros já autorizados na página (não amplia permissões)."""
    if busca_id is None or df.empty:
        return df
    return df[df[coluna].isin(ids_leads(busca_id))].copy()


def com_tags(df: pd.DataFrame, coluna: str = "id") -> pd.DataFrame:
    if df.empty:
        return df.assign(tags=pd.Series(dtype=str))
    saida = df.copy()
    etiquetas = etiquetas_por_lead([int(x) for x in saida[coluna].tolist()])
    saida["tags"] = saida[coluna].map(etiquetas).astype("string").fillna("")
    return saida
