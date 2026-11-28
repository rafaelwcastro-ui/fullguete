# API Fullguete para homologação local

A API mantém leitura como padrão. As gravações exigem um banco fictício criado pelo preparador e uma opção explícita. Use apenas servidores em loopback e credenciais de demonstração.

## Executar a homologação com escrita

Na raiz, em um ambiente Python isolado:

```sh
pip install -r requirements.txt -r portal_api/requirements.txt
python -m portal_api.sandbox /tmp/fullguete-homologacao
FULLGUETE_API_DB_COPY=/tmp/fullguete-homologacao/homologacao.db \
FULLGUETE_API_WRITE_MODE=homologacao \
python -m uvicorn portal_api.app:create_app --factory --host 127.0.0.1 --port 8000
```

O preparador exige um diretório novo e gera esquema, 100 leads fictícios, usuários e modelos locais. A API recusa o caminho e aliases do banco operacional, bases mistas, perfis reais na base e cópias que não tenham sido preparadas. A API não aplica migrações. Para executar somente leitura, omita `FULLGUETE_API_WRITE_MODE`. Para uso local paralelo, não aponte a configuração do Streamlit para o banco de homologação.

Em outro terminal, rode `cd frontend && npm ci && npm run build && npm run start -- --hostname 127.0.0.1`. Abra `http://127.0.0.1:3000/operacao`. Logins fictícios `gestor`, `bdr.ana`, `bdr.bruno` e `executivo`, com senha `fullguete-demo`.

## Contratos

| Rota | Finalidade |
|---|---|
| `POST /v1/session` e `DELETE /v1/session` | Sessão opaca revogável de 30 minutos |
| `GET /v1/me` | Ator atual e disponibilidade de gravação |
| `GET /v1/leads` e `GET /v1/leads/{id}` | Lista paginada, ficha, versão e indicadores no modo de homologação |
| `GET /v1/campaigns` | Campanhas com leads visíveis no escopo |
| `GET /v1/crm`, `GET /v1/crm/{id}` | Kanban e ficha com oportunidade, passagem e últimos 30 eventos |
| `GET /v1/agenda` | Compromissos paginados por status e lead |
| `GET /v1/analytics` | Funil, produtividade, SLA, campanhas, receita e IA por coorte autorizada |
| `POST /v1/assistente` | Orientação local do catálogo, do lead ou da carteira |
| `GET /v1/operation-options` | Opções de funil e catálogos usados nos formulários |
| `GET /v1/search-history` e `GET /v1/search-history/{id}` | Buscas simuladas e resultados reabríveis pelo gestor |
| `POST /v1/commands` | Comando autenticado com `Idempotency-Key` UUID |
| `POST /v1/company-search` | Consulta externa opcional do modo somente leitura, desativada sem `FULLGUETE_API_CNPJA_KEY` |

No navegador, o BFF Next.js mantém o token em cookie HttpOnly/SameSite Strict e valida a origem das operações. Para testes diretos, envie `Authorization: Bearer <token>`. As respostas comerciais usam `Cache-Control: no-store`.

### Comandos e transação

- Gestor pode buscar, importar, processar, revisar, encaminhar e atribuir. Nos comandos de BDR, o gestor opera os leads fictícios elegíveis e o BDR opera somente os da sua carteira. Executivo consulta a própria carteira e pode operar CRM e agenda nesse escopo.
- A busca de escrita usa uma amostra determinística do catálogo fictício local e persiste histórico. Ela ignora chaves externas no modo de gravação. Importe apenas os CNPJs da busca salva. A ingestão existente deduplica e o serviço de prospecção associa o lead preexistente a outra campanha sem duplicá-lo. Novos leads entram com base legal pendente.
- Processamento reutiliza os agentes, score e classificação do Python em modo local. A interface permite decidir revisão humana, encaminhar casos elegíveis e redistribuir leads ativos.
- Status, atividades, cadência, agenda e BANT usam os serviços existentes. Opt-out exclui o lead das ações. Contatos, conclusão de cadência e retornos comerciais exigem base e etapa elegíveis. BANT aceita um critério por vez. O preenchimento do BANT pode avançar sem contato.
- Comandos de lead enviam `leads: [{ id, versao }]`. SQLite inicia `BEGIN IMMEDIATE` antes da autenticação e das checagens de papel, carteira, LGPD e versão. Serviços herdam a conexão só no contexto do comando. Falha em qualquer item reverte o lote. A versão desatualizada recebe 409. Banco ocupado recebe 503.
- A chave UUID é gravada por usuário junto com o resultado e a transação. A repetição do mesmo pedido recupera o resultado, inclusive após reinício, se o usuário ainda estiver autorizado. Reutilizar a chave com outro pedido dá 409. A interface reaproveita a chave para repetir um pedido idêntico após falha de rede. Uma operação confirmada atualiza ficha, totais, revisão, fila, SLA e campanhas.

### CRM, Agenda e Analytics

- Kanban usa as etapas do funil Python. O BDR trabalha a oportunidade na carteira, qualifica e passa ao executivo com reunião futura e resumo local. Gestor e executivo atribuído podem avançar à proposta e registrar ganho ou perda. Perdas exigem motivo. Os resultados alimentam os rótulos de aprendizado legados.
- Compromissos comerciais exigem base legal e etapa compatível. Tarefas internas permanecem disponíveis para análise. Agenda combina carteira com responsabilidade pelo compromisso e registra criação, reagendamento, cancelamento e conclusão. Reagendar mantém o mesmo compromisso, valida conflitos de reunião e sincroniza a próxima ação.
- Analytics usa uma coorte pela data de captura, filtrável por campanha. Conversões contam leads únicos que alcançaram cada etapa. SLA e receita prevista reutilizam as métricas do Python. A previsão pondera o valor mensal por etapa, com 15% em Qualificado, 30% em Reunião marcada e 60% em Proposta. Produtividade, tratamentos e concordância referem-se aos leads do recorte.
- O Assistente trabalha em modo local e consultivo. Pode destacar revisão, SLAs vencidos e propostas, priorizar oportunidades do escopo e recomendar ações com contexto autorizado e catálogo. O modo local não envia consultas ao provedor de IA. Leads com contato bloqueado recebem orientação de análise interna. A regularização da base legal permanece no serviço existente de Governança. O teste de ponta a ponta chama esse serviço na cópia fictícia.

## Validação

```sh
pytest
python -m unittest -v portal_api.test_readonly portal_api.test_commands
python -m compileall -q portal_api
ruff check .
ruff format --check .
cd frontend
npm ci
npm run build
npm run typecheck
```

A suíte de gravação prepara a base fictícia em outro processo e usa uma cópia por teste. Cobre escopo, opt-out, base legal, deduplicação, revisão, processamento, concorrência, rollback de lote e repetição após reinício.

### Navegador

Com a API e o Next.js rodando sobre uma base fictícia recém-preparada, instale Playwright e axe-core em um diretório temporário e execute o teste. O roteiro grava dados na cópia e cobre os fluxos do gestor em 1440 px e do BDR em 390 px.

```sh
npm install --prefix /tmp/fullguete-browser playwright-core @axe-core/playwright
NODE_PATH=/tmp/fullguete-browser/node_modules \
CHROMIUM_PATH=/usr/bin/chromium \
OPERATION_URL=http://127.0.0.1:3000/operacao \
OPERATION_SCREENSHOTS=/tmp/fullguete-capturas \
node frontend/integration/test_operation_browser.cjs
```

Omita `OPERATION_SCREENSHOTS` para executar sem gravar capturas.

Capturas da validação do PR #27. [Desktop em 1440 px](../docs/operacao-desktop.webp) · [Mobile em 390 px](../docs/operacao-mobile.webp).

O roteiro complementar `frontend/integration/test_commercial_browser.cjs` usa as mesmas variáveis e verifica passagem, Agenda, Analytics, Assistente e fechamento. Execute cada roteiro sobre uma base fictícia recém-preparada ou execute primeiro o roteiro comercial e depois o roteiro de Prospecção e BDR, na mesma cópia.

Evidências da migração comercial no PR #27. [CRM desktop](../docs/crm-desktop.webp) · [Agenda mobile](../docs/agenda-mobile.webp) · [Analytics mobile](../docs/analytics-mobile.webp) · [Assistente desktop](../docs/assistente-desktop.webp).
