-- Mantém a abertura do estabelecimento após a importação (antes só existia no payload bronze).
ALTER TABLE leads ADD COLUMN data_abertura TEXT;
UPDATE leads SET data_abertura = (
    SELECT json_extract(b.payload, '$.data_abertura')
    FROM leads_brutos b
    WHERE b.lead_id=leads.id AND json_valid(b.payload)
      AND json_extract(b.payload, '$.data_abertura') IS NOT NULL
    ORDER BY b.id DESC LIMIT 1
) WHERE data_abertura IS NULL;

-- Campanhas de descoberta de empresas: filtros, amostras de respostas e origem de cada lead.
-- Chaves de API nunca são persistidas nesta estrutura.
CREATE TABLE IF NOT EXISTS buscas_prospeccao (
    id INTEGER PRIMARY KEY,
    tag TEXT NOT NULL UNIQUE,
    provedor TEXT NOT NULL,
    segmento TEXT NOT NULL,
    cidade TEXT NOT NULL,
    uf TEXT NOT NULL,
    ano INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    cnaes TEXT NOT NULL DEFAULT '',
    filtros_json TEXT NOT NULL,
    resultados_json TEXT NOT NULL DEFAULT '[]',
    total_fonte INTEGER NOT NULL DEFAULT 0,
    criada_em TEXT NOT NULL,
    atualizada_em TEXT NOT NULL,
    criada_por TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_buscas_criada ON buscas_prospeccao(criada_em);
CREATE TABLE IF NOT EXISTS buscas_leads (
    busca_id INTEGER NOT NULL REFERENCES buscas_prospeccao(id) ON DELETE CASCADE,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    associado_em TEXT NOT NULL,
    PRIMARY KEY (busca_id, lead_id)
);
CREATE INDEX IF NOT EXISTS idx_buscas_leads_lead ON buscas_leads(lead_id);

-- Vínculo recuperável de importações CNPJá realizadas antes de existir a tag.
-- Os filtros originais NÃO estavam gravados e não são inventados.
INSERT INTO buscas_prospeccao
    (tag, provedor, segmento, cidade, uf, ano, mes, cnaes, filtros_json,
     resultados_json, total_fonte, criada_em, atualizada_em, criada_por)
SELECT '#cnpja-importacoes-anteriores-01', 'cnpja', 'Histórico anterior',
       'Não informado', '', 0, 0, '', '{}', '[]', 0,
       MIN(recebido_em), MAX(recebido_em), 'migracao'
FROM leads_brutos
WHERE origem='cnpja' AND lead_id IS NOT NULL
HAVING COUNT(*) > 0;

INSERT OR IGNORE INTO buscas_leads (busca_id, lead_id, associado_em)
SELECT s.id, b.lead_id, MIN(b.recebido_em)
FROM leads_brutos b
CROSS JOIN buscas_prospeccao s
WHERE b.origem='cnpja' AND b.lead_id IS NOT NULL
  AND s.tag='#cnpja-importacoes-anteriores-01'
GROUP BY s.id, b.lead_id;
