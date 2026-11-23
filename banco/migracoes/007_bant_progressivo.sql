-- O BANT é preenchido progressivamente: cada critério pode ser validado pelo BDR
-- sem exigir dados que a empresa ainda não forneceu. Valores preliminares da IA
-- permanecem hipóteses na interface e NÃO são inseridos como fatos no BANT.
CREATE TABLE IF NOT EXISTS bant_validacoes (
    lead_id INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    campo TEXT NOT NULL CHECK(campo IN ('orcamento','autoridade','necessidade','prazo')),
    confirmado INTEGER NOT NULL DEFAULT 0 CHECK(confirmado IN (0,1)),
    atualizado_em TEXT NOT NULL,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
    PRIMARY KEY (lead_id, campo)
);
