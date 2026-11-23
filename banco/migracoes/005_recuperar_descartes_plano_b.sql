-- Recupera somente CNPJs reais descartados automaticamente por falha do Gemini.
-- Preserva nota, classificação original, histórico e base legal de contato.
-- Não toca em opt-out, descartes por decisão humana ou leads fictícios.

INSERT INTO etapas_historico (lead_id, de, para, ator, motivo, detalhe, registrado_em)
SELECT l.id, l.etapa, 'Revisão humana', 'migracao_plano_b_005', NULL,
       'Descarte por plano B local reclassificado como revisão comercial: score e decisão original da IA preservados.',
       strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
FROM leads l
JOIN tratamentos t ON t.id=(
    SELECT MAX(t2.id) FROM tratamentos t2 WHERE t2.lead_id=l.id AND t2.concluido_em IS NOT NULL
)
WHERE l.etapa='Descartado'
  AND l.origem IN ('cnpja', 'busca_cnpj')
  AND l.base_ficticia=0 AND l.opt_out=0
  AND t.plano_b=1 AND t.destino='Descartado'
  AND EXISTS (
      SELECT 1 FROM etapas_historico h
      WHERE h.id=(SELECT MAX(h2.id) FROM etapas_historico h2 WHERE h2.lead_id=l.id)
        AND h.ator='agente_supervisor' AND h.para='Descartado'
  );

UPDATE leads
SET etapa='Revisão humana',
    atualizado_em=strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
    versao=versao+1
WHERE etapa='Descartado'
  AND id IN (
      SELECT h.lead_id FROM etapas_historico h
      WHERE h.ator='migracao_plano_b_005' AND h.para='Revisão humana'
  );
