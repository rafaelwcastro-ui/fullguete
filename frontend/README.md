# Fullguete 3.0 — prévia do PR #26

## Execução local

Node.js 20.9+ com npm. O lockfile foi validado com Node.js 24.

```sh
cd frontend
npm ci
npm run typecheck
npm run build
npm run start
```

Abra http://localhost:3000. Use `npm run dev` para desenvolvimento.

## O que a prévia cobre

- **Visão geral e Analytics** usam o snapshot fictício com 30 dias, janela de 7 dias e tabela diária em Analytics. Datas agrupam leads pela captura. A série mede as etapas atingidas até a data de corte do snapshot.
- **Prospecção** permite consultar empresas e campanhas fictícias, com recortes distintos de qualificação e revisão.
- **Central BDR** separa fila, carteira e triagem. Próximas ações abre a ficha correspondente em um clique, inclusive quando a base legal está pendente.
- **CRM** apresenta exemplos por etapa e uma agenda somente leitura. **Assistente IA** permite consultar a ficha de exemplo em contexto. O chat com o catálogo, mudanças de etapa e reagendamento continuam disponíveis no Streamlit.

A [paleta](../docs/PALETA_FULLGUETE.md) vem dos PNGs oficiais. O frontend usa Next.js App Router, React, TypeScript, Tailwind CSS 4, o Card local em estilo shadcn/ui e Recharts. A barra de progresso é uma adaptação do Tremor Raw licenciada sob Apache 2.0. O pacote `@tremor/react` declara React 18 como peer dependency. O componente copiável mantém a stack React 19/Tailwind 4 sem ignorar peers.

## Snapshot e integração

```sh
cd frontend/integration
python -m unittest -v test_export_dashboard
python build_demo_snapshot.py
```

O gerador cria sua própria base temporária e usa o exportador para produzir `lib/demo-dashboard.json`. O build da prévia embarca apenas esse JSON. A consulta usa SQLite somente leitura, filtra `base_ficticia=1` e exporta totais por dia. Nenhum banco operacional deve ser usado na prévia.

### Contratos para a próxima etapa

| Jornada | Contrato e regras a preservar |
|---|---|
| Prospecção | Filtros de CNAE, município e período e histórico por campanha. Importação selecionada no pipeline Python com deduplicação por CNPJ e associação à campanha; dados cadastrais começam com base legal pendente. Credenciais e importação ficam no servidor. |
| Central BDR | Listagem paginada por situação, campanha, SLA e responsável. Resolver a identidade na sessão do servidor e aplicar escopo antes de montar fichas. Reusar triagem e gestão de leads, com validação de perfil, atribuição, estado e opt-out. |
| CRM | Usar serviços de agenda e comercial para transições, BANT, atividades e passagem ao executivo. Verificar titularidade, papel e regras de contato em cada operação. |
| Analytics | Manter `fullguete.dashboard.v1` para a série agregada de demonstração. Indicadores técnicos e dados operacionais exigem autorização e contrato próprios. |
| Assistente IA | Resolver o lead autorizado antes de expor contexto ou chamar o serviço existente de chat com o catálogo. Manter o modo consultivo. |

A API autenticada e todos os fluxos de escrita estão pendentes. Os testes de autorização da suíte Python validam o comportamento operacional existente em SQLite isolado. A próxima etapa da API exige testar sessão ausente, BDR responsável e fora da carteira, gestor, executivo e opt-out nas rotas.
