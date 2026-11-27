# Fullguete — instruções para agentes de desenvolvimento

## Identidade visual obrigatória
- A marca original é a fonte de verdade: inspecione `assets/logo.png` e `assets/icone.png`, extraia a paleta e documente os HEX reais antes de modificar o design.
- Preserve os arquivos da marca e use-os na interface; substitua o ícone provisório da prévia pelo ativo oficial. Não redesenhe a logo nem adote o verde/ciano da referência se não pertencer à paleta original. Use a referência aprovada para composição, hierarquia, contraste, cards quase pretos, menu e distribuição visual, não como identidade cromática.
- Derive tokens semânticos acessíveis, verifique contraste e responsividade. Não use sparklines fictícios como dados reais.

## Escopo e segurança
- Trabalhe somente na branch `design/fullguete-next-preview` ou numa branch derivada dela. PR de referência: #26. Não faça merge em `main`, não publique e não altere a aplicação Streamlit em operação sem autorização explícita.
- Preserve serviços Python, regras de negócio, captura, agentes IA, score, rastreabilidade, BDR, BANT progressivo, agenda, CRM, LGPD, permissões e catálogo. Não remova funções por parecerem redundantes; simplifique a exposição visual e valide equivalência.
- Leia `README.md`, `frontend/README.md`, `docs/REDESIGN_PORTAL.md` e `docs/REDESIGN_VISUAL_APROVADO.md`; em conflito cromático, este arquivo prevalece.
- Use Next.js, React, TypeScript, Tailwind, shadcn/ui e Tremor seletivamente após validar compatibilidade; preserve o motor Python. Não use credenciais reais, nem conecte a prévia ao banco produtivo. O SQLite atual pode executar migrações ao abrir.

## Primeira tarefa
1. Inspecione os ativos oficiais e aplique a paleta real à prévia. Preserve a composição dark aprovada.
2. Instale dependências, gere lockfile, rode typecheck, build, teste do exportador de leitura e testes Python de regressão em ambiente isolado; corrija falhas sem alterar regras operacionais.
3. Valide desktop e mobile, navegação e acessibilidade; registre screenshots se o ambiente suportar.
4. Evolua Prospecção e Central BDR incrementalmente, com contratos de integração e testes de autorização. Não apresente controles de demonstração como funcionais em produção.
5. Registre alterações, resultados de testes, limitações e próximos passos no PR de redesign. Não mescle nem publique.
