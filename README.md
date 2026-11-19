# Fullguete · Ranking de Leads com IA

Portal em Streamlit que recebe uma planilha de empresas, limpa os dados e gera um ranking de
prioridade comparando cada lead com o **perfil do cliente ideal (ICP)**.

- **Claude (Anthropic)** avalia setor, porte, localização e descrição e devolve nota de 0 a 100 + justificativa.
- **Sem chave de API**, o portal usa uma análise local (similaridade TF-IDF + regras).
- Acesso com **usuário e senha**.
- Histórico em **SQLite**, exportação em **CSV/Excel**, identidade visual Fullguete.

## Estrutura

```
app.py                     # interface Streamlit
fullguete/
  dados.py                 # leitura de CSV/Excel, padronização e remoção de duplicatas
  score_ia.py              # pontuação com Claude (saída JSON estruturada, lotes paralelos)
  score_local.py           # pontuação local sem IA
  banco.py                 # histórico em SQLite
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
   ANTHROPIC_API_KEY = "sk-ant-..."

   [usuarios.admin]
   nome = "Rafael"
   senha_hash = "pbkdf2_sha256$600000$..."
   ```
   O jeito mais fácil é copiar o conteúdo do seu `.streamlit/secrets.toml` local.
5. Clique em **Deploy**.

> **Atenção:** no Streamlit Community Cloud o disco é temporário. O histórico em SQLite é apagado quando o
> app reinicia ou dorme por inatividade. Para a apresentação isso basta; para guardar dados de forma
> permanente, troque o SQLite por um Postgres gratuito (Supabase ou Neon).

## Custos e segurança

- A chave da Anthropic fica só nos *Secrets*, nunca no código.
- O portal exige **usuário e senha**. As senhas ficam só como hash PBKDF2 nos Secrets; após 5 erros
  o login bloqueia por 60 segundos.
- Para criar ou trocar um usuário: `.venv/bin/python -m fullguete.auth <usuario> "Nome"`. A senha aleatória
  gerada vai para `.streamlit/credenciais_locais.txt` (fora do git); depois copie o novo hash para os Secrets.
- Cada análise com IA está limitada a 200 leads (`MAX_LEADS_IA` em `app.py`).
