# Redesign Fullguete — proposta para homologação
Objetivo: reduzir a carga cognitiva sem retirar capacidades existentes. Referência: dashboards dark com contraste, cartões contidos, hierarquia e um acento verde-água/ciano. Não copiar layout ou marca de terceiros.

## Fluxo alvo
Captura e tratamento → triagem e fila BDR → carteira/CRM → resultado e aprendizado.

| Nova área | Origem existente | Decisão proposta |
|---|---|---|
| Visão geral | Dashboard | Mostrar 4 KPIs, tendências e ações urgentes; detalhes em Analytics |
| Prospecção | Captura + Tratamento IA | Uma jornada com abas Buscar, Campanhas, Qualificar e Revisar; manter deduplicação, histórico e destino |
| Central de trabalho | Fila BDR + Carteira | Fila prioritária por padrão; Todos os leads e triagem em abas com filtros e regras de perfil |
| CRM | CRM & funil | Kanban, agenda, ficha e oportunidade em navegação contextual |
| Analytics | Indicadores | Separar negócio de saúde técnica; indicadores técnicos sob área avançada autorizada |
| Administração | Governança + Catálogo | Controles LGPD, regras, catálogo, parâmetros e auditoria; permissões não devem ser presumidas |
| Assistente contextual | Assistente IA | Painel em contexto; manter acesso ao chat, sem ações autônomas |

Não remover código nem mudar os critérios de roteamento nesta fase. Diagnóstico de CNPJ fora da fila foi criado para rastreabilidade: preservar sua consulta em Todos os leads, evitando cópias visuais, mantendo avisos LGPD perto das ações. Ações permitidas dependem do backend, não da visibilidade de botões.

## Critérios obrigatórios de equivalência
- Captura por APIs/planilha/lista e campanhas com rastreabilidade e deduplicação; busca anterior reaberta sem cobrança adicional onde já suportado.
- Tratamento IA, nota explicável, recomendação, revisão humana, todos os destinos e filtros.
- Fila BDR por responsável/SLA, seleção, mudanças de status, redistribuição, agenda, BANT progressivo não obrigatório, descarte e registro.
- CRM, histórico, oportunidade, passagem ao executivo e feedback.
- Governança, LGPD, opt-out, autorização no servidor, dados reais separados de fictícios e catálogo.
- Testar as rotas com os papéis gestor, BDR e executivo. Não pressupor que o novo menu é uma política de autorização.

## Etapas
1. Prévia visual isolada em frontend/ (dados sintéticos, sem integração ou deploy produtivo).
2. Inventário de contratos e testes de regressão do Python existente; registrar baseline e testar backups.
3. Adicionar camada API Python sobre serviços existentes, começando por leitura de indicadores e depois mutações autorizadas. Usar um contrato de dados explícito e sessões seguras; manter credenciais exclusivamente no servidor.
4. Migrar uma jornada por vez, testar equivalência, LGPD, concorrência, responsividade e acessibilidade; homologação com dados de teste.
5. Implantar ambiente paralelo, validar, promover somente com aprovação e rollback. Avaliar banco persistente antes de uso contínuo.

A base Streamlit e seus testes permanecem intocados na primeira etapa. A prévia não prova que as funcionalidades foram portadas. Não alterar o deploy atual.
