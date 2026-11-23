-- Recupera somente CNPJs retidos pela regra antiga de ausência de base para contato.
-- Opt-out, outras causas de retenção e decisões pré-existentes não são alterados.
-- A base legal original permanece 'sem_base': esta migração NÃO autoriza contato.

INSERT INTO etapas_historico (lead_id, de, para, ator, motivo, detalhe, registrado_em)
SELECT l.id, l.etapa, 'Capturado', 'migracao_fluxo_lgpd', NULL,
       'Retenção antiga por falta de base legal: liberado apenas para tratamento interno.',
       strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
FROM leads l
WHERE l.etapa='Retido LGPD'
  AND l.opt_out=0
  AND (SELECT c.base_legal FROM consentimentos c
       WHERE c.lead_id=l.id ORDER BY c.id DESC LIMIT 1)='sem_base'
  AND NOT EXISTS (
      SELECT 1 FROM consentimentos c
      WHERE c.lead_id=l.id AND c.opt_out_em IS NOT NULL
  )
  AND EXISTS (
      SELECT 1 FROM tratamentos t
      WHERE t.id=(SELECT MAX(t2.id) FROM tratamentos t2 WHERE t2.lead_id=l.id)
        AND t.destino='Retido LGPD'
        AND t.decomposicao LIKE '%Sem base legal válida para contato.%'
  );

UPDATE leads
SET etapa='Capturado', versao=versao+1, atualizado_em=strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
WHERE etapa='Retido LGPD'
  AND opt_out=0
  AND (SELECT c.base_legal FROM consentimentos c
       WHERE c.lead_id=leads.id ORDER BY c.id DESC LIMIT 1)='sem_base'
  AND NOT EXISTS (
      SELECT 1 FROM consentimentos c
      WHERE c.lead_id=leads.id AND c.opt_out_em IS NOT NULL
  )
  AND EXISTS (
      SELECT 1 FROM tratamentos t
      WHERE t.id=(SELECT MAX(t2.id) FROM tratamentos t2 WHERE t2.lead_id=leads.id)
        AND t.destino='Retido LGPD'
        AND t.decomposicao LIKE '%Sem base legal válida para contato.%'
  );
