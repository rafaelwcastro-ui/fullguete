# Fullguete v2

Protótipo acadêmico do MBA Executivo da FGV, disciplina Arquitetura de Dados e Aplicações de Data Science em
Negócios. Demonstra, de ponta a ponta, um fluxo de geração de receita apoiado por IA:

**Captura do lead → Tratamento pela IA → Painel do BDR → Funil até o fechamento → Aprendizado devolvido ao modelo.**

## Objetivo de negócio

Aumentar a receita com as soluções B2B da Equifax Brasil e a produtividade do time de BDRs. O Fullguete recebe
empresas interessadas, a IA qualifica cada uma, diz qual solução Equifax faz sentido e por quê, e entrega ao BDR
uma fila priorizada com roteiro de abordagem. O BDR decide; o resultado do funil ensina o modelo.

> O Fullguete não toma decisão de crédito: ele prioriza prospects comerciais. Projeto acadêmico, sem vínculo com a
> Equifax. Não existe API da Equifax neste projeto: dados que dependeriam dela são simulados e rotulados como tal.
> APIs cadastrais reais: CNPJ.ws para consultas por CNPJ conhecido e LocalizaCNPJ para pesquisa segmentada, quando há chave Free configurada. Nenhum dado Equifax é consultado por API.

## O que tem dentro

| Menu | O que faz |
|---|---|
| Dashboard | Funil cumulativo, alertas (SLA, LGPD, drift, plano B), quentes aguardando ação, soluções e origem |
| Captura de leads | Formulário CNPJ.ws, planilha, lista de CNPJs, pesquisa real com filtros de segmento/cidade/mês de abertura (LocalizaCNPJ), webhook simulado e base fictícia |
| Tratamento IA | ICP versionado, 7 agentes por lote, ficha com nota decomposta e caminho no grafo, revisão humana, exportação |
| Fila do BDR | Metas do dia, fila por SLA e nota, oferta, roteiro com copiar, cadência, BANT, correção da IA, agendamento |
| Carteira | Todos os leads em qualquer etapa; o gestor redistribui |
| CRM & funil | Kanban, oportunidade, passagem ao executivo, linha do tempo de ponta a ponta, feedback para o modelo |
| Assistente IA | Chat com o catálogo (RAG) e o lead em contexto; não executa ações |
| Catálogo de ofertas | 29 soluções Equifax, uso pela IA, knowledge graph e regras editáveis |
| Indicadores | Negócio (conversão, SLA, receita, K-Means) e técnica (modelos, retreino, PSI, latência, custo, plano B) |
| Governança & LGPD | Base legal, opt-out, titular, retenção, auditoria, pesos e limites, checagem de viés |

Documentação para a entrega: [Arquitetura](docs/ARQUITETURA.md) · [Estratégia de IA](docs/ESTRATEGIA_IA.md) ·
[Governança](docs/GOVERNANCA.md) · [Roteiro da demonstração](docs/ROTEIRO_DEMO.md).

## Busca de CNPJs reais por tags

Acesse **Captura de leads → Buscar CNPJs reais**. Configure a chave gratuita da LocalizaCNPJ
em `LOCALIZA_CNPJ_TOKEN` (Secrets do Streamlit ou `.env`) ou digite-a no formulário durante a sessão.

Exemplo: segmento **Varejo**, cidade **Campinas**, UF **SP**, abertura **Abril/2026**.
O filtro de segmento é traduzido em atividade econômica da Receita; para máxima precisão, informe
o código CNAE de 7 dígitos. A consulta aplica os filtros de abertura no servidor, suporta
paginação por cursor e exporta apenas dados cadastrais empresariais em CSV.

A interface permite selecionar resultados e importá-los, com deduplicação de CNPJ. Como dados
cadastrais públicos não equivalem a consentimento, o padrão é `sem_base`: avalie
a base legal em Governança antes de contato. O portal não grava sócios nem dados
pessoais de contato retornados pelo fornecedor. **Sem chave configurada, a pesquisa
não retorna dados**: não há substituição silenciosa por base fictícia.

Fonte técnica: <https://api.localizacnpj.com.br/>. O serviço externo exige cadastro e
possui cota mensal, que pode mudar conforme o provedor. Sem acesso a uma chave válida
não é possível garantir, neste repositório, que um filtro terá resultados reais.

## Como rodar localmente

Requer Python 3.11 ou mais novo.

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # preencha a GEMINI_API_KEY se quiser usar a IA generativa (opcional)
.venv/bin/streamlit run app.py
```

Sem chave, tudo funciona no modo local: nota por TF-IDF e regras, recomendação pelo grafo e roteiros por
modelos de texto. Testes e estilo:

```bash
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

## Variáveis

| Variável | Para que serve | Padrão |
|---|---|---|
| `GEMINI_API_KEY` | Chave do Google Gemini. Sem ela, modo local | vazia |
| `GEMINI_MODEL` | Modelo do Gemini (leve por padrão) | `gemini-3.1-flash-lite` |
| `CNPJ_WS_TOKEN` | Token comercial do CNPJ.ws. Sem ele, API pública (3 consultas por minuto) | vazio |
| `LOCALIZA_CNPJ_TOKEN` | Chave gratuita da LocalizaCNPJ para descobrir CNPJs por atividade, cidade e mês de abertura | vazio |
| `FULLGUETE_DB_PATH` | Caminho do banco SQLite | `data/fullguete_v2.db` |
| `FULLGUETE_MODO` | `simulado` (logins de demonstração e base fictícia) ou `real` | `simulado` |
| `FULLGUETE_LOGINS_DEMO` | Botões de login dos perfis fictícios: `sim`, `nao` ou `auto` (some se houver usuários nos Secrets) | `auto` |
| `FULLGUETE_CENARIO_DEMO` | No modo simulado, monta um mês fictício de operação na primeira abertura (`sim` ou `nao`) | `sim` |

As variáveis podem ficar no `.env` (local, fora do Git) ou nos Secrets do Streamlit Cloud. Nenhuma chave fica no
código.

## Logins de demonstração (só no modo simulado)

A tela de login mostra um botão para cada perfil. Também dá para entrar com usuário e senha
`fullguete-demo`:

| Perfil | Usuário |
|---|---|
| Gestor | `gestor` |
| BDR | `bdr.ana`, `bdr.bruno`, `bdr.carla` |
| Executivo de contas | `executivo` |

Num link público, use `FULLGUETE_LOGINS_DEMO = "nao"` (no padrão `auto`, os botões somem sempre que houver
usuários em `[usuarios]` nos Secrets). Os perfis fictícios continuam existindo para receber a distribuição de
leads, mas sem senha utilizável. No modo real esses logins ficam desativados. Usuários reais vêm dos Secrets, só com o hash da senha:

```toml
[usuarios.maria]
nome = "Maria"
papel = "gestor"   # bdr, gestor ou executivo
senha_hash = "pbkdf2_sha256$600000$..."
```

Para gerar o hash: `.venv/bin/python -m nucleo.auth`.

## Publicar no Streamlit Community Cloud

1. Envie o repositório para o GitHub (o `.gitignore` já exclui `.env`, `secrets.toml`, bancos e modelos).
2. Em <https://share.streamlit.io>, crie o app apontando para `app.py`, com Python 3.11.
3. Em Secrets, cole as variáveis da tabela acima (por exemplo `GEMINI_API_KEY` e `FULLGUETE_MODO = "simulado"`).
4. Faça o deploy. Na primeira abertura a base de demonstração é montada.

O disco do Streamlit Cloud é temporário: o SQLite e os modelos voltam ao estado inicial quando a instância
reinicia. Para uso contínuo, aponte `FULLGUETE_DB_PATH` para um volume persistente.

## Estrutura

```
app.py                     navegação, tema, carga inicial e login
paginas/                   uma página por item do menu
nucleo/                    configuração, login, estados do lead, comercial, revisão, LGPD, componentes de tela
dados/                     ingestão, limpeza, CNPJ.ws, variáveis, base fictícia e cenário de demonstração
ia/                        agentes, orquestrador, provedor LLM, esquemas, grafo, RAG, nota local, propensão,
                           K-Means, drift, observabilidade, assistente e resumo
prompts/v1/                prompt de sistema e exemplo few shot versionados
catalogo/                  catálogo das soluções Equifax e regras do knowledge graph
banco/                     esquema, migrações, conexão, consultas, métricas e carga inicial
modelos/                   modelos treinados e metricas.json (gerados)
tests/                     testes pytest
docs/                      arquitetura, estratégia, governança e roteiro da demonstração
legado/v1/                 código da primeira versão, preservado
```

## Limites do protótipo

- O histórico que treina a propensão é sintético. Com uso real, ele passa a aprender com os resultados do funil.
- Sinais de mercado (vende a prazo, tem e-commerce, volume de pedidos) são simulados e rotulados como simulados.
- Os valores de oportunidade e receita são fictícios.
- O banco é SQLite local, sem concorrência pesada; serve ao protótipo, não a produção.
- Nenhuma mensagem é enviada pelo sistema: roteiros são rascunhos para o BDR.
- A busca de empresas por CNAE e região exige token comercial do CNPJ.ws; a região é só filtro, nunca critério de nota.

## Nova captura real com CNPJá Comercial

O Fullguete oferece a aba **Captura de leads → Buscar empresas (CNPJá)**, separada da
LocalizaCNPJ (legado). Configure `CNPJA_API_KEY` nos Secrets do Streamlit ou
digite temporariamente a chave da **API Comercial** na própria aba; não use a
chave em código ou commits.

**Fluxo de validação:** 1) clique em **Validar chave e consultar saldo (grátis)**
(`GET /credit`), 2) pesquise com `limit=10`, 3) confira resultados e importe
apenas os CNPJs selecionados. O primeiro teste pode ser Varejo, Campinas/SP,
Abril de 2026, CNAE 4711302 (supermercados). A busca usa o código IBGE
do município obtido pela API pública do IBGE; você também pode preencher o
código manualmente caso a consulta ao IBGE esteja indisponível.

A pesquisa usa `GET https://api.cnpja.com/office`, com filtros documentados
`address.state.in`, `address.municipality.in`, `founded.gte`,
`founded.lte`, `mainActivity.id.in` e `status.id.in=2`. O fornecedor cobra
1 crédito por até 10 registros retornados. A tag **Varejo** usa apenas uma
lista ilustrativa de CNAEs: para uma cobertura completa, configure uma
lista mais abrangente de CNAEs conforme a estratégia comercial.

A pesquisa retorna dados de empresas, sem importar sócios ou dados pessoais de
contato; por padrão os registros entram com base legal não validada
(`sem_base`). São deduplicados por CNPJ no pipeline existente. **Os testes
do CI usam respostas simuladas, não comprovam a busca autenticada.** É
necessário validar pelo botão da aba com uma conta comercial habilitada.

Documentação: https://cnpja.com/api

## Campanhas de prospecção e rastreabilidade

A pesquisa CNPJá salva automaticamente filtros, amostra de empresas retornadas, data e
autor, e gera uma tag como `#varejo-campinas-202604-01`. Pode ser reaberta no histórico
sem gastar créditos. A importação de empresas selecionadas vincula os CNPJs à campanha;
se o CNPJ já existia, apenas associa a nova origem, sem criar outro lead. A data de
abertura é preservada no cadastro e as buscas anteriores à migração têm essa informação
recuperada dos registros brutos quando disponível.

Use **Tratamento IA → Todos os leads** para localizar qualquer empresa, inclusive as
retidas por falta de base legal, em revisão e ainda não atribuídas. Os filtros de
campanha aparecem também na lista de tratados, Carteira, Fila do BDR, CRM e
Governança/LGPD. O lead não deve ser apresentado como desaparecido só porque não
está habilitado a seguir para contato.

**Persistência:** o histórico é gravado no SQLite da instalação atual. No Streamlit
Community Cloud, esse sistema de arquivos é efêmero; novos deploys ou reinícios
podem zerar os dados. Para produção e retenção garantida, implante PostgreSQL gerenciado
com migração e backups testados; não considere essa implementação local uma garantia
de persistência definitiva.

**Inteligência comercial:** o prompt `v2` exige separar informações cadastrais
verificadas de hipóteses sobre necessidades e produtos. Sinais comportamentais
simulados são proibidos para CNPJs reais; a IA não inventa faturamento, inadimplência
ou indicadores de risco. O ICP em **Tratamento IA → ICP**, os pesos e limites em
**Governança → Pesos e limites** e as correções de BDR permitem evoluir a
calibração. A propensão de conversão não deve ser interpretada como probabilidade
estatisticamente validada em clientes reais enquanto o modelo depender de treinamento
em base fictícia. Os leads sem base legal para contato continuam retidos e não são
enviados ao LLM, conforme as regras atuais de governança.
