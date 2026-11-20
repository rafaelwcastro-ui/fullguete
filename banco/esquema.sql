-- Esquema base do Fullguete v2 (versão 1).
-- Mudanças posteriores entram como arquivos em banco/migracoes/NNN_descricao.sql.
-- Camadas do pipeline: leads_brutos (bronze), leads + contatos (prata), leads_features (ouro).

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    login TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    papel TEXT NOT NULL CHECK (papel IN ('bdr', 'gestor', 'executivo')),
    senha_hash TEXT NOT NULL,
    meta_contatos_dia INTEGER NOT NULL DEFAULT 20,
    demonstracao INTEGER NOT NULL DEFAULT 0,
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL
);

-- Bronze: tudo que chega, do jeito que chegou.
CREATE TABLE IF NOT EXISTS leads_brutos (
    id INTEGER PRIMARY KEY,
    recebido_em TEXT NOT NULL,
    origem TEXT NOT NULL,             -- formulario, planilha, cnpj_lista, webhook_site, base_ficticia
    lote TEXT,
    payload TEXT NOT NULL,            -- JSON original
    status TEXT NOT NULL DEFAULT 'Recebido',  -- Recebido, Na fila da IA, Tratado, Retido, Rejeitado
    problemas TEXT NOT NULL DEFAULT '[]',     -- JSON com o que a higienização encontrou
    lead_id INTEGER REFERENCES leads(id),
    base_ficticia INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_brutos_status ON leads_brutos(status, recebido_em);

-- Prata: dados da empresa, limpos e sem duplicidade.
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    origem TEXT NOT NULL,
    cnpj TEXT,
    chave_dedup TEXT NOT NULL UNIQUE,  -- CNPJ ou nome|cidade|uf normalizados
    razao_social TEXT NOT NULL,
    nome_fantasia TEXT,
    cnae TEXT,
    setor TEXT,
    segmento TEXT,                     -- grupo de CNAE usado no grafo
    porte TEXT,
    funcionarios INTEGER,
    cidade TEXT,
    uf TEXT,
    site TEXT,
    descricao TEXT,
    situacao_cadastral TEXT,
    interesse TEXT,                    -- Crédito, Antifraude, Cobrança, Prospecção, Não sei
    observacao TEXT,
    sinais_simulados TEXT NOT NULL DEFAULT '{}',  -- JSON, sempre rotulado como simulado
    dados_cnpjws TEXT,                 -- JSON real do CNPJ.ws, quando houver
    etapa TEXT NOT NULL DEFAULT 'Capturado',
    responsavel_id INTEGER REFERENCES usuarios(id),
    executivo_id INTEGER REFERENCES usuarios(id),
    nota_final REAL,
    classificacao TEXT,
    solucao_principal TEXT,
    sla_limite TEXT,
    primeiro_contato_em TEXT,
    proxima_acao TEXT,
    retorno_em TEXT,
    opt_out INTEGER NOT NULL DEFAULT 0,
    base_ficticia INTEGER NOT NULL DEFAULT 0,
    versao INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_leads_etapa ON leads(etapa);
CREATE INDEX IF NOT EXISTS idx_leads_responsavel ON leads(responsavel_id, etapa);

-- Dados pessoais do contato ficam separados e nunca vão para o LLM.
CREATE TABLE IF NOT EXISTS contatos (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    nome TEXT,
    cargo TEXT,
    email TEXT,
    telefone TEXT,
    criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contatos_lead ON contatos(lead_id);

-- Ouro: variáveis prontas para os modelos.
CREATE TABLE IF NOT EXISTS leads_features (
    lead_id INTEGER PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
    gerado_em TEXT NOT NULL,
    features TEXT NOT NULL,            -- JSON
    cluster INTEGER
);

CREATE TABLE IF NOT EXISTS consentimentos (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    base_legal TEXT NOT NULL,          -- consentimento, legitimo_interesse, sem_base
    consentiu INTEGER NOT NULL DEFAULT 0,
    canal TEXT,
    registrado_em TEXT NOT NULL,
    registrado_por TEXT NOT NULL,
    opt_out_em TEXT,
    observacao TEXT
);
CREATE INDEX IF NOT EXISTS idx_consentimentos_lead ON consentimentos(lead_id);

CREATE TABLE IF NOT EXISTS icp_versoes (
    id INTEGER PRIMARY KEY,
    criada_em TEXT NOT NULL,
    criada_por TEXT NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT NOT NULL,
    setores TEXT NOT NULL DEFAULT '[]',
    portes TEXT NOT NULL DEFAULT '[]',
    palavras_chave TEXT NOT NULL DEFAULT '[]',
    ativa INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tratamentos (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    lote TEXT NOT NULL,
    iniciado_em TEXT NOT NULL,
    concluido_em TEXT,
    icp_versao_id INTEGER REFERENCES icp_versoes(id),
    motor TEXT NOT NULL,               -- gemini ou local
    modelo TEXT,
    versao_prompt TEXT,
    modelo_propensao TEXT,
    nota_aderencia REAL,
    propensao REAL,
    confianca REAL,
    nota_final REAL,
    classificacao TEXT,
    destino TEXT,
    decomposicao TEXT,                 -- JSON
    resultado TEXT,                    -- JSON validado da IA
    plano_b INTEGER NOT NULL DEFAULT 0,
    tempo_ms INTEGER,
    custo_estimado REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tratamentos_lead ON tratamentos(lead_id, id);
CREATE INDEX IF NOT EXISTS idx_tratamentos_lote ON tratamentos(lote);

-- Linha de progresso por agente.
CREATE TABLE IF NOT EXISTS tratamento_etapas (
    id INTEGER PRIMARY KEY,
    tratamento_id INTEGER NOT NULL REFERENCES tratamentos(id) ON DELETE CASCADE,
    lote TEXT NOT NULL,
    ordem INTEGER NOT NULL,
    agente TEXT NOT NULL,
    status TEXT NOT NULL,              -- ok, alerta, erro, pulado
    iniciado_em TEXT NOT NULL,
    tempo_ms INTEGER,
    detalhe TEXT
);
CREATE INDEX IF NOT EXISTS idx_etapas_lote ON tratamento_etapas(lote, ordem);

CREATE TABLE IF NOT EXISTS recomendacoes (
    id INTEGER PRIMARY KEY,
    tratamento_id INTEGER NOT NULL REFERENCES tratamentos(id) ON DELETE CASCADE,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    solucao_id TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('principal', 'complementar')),
    motivo TEXT,
    confianca REAL,
    caminho_grafo TEXT                 -- JSON com o subgrafo que justificou
);
CREATE INDEX IF NOT EXISTS idx_recomendacoes_solucao ON recomendacoes(solucao_id);

CREATE TABLE IF NOT EXISTS atribuicoes (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    atribuido_em TEXT NOT NULL,
    atribuido_por TEXT NOT NULL,
    motivo TEXT,
    ativa INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS atividades (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    usuario_id INTEGER REFERENCES usuarios(id),
    registrada_em TEXT NOT NULL,
    tipo TEXT NOT NULL,                -- Ligação, E-mail, WhatsApp, Reunião, Nota
    resultado TEXT,
    anotacao TEXT,
    proxima_acao TEXT,
    retorno_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_atividades_lead ON atividades(lead_id, id);

CREATE TABLE IF NOT EXISTS cadencia_passos (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    dia INTEGER NOT NULL,
    canal TEXT NOT NULL,
    descricao TEXT NOT NULL,
    previsto_para TEXT NOT NULL,
    feito_em TEXT
);

CREATE TABLE IF NOT EXISTS bant (
    lead_id INTEGER PRIMARY KEY REFERENCES leads(id) ON DELETE CASCADE,
    orcamento TEXT,
    autoridade TEXT,
    necessidade TEXT,
    prazo TEXT,
    atualizado_em TEXT NOT NULL,
    usuario_id INTEGER REFERENCES usuarios(id)
);

CREATE TABLE IF NOT EXISTS etapas_historico (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    de TEXT,
    para TEXT NOT NULL,
    ator TEXT NOT NULL,
    motivo TEXT,
    detalhe TEXT,
    registrado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_etapas_hist_lead ON etapas_historico(lead_id, id);

CREATE TABLE IF NOT EXISTS oportunidades (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL UNIQUE REFERENCES leads(id) ON DELETE CASCADE,
    solucoes TEXT NOT NULL DEFAULT '[]',
    valor_mensal REAL,                 -- valor fictício informado pelo usuário
    executivo_id INTEGER REFERENCES usuarios(id),
    previsao_fechamento TEXT,
    resumo_passagem TEXT,
    criada_em TEXT NOT NULL,
    atualizada_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS correcoes_ia (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    tratamento_id INTEGER REFERENCES tratamentos(id),
    usuario_id INTEGER REFERENCES usuarios(id),
    campo TEXT NOT NULL,               -- solucao, nota, classificacao
    valor_ia TEXT,
    valor_correto TEXT,
    concorda INTEGER NOT NULL DEFAULT 0,
    motivo TEXT NOT NULL,
    registrada_em TEXT NOT NULL
);

-- Histórico de resultados usado para treinar a propensão (fictício no início, depois do funil).
CREATE TABLE IF NOT EXISTS rotulos_treino (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id) ON DELETE SET NULL,
    fonte TEXT NOT NULL,               -- base_ficticia ou funil
    registrado_em TEXT NOT NULL,
    features TEXT NOT NULL,            -- JSON com as mesmas variáveis de leads_features
    resultado INTEGER NOT NULL,        -- 1 ganho, 0 perdido
    motivo TEXT,
    solucao_id TEXT,
    valor_mensal REAL
);

CREATE TABLE IF NOT EXISTS modelos_registro (
    id INTEGER PRIMARY KEY,
    nome TEXT NOT NULL,
    versao TEXT NOT NULL,
    algoritmo TEXT NOT NULL,
    treinado_em TEXT NOT NULL,
    metricas TEXT NOT NULL,            -- JSON
    variaveis TEXT NOT NULL,           -- JSON
    n_treino INTEGER,
    n_teste INTEGER,
    caminho TEXT,
    ativo INTEGER NOT NULL DEFAULT 0,
    UNIQUE (nome, versao)
);

-- Observabilidade de toda chamada de IA.
CREATE TABLE IF NOT EXISTS eventos_ia (
    id INTEGER PRIMARY KEY,
    ocorrido_em TEXT NOT NULL,
    lote TEXT,
    lead_id INTEGER,
    agente TEXT NOT NULL,
    provedor TEXT NOT NULL,
    modelo TEXT,
    versao_prompt TEXT,
    latencia_ms INTEGER,
    tokens_entrada INTEGER NOT NULL DEFAULT 0,
    tokens_saida INTEGER NOT NULL DEFAULT 0,
    custo_estimado REAL NOT NULL DEFAULT 0,
    plano_b INTEGER NOT NULL DEFAULT 0,
    cache INTEGER NOT NULL DEFAULT 0,
    erro TEXT
);
CREATE INDEX IF NOT EXISTS idx_eventos_data ON eventos_ia(ocorrido_em);

CREATE TABLE IF NOT EXISTS cache_cnpj (
    cnpj TEXT PRIMARY KEY,
    consultado_em TEXT NOT NULL,
    dados TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS configuracoes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,               -- JSON
    atualizado_em TEXT NOT NULL,
    atualizado_por TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS configuracoes_historico (
    id INTEGER PRIMARY KEY,
    chave TEXT NOT NULL,
    valor_anterior TEXT,
    valor_novo TEXT NOT NULL,
    alterado_em TEXT NOT NULL,
    alterado_por TEXT NOT NULL,
    motivo TEXT
);

CREATE TABLE IF NOT EXISTS auditoria (
    id INTEGER PRIMARY KEY,
    ocorrido_em TEXT NOT NULL,
    ator TEXT NOT NULL,
    acao TEXT NOT NULL,
    entidade TEXT NOT NULL,
    entidade_id TEXT,
    detalhe TEXT                       -- JSON
);
CREATE INDEX IF NOT EXISTS idx_auditoria_entidade ON auditoria(entidade, entidade_id);
