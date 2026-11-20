# Governança, ética e LGPD

## Princípio central

**O Fullguete não toma decisão de crédito.** Ele prioriza prospects comerciais para o time que vende as soluções
Equifax. Decisões de crédito são do cliente, usando essas soluções. Nenhum agente envia mensagem, muda etapa por
conta própria ou fecha negócio.

## LGPD aplicada

| Exigência | Como o Fullguete atende | Onde |
|---|---|---|
| Base legal | Todo lead entra com base legal (consentimento ou legítimo interesse). Sem base, fica Retido LGPD e não recebe contato | Captura, Agente de Risco, Governança |
| Consentimento | Formulário registra a base legal e o aceite; tabela `consentimentos` guarda quem, quando e por qual canal | `dados/ingestao.py` |
| Opt-out | Tira o lead de todas as filas, encerra a cadência e bloqueia novos contatos (testado) | `nucleo/lgpd.py` |
| Minimização | Dados pessoais do contato em tabela separada; nunca vão ao LLM; e-mails e telefones digitados em campos livres são removidos antes do envio | `dados/limpeza.py`, `ia/agentes.py` |
| Direitos do titular | Exportação em JSON e exclusão dos dados pessoais (a empresa e a auditoria ficam) | Governança, aba Titular |
| Retenção | Prazo configurável; ao aplicar, remove dados pessoais de leads parados | Governança, aba Retenção |
| Prestação de contas | Trilha de auditoria de decisões da IA, revisões, correções, mudanças de etapa e configurações | tabela `auditoria` |

## Ética, viés e explicabilidade (XAI)

- **Explicabilidade:** toda nota mostra quanto veio da aderência, da propensão e da confiança, a justificativa
  em português e o caminho no grafo (segmento → sinal → solução). A versão do modelo e do prompt fica gravada.
- **Sem segmentação territorial:** UF e município não entram na nota nem nas variáveis do modelo. Servem só como
  filtro, para não penalizar regiões.
- **Checagem de viés:** a página Governança compara a distribuição de notas e a conversão por segmento e porte.
- **Dados sintéticos rotulados:** a base fictícia e os sinais simulados aparecem com selo na interface.
- **Sem invenção de produto:** o LLM só pode recomendar soluções entre as candidatas recuperadas do catálogo;
  qualquer outro id é rejeitado pela validação.

## Human in the loop

1. **Revisão humana obrigatória** para casos de baixa confiança, risco (empresa inativa, dados insuficientes) ou
   quando a própria IA pede revisão.
2. **Correção pelo BDR:** o BDR concorda ou discorda da solução e da classificação, com motivo. Isso gera a taxa
   de concordância BDR x IA.
3. **Rascunhos, não mensagens:** roteiros e e-mails são rascunhos com botão de copiar. O sistema não envia nada.
4. **Pesos e limites** da nota ficam com o gestor, com histórico de quem mudou, quando e por quê.

## Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| LLM inventa produto ou dado | Recomendação errada | RAG com candidatas fechadas, validação Pydantic, rejeição de ids fora da lista, temperatura baixa |
| JSON inválido ou API fora do ar | Lead sem tratamento | Nova tentativa com a mensagem de erro e plano B local; evento registrado |
| Vazamento de dado pessoal para o LLM | Violação da LGPD | Separação de tabelas, remoção em campos livres, teste automatizado |
| Contato sem base legal | Sanção e dano de marca | Agente de Risco retém o lead antes da IA; máquina de estados bloqueia contato com opt-out |
| Modelo treinado em dados sintéticos | Propensão pouco realista | Aviso na interface, retreino com resultados reais do funil, comparação de dois algoritmos |
| Drift no perfil dos leads | Notas perdem qualidade | PSI semanal com alerta no Dashboard e em Indicadores |
| Viés por segmento ou porte | Tratamento desigual | Checagem de viés, localização fora da nota, revisão de pesos com histórico |
| Custo de API em escala | Inviabilidade | Modelo leve, lotes de 15, cache por empresa, custo por lead visível |
| Prompt injection pelos dados da empresa | Comportamento inesperado | Prompt trata dados como informação e não instruções; saída restrita ao esquema |
