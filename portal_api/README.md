# API Fullguete — incremento 1, homologação somente leitura

**Não publicar nem utilizar o arquivo SQLite produtivo.** A API não altera o banco, não aplica migrações e não importa dados. O servidor exige uma cópia separada do SQLite com esquema atualizado e usuários de teste. Por padrão, só lê leads com `base_ficticia=1`. Não há logins especiais: utiliza usuário ativo e verificação PBKDF2 existente. Não copie dados reais para uma instância pública.

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

Envie `Authorization: Bearer <token>` nas leituras. Não persistir o token em localStorage; a integração Next.js deverá manter a sessão em backend-for-frontend e cookie HttpOnly/Secure/SameSite, sem expor tokens ao navegador. Não há CORS aberto. Esta API local tem sessões em memória e limitador global de login; antes de produção, exigir TLS, armazenamento compartilhado/revogável de sessões, política de rate limit distribuída, auditoria, revisão de autorização e testes de integração.

## Decisões conservadoras de escopo

- Gestor: todos os leads fictícios não opt-out; triagem exclusiva.
- BDR: somente `responsavel_id` próprio; executivo: somente `executivo_id` próprio. Isso é mais restritivo que algumas telas de legado e exige homologação de negócio.
- Opt-out não aparece nas rotas comerciais; governança própria fica pendente. Base legal pendente permite classificação interna, mas não libera contato. Reutiliza `lgpd.base_para_contato` e `estados.ETAPAS_DE_CONTATO`. Nenhum endpoint executa contato.
- Campanhas só aparecem se houver leads autorizados vinculados; ainda não lista campanhas sem importação, nem resultados brutos. Ficha não inclui contatos, observações, textos livres ou payload de IA.
- `allow_real_copy=True` é parâmetro explícito para futuros testes programáticos restritos em cópia autorizada, desabilita contas demonstrativas; não está habilitado no comando padrão e não é autorização de uso produtivo.
- Não há gravações operacionais. O frontend Next.js existente permanece intacto. A ligação da interface ao contrato, filtros adicionais (SLA/responsável), testes com esquema real migrado, equivalência e hardening são próximos passos. Os testes adicionados usam fixture mínima de SQLite e devem ser executados antes de habilitar qualquer gravação.
