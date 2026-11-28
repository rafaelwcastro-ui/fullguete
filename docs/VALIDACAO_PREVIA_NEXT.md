# Auditoria e validação da prévia Fullguete 3.0

A auditoria partiu de `c4e8bdf`, revisão do PR #26. A aplicação Next.js já estava isolada em `frontend/`, mas o tema usava verde e um símbolo provisório, o gráfico usava uma série esparsa independente do exportador e várias abas exibiam a mesma amostra. O checkout também era distribuído sem lockfile.

A prévia agora usa os ativos oficiais e os [tokens de marca](PALETA_FULLGUETE.md). O exportador Python alimenta um JSON embarcado reproduzível, gerado a partir de SQLite temporário. Prospecção e Central BDR têm recortes distintos e fichas acessíveis. CRM usa etapas e agenda fictícias, Analytics expõe a série diária e o Assistente IA tem acesso local a fichas de exemplo. O [README da prévia](../frontend/README.md) descreve os contratos previstos para integração e os fluxos operacionais ainda atendidos pelo Streamlit.

## Verificações

- `npm ci`, `npm run build` e `npm run typecheck` aprovados. Node.js 24.22.3, Next.js 16.4.6, React 19.3.1 e Tailwind 4.3.5. O Tremor Raw foi integrado como componente local.
- `pytest` com SQLite e modelos temporários. 137 testes aprovados, incluindo regressões de triagem, permissões BDR, opt-out, CRM, agenda e contexto do Assistente.
- `python -m unittest -v test_export_dashboard`. O cenário confirma exclusão de leads reais e eventos futuros, deduplicação de histórico e preservação dos bytes da base. Duas gerações do snapshot produziram o mesmo SHA-256.
- `ruff check .`, `ruff format --check .` e `git diff --check` aprovados.
- Chromium com Playwright em 1440, 390 e 320 px. Verificados períodos de 7 e 30 dias, acesso direto à ficha, triagem BDR, campanhas, revisão, CRM, agenda e contexto do Assistente. Sem overflow na página ou exceções JavaScript nos fluxos testados.
- axe-core, regras WCAG 2.0/2.1 A e AA, sem violações detectadas nas telas verificadas de Visão geral, triagem e Analytics nos três tamanhos.
- O CI anterior do PR falhava no Ruff do exportador. As correções estão restritas aos arquivos de integração da prévia.

Capturas da Visão geral: [desktop 1440 px](previa-1440.webp) e [mobile 390 px](previa-390.webp).
