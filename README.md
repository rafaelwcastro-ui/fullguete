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
> A única API real é a do CNPJ.ws.

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
