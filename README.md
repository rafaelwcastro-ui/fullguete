# Fullguete · Captura, ranking e área do BDR

Portal em Streamlit que captura empresas via CNPJ.ws ou importa planilhas, limpa os dados e
prioriza cada lead em relação ao **perfil do cliente ideal (ICP)**. O BDR seleciona empresas do
ranking e acompanha a prospecção na própria carteira.

- **IA (Claude, OpenAI ou Gemini)** avalia setor, porte, localização e descrição e devolve nota de 0 a 100 + justificativa.
- O **Gemini** é selecionado por padrão quando sua chave está disponível. A análise local usa similaridade TF-IDF e regras.
- Acesso com **usuário e senha**.
- Carteira por usuário, pipeline, registro de atividades e agenda de retornos em **SQLite**.
- Histórico de rankings e exportação em **CSV/Excel**, com identidade visual Fullguete.

## Fluxo no portal

1. Em **Nova análise**, escolha **API de CNPJ**, **Planilha** ou **Base fictícia**.
2. Revise a base retornada, preencha o perfil do cliente ideal e clique em **Gerar ranking**.
3. No bloco **Enviar leads para minha carteira BDR**, selecione as empresas que deseja trabalhar.
4. Na **Área do BDR**, abra a ficha de uma empresa, atualize a etapa, registre a atividade e programe o retorno.

A carteira mantém as etapas e atividades de cada lead ao receber novas notas do ranking. O histórico de análise
e o acompanhamento do BDR são armazenados em tabelas independentes.

## Captura por CNPJ

- **Buscar empresas por filtros** usa a API Comercial Premium do CNPJ.ws. A busca aceita CNAE principal, UF,
  código IBGE do município e até 25 resultados por vez. Configure `CNPJ_WS_TOKEN` nos Secrets.
  O portal pesquisa CNPJs ativos e busca os cadastros das empresas encontradas.
  [Documentação da pesquisa](https://docs.cnpj.ws/referencia-de-api/api-comercial/pesquisa-de-empresas)
- **Consultar CNPJs conhecidos** recebe uma lista de CNPJs. Com token, usa a consulta comercial. Sem token,
  usa a consulta pública do CNPJ.ws, limitada a três requisições por minuto por IP.
  [Documentação da consulta pública](https://docs.cnpj.ws/referencia-de-api/api-publica/consultando-cnpj)

Os dados de cadastro dependem da fonte. O ranking avalia os campos disponíveis. Telefone, e-mail e CNPJ aparecem
na ficha do BDR e ficam fora do pedido enviado à API de IA.

## Estrutura

```
app.py                     # interface Streamlit
fullguete/
  dados.py                 # leitura de CSV/Excel, padronização e remoção de duplicatas
  captura.py               # busca de empresas e consulta de cadastros no CNPJ.ws
  area_captura.py          # formulário e prévia da base capturada
  score_ia.py              # pontuação com Claude, OpenAI ou Gemini (saída JSON estruturada, lotes paralelos)
  score_local.py           # pontuação local sem IA
  banco.py                 # conexão SQLite, tabelas e histórico de análises
  carteira.py              # carteira por usuário, etapas e atividades
  area_bdr.py              # fila de trabalho, pipeline e edição de fichas
  models.py                # perfil do cliente ideal
data/exemplo_leads.csv     # base fictícia para a demonstração
assets/                    # logo e ícone
.streamlit/config.toml     # tema com as cores da marca
```

## Rodar localmente

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # coloque sua chave (opcional)
.venv/bin/streamlit run app.py
```

## Formato da planilha

Só a coluna de **nome da empresa** é obrigatória. As demais são reconhecidas por nomes comuns:

| Campo | Nomes aceitos |
|---|---|
| empresa | empresa, nome, razao_social, nome_fantasia |
| setor | setor, segmento, ramo, cnae, atividade |
| porte | porte, tamanho (MEI, ME, EPP, Média, Grande) — ou deduzido de `funcionarios` |
| cidade / uf | cidade, municipio / uf, estado |
| descricao | descricao, sobre, observacoes |
| contato | email, telefone, site, cnpj |

## Publicar no Streamlit Community Cloud

1. Crie um repositório no GitHub e envie o projeto (o `.gitignore` já exclui `secrets.toml`, `.venv` e o banco):
   ```bash
   git init && git add . && git commit -m "Fullguete: ranking de leads"
   git branch -M main
   git remote add origin https://github.com/<seu-usuario>/fullguete.git
   git push -u origin main
   ```
2. Em <https://share.streamlit.io>, clique em **Create app**, escolha o repositório, branch `main` e arquivo `app.py`.
3. Em **Advanced settings → Python version**, escolha **3.11**.
4. Em **Secrets**, cole:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."   # opcional
   OPENAI_API_KEY = "sk-..."          # opcional
   OPENAI_MODEL = "gpt-5-mini"        # opcional
   GEMINI_API_KEY = "AIza..."         # opcional
   GEMINI_MODEL = "gemini-3.1-flash-lite"  # opcional
   CNPJ_WS_TOKEN = ""                   # token comercial para pesquisa por filtros

   [usuarios.admin]
   nome = "Rafael"
   senha_hash = "pbkdf2_sha256$600000$..."
   ```
   O jeito mais fácil é copiar o conteúdo do seu `.streamlit/secrets.toml` local.
5. Clique em **Deploy**.

No Streamlit Community Cloud, o arquivo SQLite pode ser perdido quando a instância é substituída. Para usar a
carteira no trabalho diário, execute o portal em um ambiente com volume persistente e aponte a variável
`FULLGUETE_DB_PATH` para o arquivo SQLite nesse volume. O caminho padrão é `data/fullguete.db`.

## Custos e segurança

- Configure as chaves de IA e o token do CNPJ.ws nos *Secrets* do Streamlit.
- O portal exige **usuário e senha**. As senhas ficam só como hash PBKDF2 nos Secrets; após 5 erros
  o login bloqueia por 60 segundos.
- Para criar ou trocar um usuário: `.venv/bin/python -m fullguete.auth <usuario> "Nome"`. A senha aleatória
  gerada vai para `.streamlit/credenciais_locais.txt` (fora do git); depois copie o novo hash para os Secrets.
- Cada análise com IA está limitada a 200 leads (`MAX_LEADS_IA` em `app.py`).
