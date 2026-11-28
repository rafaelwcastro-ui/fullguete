# Direção visual aprovada — Fullguete 3.0

Referência aprovada: dashboard dark de cartões quase pretos sobre faixa superior com degradê verde–ciano e menu lateral ativo em degradê. Adaptação própria do Fullguete, sem copiar marca ou imagens de terceiros.

- Remover banner de marketing e dar prioridade aos indicadores.
- Usar menu curto e hierarquia visual, uma cor primária e cores semânticas.
- Navegação de prévia: Visão geral, Prospecção (Busca, Campanhas, Qualificação, Revisão), Central de trabalho (Minha fila, Todos os leads, Triagem), CRM (Kanban, Agenda), Analytics e Administração.
- Dados e ficha de exemplo são somente leitura; a navegação, os filtros e a seleção de ficha funcionam localmente. Não simular chamadas a APIs ou mudanças de status.
- A camada atual de autenticação usa estado de sessão do Streamlit. Não reutilizar sessões implicitamente em Next.js. O conector SQLite atual pode migrar a base ao abrir, mesmo para consultas: não conectá-lo a uma aplicação experimental usando o arquivo em produção.
- Primeiro contrato de integração será o funil agregado do banco de demonstração, em um snapshot de leitura, seguido por API autenticada e testes por perfil. Nenhuma chave ou registro real deve ser disponibilizado ao navegador antes dessa fase.
- Preservar a identidade oficial: esta prévia usa ícone temporário; usar assets existentes na homologação.
