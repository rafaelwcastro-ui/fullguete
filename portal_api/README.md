# API Fullguete — incremento 1, homologação somente leitura

**Não publicar nem utilizar o arquivo SQLite produtivo.** A API opera em leitura no SQLite e oferece consulta externa opcional. O servidor exige uma cópia separada do SQLite com esquema atualizado e usuários de teste. Por padrão, só lê leads com `base_ficticia=1`. Não há logins especiais: utiliza usuário ativo e verificação PBKDF2 existente. Não copie dados reais para uma instância pública.

## Rodar localmente

Na raiz, em ambiente virtual isolado:

```sh
pip install -r requirements.txt -r portal_api/requirements.txt
python -m unittest -v portal_api.test_readonly
FULLGUETE_API_DB_COPY=/caminho/copia-demo.db python -m uvicorn portal_api.app:create_app --factory --host 127.0.0.1 --port 8000
```

## Contrato

| Método | Rota | Finalidade |
|---|---|---|
| POST | /v1/session | Login JSON (login, senha); token opaco de 30 min |
| DELETE | /v1/session | Revoga token |
| GET | /v1/me | Identidade e perfil do servidor |
| GET | /v1/leads | Lista paginada; view=all/queue/triage/review, campaign_id, limit, offset |
| GET | /v1/leads/{id} | Ficha cadastral mínima e tags |
| GET | /v1/campaigns | Campanhas com leads visíveis, totais limitados ao escopo |
| POST | /v1/company-search | Consulta CNPJá opcional para gestor, sem persistência |

Envie `Authorization: Bearer <token>` nas leituras. Não persistir o token em localStorage; a integração Next.js mantém a sessão em backend-for-frontend e cookie HttpOnly/Secure/SameSite, sem expor tokens ao navegador. Não há CORS aberto. Esta API local tem sessões em memória e limitador global de login; antes de produção, exigir TLS, armazenamento compartilhado/revogável de sessões, política de rate limit distribuída, auditoria, revisão de autorização e testes de integração.

## Decisões conservadoras de escopo

- Gestor: todos os leads fictícios não opt-out; triagem exclusiva.
- BDR: somente `responsavel_id` próprio; executivo: somente `executivo_id` próprio. Isso é mais restritivo que algumas telas de legado e exige homologação de negócio.
- Opt-out não aparece nas rotas comerciais; governança própria fica pendente. Base legal pendente permite classificação interna, mas não libera contato. Reutiliza `lgpd.base_para_contato` e `estados.ETAPAS_DE_CONTATO`. Nenhum endpoint executa contato.
- Campanhas só aparecem se houver leads autorizados vinculados; ainda não lista campanhas sem importação, nem resultados brutos. Ficha não inclui contatos, observações, textos livres ou payload de IA.
- `allow_real_copy=True` é parâmetro explícito para futuros testes programáticos restritos em cópia autorizada, desabilita contas demonstrativas; não está habilitado no comando padrão e não é autorização de uso produtivo.
- Não há gravações operacionais. A prévia validada permanece intacta. Uma rota separada Next.js em /operacao conecta as leituras iniciais através de um BFF local; filtros adicionais (SLA/responsável), equivalência e hardening são próximos passos. Os testes adicionados usam fixture mínima de SQLite e devem ser executados antes de habilitar qualquer gravação.

## Interface de homologação
Com a API local em execução, em outro terminal rode `cd frontend && npm ci && npm run dev` e abra http://localhost:3000/operacao. A rota usa um BFF Next.js local com cookie HttpOnly/SameSite Strict, token opaco não exposto ao JavaScript, filtro de rotas e verificação de origem no login/logout. Cookie Secure em HTTPS; HTTP permitido apenas para homologação local. Não expor o servidor Next.js ou API na internet. O dashboard demonstrativo original permanece em /.

## Auditoria do PR #27

- Sessão revogada no logout; o BFF informa falha quando o servidor não confirma a revogação. Validações da API não repetem valores de credenciais. A API recusa o caminho configurado para o SQLite operacional e aliases do mesmo arquivo.
- Gestor e BDR podem ver a fila, ordenada por prazo de SLA e depois por score. O executivo continua com leitura da própria carteira, sem fila BDR nem triagem. Opt-out permanece excluído de todas as leituras comerciais. Base legal pendente permite ficha e progresso interno do BANT, e bloqueia a cadência de contato.
- Gestor e BDR no escopo recebem somente indicadores preenchido/confirmado do BANT. A ficha inclui dia, canal, prazo e conclusão da cadência quando a etapa e a base legal permitem contato. Valores livres e roteiros ficam fora da API.
- `POST /v1/company-search` consulta até 10 empresas com UF, código IBGE, CNAE e mês/ano de abertura. Somente gestor autenticado pode consultar. A rota fica desativada sem `FULLGUETE_API_CNPJA_KEY`, uma configuração exclusiva do servidor da API. A consulta ativa pode consumir créditos e está limitada a uma chamada por 15 s por processo. A integração foi testada com resposta simulada, sem chave real ou chamada ao fornecedor.

Nenhuma rota de mutação de lead está disponível. A busca externa não grava campanha nem importa seus resultados. Para a próxima etapa, importação deverá reutilizar `banco.prospeccao.importar` e separar respostas reais do SQLite fictício. Revisão, triagem, atribuição, cadência e BANT deverão reutilizar `nucleo.revisao`, `nucleo.triagem` e `nucleo.comercial` com autorização e operação na mesma transação. Em particular, `comercial.marcar_passo` valida a base legal ao concluir a cadência, mas o adaptador terá de validar também propriedade do lead, etapa e opt-out. As funções que chamam `conectar()` não podem ser chamadas diretamente na API de homologação, pois essa conexão resolve o banco padrão e pode migrá-lo.
