# Modelos

Registro simples de modelos (MLOps). Os arquivos `.joblib` e o `metricas.json` são gerados na primeira
execução e a cada retreino, e ficam fora do Git porque são recriados a partir dos dados.

- `propensao_<banco>_v<N>_<algoritmo>.joblib`: propensão de conversão. A cada treino são registradas as duas
  abordagens (regressão logística e árvore de decisão) e a de maior AUC fica ativa.
- `segmentos_<banco>_v<N>.joblib`: K-Means com os perfis de cliente.
- `metricas.json`: resumo do último treino (versão, comparação entre algoritmos, fontes dos dados).

O registro completo (versão, data, métricas, variáveis, ativo) fica na tabela `modelos_registro` e aparece em
Indicadores, aba Técnica. O botão "Retreinar com os resultados do funil" cria uma versão nova.
