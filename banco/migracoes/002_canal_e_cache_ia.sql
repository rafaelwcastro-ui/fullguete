-- Canal de captura no lead (formulário, planilha, webhook...) e cache das respostas da IA.
ALTER TABLE leads ADD COLUMN canal TEXT;

CREATE TABLE IF NOT EXISTS cache_ia (
    chave TEXT PRIMARY KEY,           -- CNPJ ou identidade + versão do prompt + ICP + candidatas
    criado_em TEXT NOT NULL,
    resposta TEXT NOT NULL            -- JSON validado
);

CREATE INDEX IF NOT EXISTS idx_leads_base_ficticia ON leads(base_ficticia);
