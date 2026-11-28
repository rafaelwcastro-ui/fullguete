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
| `GET /v1/operation-options` | Opções de funil e catálogos usados nos formulários |
| `GET /v1/search-history` e `GET /v1/search-history/{id}` | Buscas simuladas e resultados reabríveis pelo gestor |
| `POST /v1/commands` | Comando autenticado com `Idempotency-Key` UUID |
| `POST /v1/company-search` | Consulta externa opcional do modo somente leitura, desativada sem `FULLGUETE_API_CNPJA_KEY` |

No navegador, o BFF Next.js mantém o token em cookie HttpOnly/SameSite Strict e valida a origem das operações. Para testes diretos, envie `Authorization: Bearer <token>`. As respostas comerciais usam `Cache-Control: no-store`.

### Comandos e transação

- Gestor pode buscar, importar, processar, revisar, encaminhar e atribuir. Nos comandos de BDR, o gestor opera os leads fictícios elegíveis e o BDR opera somente os da sua carteira. Executivo tem leitura da carteira e não executa comandos.
- A busca de escrita usa uma amostra determinística do catálogo fictício local e persiste histórico. Ela ignora chaves externas no modo de gravação. Importe apenas os CNPJs da busca salva. A ingestão existente deduplica e o serviço de prospecção associa o lead preexistente a outra campanha sem duplicá-lo. Novos leads entram com base legal pendente.
- Processamento reutiliza os agentes, score e classificação do Python em modo local. A interface permite decidir revisão humana, encaminhar casos elegíveis e redistribuir leads ativos.
- Status, atividades, cadência, agenda e BANT usam os serviços existentes. Opt-out exclui o lead das ações. Contatos, conclusão de cadência e retornos comerciais exigem base e etapa elegíveis. BANT aceita um critério por vez. O preenchimento do BANT pode avançar sem contato.
- Comandos de lead enviam `leads: [{ id, versao }]`. SQLite inicia `BEGIN IMMEDIATE` antes da autenticação e das checagens de papel, carteira, LGPD e versão. Serviços herdam a conexão só no contexto do comando. Falha em qualquer item reverte o lote. A versão desatualizada recebe 409. Banco ocupado recebe 503.
- A chave UUID é gravada por usuário junto com o resultado e a transação. A repetição do mesmo pedido recupera o resultado, inclusive após reinício, se o usuário ainda estiver autorizado. Reutilizar a chave com outro pedido dá 409. A interface reaproveita a chave para repetir um pedido idêntico após falha de rede. Uma operação confirmada atualiza ficha, totais, revisão, fila, SLA e campanhas.

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
