# Fullguete — prévia de interface
Esta aplicação Next.js é isolada do Streamlit. Não lê SQLite, não usa credenciais, não chama APIs de CNPJ ou IA e não modifica registros reais. O conjunto de dados é integralmente fictício e está identificado na tela. Não é uma substituição funcional do portal.

## Executar
Node.js 20.9+ (preferir LTS compatível com Next.js 16).
```sh
cd frontend
npm install
npm run typecheck
npm run build
npm run dev
```
Abra http://localhost:3000. A interface inclui filtro de período ilustrativo, busca local de empresas de exemplo, indicadores, gráfico e pipeline responsivo. A navegação operacional completa ainda não foi migrada.

## Stack
Next.js App Router, React, TypeScript, Tailwind 4, Lucide, Recharts. Configuração para shadcn/ui e um componente Card local seguindo a convenção de componentes copiáveis; não houve execução do CLI. Tremor deve ser adotado seletivamente por componentes copiados e validados, sem adicionar um segundo sistema de design ou misturar versões incompatíveis de Tailwind/Recharts. Esta primeira prévia utiliza Recharts diretamente.

## Segurança e migração
Não publicar este frontend como produção. Não incluir dados de clientes ou chaves em JavaScript. Antes de integrar, definir API Python autenticada (por exemplo FastAPI), testar autorização por perfil e escopo, proteger dados e aplicar o mesmo serviço de transição e regras LGPD existente. Preservar arquivos operacionais e contratos. Somente substituir a interface anterior após testes e homologação. A persistência SQLite no Streamlit Cloud é efêmera, conforme README principal; não migrar dados sem backup e estratégia validada.
