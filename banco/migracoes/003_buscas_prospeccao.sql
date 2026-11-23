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
