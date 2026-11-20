# Roteiro da demonstração (5 a 7 minutos)

Funciona sem chave de API. Com `GEMINI_API_KEY` no `.env`, o tratamento usa o Gemini e o resto é igual.

**Antes de começar:** abra o app no modo simulado. Na primeira abertura ele monta um mês fictício de operação.
Para ensaiar de novo do zero, use Governança & LGPD → Base de demonstração → Reiniciar.

| Tempo | Passo | O que mostrar e falar |
|---|---|---|
| 0:00 | **1. Login como gestor, Dashboard** | Clique em "Gestor: Gestor Demo". Mostre o objetivo no topo, o funil de ponta a ponta com a conversão entre etapas e os alertas (Quentes sem contato acima do SLA, retidos por LGPD). Fale: "a IA é o meio, o objetivo é receita e produtividade do BDR". |
| 0:45 | **2. Captura** | Captura de leads → Formulário manual. Digite um CNPJ real e clique em Buscar dados (CNPJ.ws real). Preencha contato e marque o consentimento. Ligue "Tratar automaticamente ao capturar". Clique em Capturar lead. Vá em Site / webhook (simulado) e simule a chegada de 10 leads: a tabela de entrada em tempo real se enche. |
| 1:45 | **3. Tratamento IA** | Aba Tratar leads: envie os capturados e mostre a linha de etapas dos 7 agentes. Na aba Leads tratados, abra a ficha do primeiro: nota decomposta (aderência, propensão, confiança), justificativa, solução Equifax recomendada, caminho no grafo e dados reais separados dos simulados. Na aba Revisão humana, resolva um caso com motivo. |
| 3:00 | **4. Login como BDR** | Sair e entrar como "BDR: Ana Demo" (ou o BDR para quem o lead foi distribuído). Fila do BDR: o lead aparece no topo. Abra Roteiro (botão copiar, nada é enviado). Em Cadência e atividade, registre uma Ligação. Em BANT, preencha a Necessidade. Em Corrigir a IA, registre uma avaliação com motivo. Em Ações, Qualificar e agendar reunião. |
| 4:30 | **5. CRM & funil** | Abra o lead. Oportunidade: soluções e valor mensal. Mova para Proposta e depois para Ganho, confirmando. Aparece "Resultado enviado para o aprendizado do modelo". Abra a Linha do tempo: captura, tratamento (nota, solução, versão do modelo), atividades, etapas e aprendizado. |
| 5:30 | **6. Indicadores** | Negócio: o ganho no funil e na receita. Técnica: clique em Retreinar com os resultados do funil e mostre a nova versão registrada, a comparação regressão logística x árvore, as variáveis que mais pesam, o drift (PSI), a latência, o custo por 1.000 leads e o uso do plano B. |
| 6:30 | **7. Governança** | Trilha de auditoria filtrada pelo lead da demonstração. Na aba Base legal e opt-out, registre o opt-out de outro lead e mostre que ele sai da fila. Feche com: "o Fullguete não decide crédito, prioriza prospects, e todo passo é explicável e auditável". |

**Plano B da apresentação:** se a internet falhar, o CNPJ.ws e o Gemini ficam indisponíveis. O tratamento cai
sozinho no modo local e a demonstração segue igual. Os leads do site simulado não dependem de rede.
