-- Compromissos comerciais independentes de alterações da etapa do funil.
-- Qualquer tarefa, retorno ou reunião planejada preserva a distinção entre
-- gestão interna e contato efetivo com uma pessoa.
CREATE TABLE IF NOT EXISTS agenda_compromissos (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    responsavel_id INTEGER NOT NULL REFERENCES usuarios(id),
    criado_por INTEGER NOT NULL REFERENCES usuarios(id),
    tipo TEXT NOT NULL CHECK(tipo IN ('Tarefa interna','Retorno','Reunião planejada','Reunião confirmada')),
    titulo TEXT NOT NULL,
    descricao TEXT,
    inicio_em TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pendente'
        CHECK(status IN ('Pendente','Concluído','Cancelado')),
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    concluido_em TEXT
);
CREATE INDEX IF NOT EXISTS idx_agenda_responsavel_prazo
    ON agenda_compromissos(responsavel_id, status, inicio_em);
CREATE INDEX IF NOT EXISTS idx_agenda_lead
    ON agenda_compromissos(lead_id, status, inicio_em);
