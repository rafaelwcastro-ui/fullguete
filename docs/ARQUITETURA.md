# Arquitetura do Fullguete

O Fullguete é um protótipo em Streamlit que leva o lead da captura ao fechamento. A IA qualifica, recomenda a
solução Equifax e escreve o roteiro; o BDR decide; o resultado do funil volta para o modelo aprender.

## 1. Pipeline de dados em 4 etapas

```mermaid
flowchart LR
    subgraph I[1. Ingestão]
        F[Formulário manual<br/>tempo real]
        W[Site / webhook<br/>simulado, tempo real]
        P[Planilha CSV e Excel<br/>lote]
        C[Lista de CNPJs<br/>API CNPJ.ws real]
        B[Base fictícia]
    end
    subgraph T[2. Transformação]
        L[Limpeza e padronização<br/>CNPJ, telefone, e-mail, UF, porte]
        D[Deduplicação<br/>CNPJ ou nome + cidade + UF]
        S[Separação dos dados pessoais]
        FE[Engenharia de variáveis<br/>segmento, sinais, porte]
    end
    subgraph A[3. Armazenamento SQLite]
        BR[(Bronze<br/>leads_brutos)]
        PR[(Prata<br/>leads + contatos)]
        OU[(Ouro<br/>leads_features)]
    end
    subgraph K[4. Consumo]
        PG[Páginas do app]
        EX[Exportação CSV e Excel]
        ML[Modelos e Indicadores]
    end
    F & W & P & C & B --> BR --> L --> D --> S --> PR --> FE --> OU --> PG & EX & ML
```

Toda origem passa por `dados/ingestao.py`: grava o registro como chegou (bronze), aplica as regras de entrada
(campo obrigatório, deduplicação e base legal), cria o lead limpo (prata) e separa nome, e-mail e telefone do
contato na tabela `contatos`. As variáveis do modelo (ouro) são geradas pelo Agente de Enriquecimento.

## 2. Fluxo de agentes do tratamento

```mermaid
flowchart TB
    A1[1. Higienização<br/>valida CNPJ, remove dados pessoais de campos livres] --> A2
    A2[2. Enriquecimento<br/>CNPJ.ws real com cache + sinais simulados rotulados] --> A3
    A3{3. Risco e conformidade<br/>base legal, opt-out, empresa inativa}
    A3 -- sem base legal ou opt-out --> R[Retido LGPD<br/>a IA não é chamada]
    A3 -- ok ou com alerta --> A4
    subgraph LLM[Uma chamada ao Gemini por lote de até 15 leads]
        A4[4. Qualificação<br/>aderência ao ICP] --> A5[5. Recomendador<br/>escolhe entre as candidatas do grafo]
        A5 --> A6[6. Redator<br/>perguntas, roteiro e objeções]
    end
    G[(Knowledge graph<br/>segmento → sinal → solução)] -- RAG: só as candidatas --> A5
    M[Propensão supervisionada<br/>e K-Means] --> A4
    A6 --> V{JSON válido e<br/>ids dentro das candidatas?}
    V -- não, 2 tentativas --> PB[Plano B local<br/>TF-IDF + regras + modelos de texto]
    V -- sim --> A7
    PB --> A7[7. Supervisor, sem LLM<br/>nota final, classe, destino, BDR de menor fila]
    A7 --> Q[Na fila do BDR] & H[Revisão humana] & N[Em nutrição] & X[Descartado]
```

Regras que o orquestrador (`ia/orquestrador.py`) garante:

- Nenhum agente envia mensagem nem muda etapa por conta própria. Só o Supervisor grava o destino, por regras.
- Nome, e-mail, telefone e localização nunca vão para o LLM (há teste automatizado para isso).
- Cada etapa de cada lead fica em `tratamento_etapas`, e cada chamada em `eventos_ia`.

## 3. Ciclo de MLOps

```mermaid
flowchart LR
    H[(Histórico de resultados<br/>rotulos_treino)] --> TR[Treino<br/>regressão logística x árvore]
    TR --> REG[(Registro<br/>modelos_registro + modelos/)]
    REG --> PRED[Propensão no tratamento]
    PRED --> FUN[Funil: BDR e executivo]
    FUN -- Ganho ou Perdido --> H
    FUN -- correções do BDR --> CON[Taxa de concordância]
    PRED --> MON[Monitoramento<br/>PSI, latência, custo, plano B]
    MON -- alerta de drift --> TR
```

O histórico começa com 500 leads sintéticos. Cada Ganho ou Perdido do funil entra como exemplo novo, e o botão
"Retreinar com os resultados do funil" (Indicadores) registra uma versão nova e ativa a de maior AUC.

## 4. Camada, tecnologia e arquivo

| Camada | Tecnologia | Arquivo |
|---|---|---|
| Interface e navegação | Streamlit (`st.navigation`) | `app.py`, `paginas/`, `estilo/tema.css`, `.streamlit/config.toml` |
| Login e perfis | PBKDF2 (hashlib) | `nucleo/auth.py` |
| Configuração e segredos | python-dotenv, Secrets do Streamlit | `nucleo/config.py`, `.env.example` |
| Ingestão | Pandas, Requests | `dados/ingestao.py`, `dados/cnpjws.py` |
| Transformação | Pandas, regex | `dados/limpeza.py`, `dados/cnpj.py`, `dados/features.py` |
| Armazenamento | SQLite com migrações | `banco/esquema.sql`, `banco/migracoes/`, `banco/conexao.py` |
| Máquina de estados | Python | `nucleo/estados.py` |
| Agentes e orquestração | Python | `ia/agentes.py`, `ia/orquestrador.py` |
| LLM | Google Gemini (google-genai) | `ia/provedor.py` |
| Prompts versionados | Markdown + few shot | `prompts/v1/` |
| Saída estruturada | Pydantic | `ia/esquemas.py` |
| RAG e knowledge graph | NetworkX, scikit-learn (TF-IDF) | `ia/grafo.py`, `ia/rag.py`, `catalogo/regras_grafo.json` |
| Nota local e plano B | scikit-learn (TF-IDF) | `ia/score_local.py`, `ia/plano_b.py` |
| Supervisionado | scikit-learn (LogisticRegression, DecisionTree) | `ia/propensao.py` |
| Não supervisionado | scikit-learn (KMeans) | `ia/segmentos.py` |
| Observabilidade e drift | SQLite, NumPy (PSI) | `ia/observabilidade.py`, `ia/drift.py` |
| Comercial e LGPD | Python | `nucleo/comercial.py`, `nucleo/revisao.py`, `nucleo/lgpd.py` |
| Indicadores | Pandas, Plotly | `banco/metricas.py`, `paginas/indicadores.py` |
| Qualidade e CI | pytest, ruff, GitHub Actions | `tests/`, `pyproject.toml`, `.github/workflows/ci.yml` |

## 5. Estados do lead

`Capturado → Em tratamento → Tratado → (Na fila do BDR | Em nutrição | Revisão humana | Descartado | Retido LGPD)
→ Em contato → Qualificado → Reunião marcada → Proposta → Ganho | Perdido`

As transições permitidas estão em `nucleo/estados.py`. Toda mudança grava quem, quando, de onde, para onde e o
motivo. Perdido e Descartado exigem motivo da lista. Com opt-out, nenhuma etapa de contato é aceita.

## 6. Custo de escala

- Modelo leve por padrão (`GEMINI_MODEL=gemini-3.1-flash-lite`), configurável.
- Até 15 leads por chamada (`tamanho_lote_ia`), com uma única chamada para qualificação, recomendação e redação.
- Cache por empresa: a mesma empresa, com o mesmo prompt, ICP e candidatas, não paga duas vezes.
- Leads retidos por LGPD não chegam ao LLM.
- Custo por lead e por 1.000 leads visível em Indicadores. No teste real, 6 leads custaram US$ 0,0025 em 11 s.
