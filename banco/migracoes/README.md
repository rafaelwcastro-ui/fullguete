# Migrações

O `banco/esquema.sql` é a versão 1 do banco. Cada mudança posterior vira um arquivo nesta pasta,
com número crescente: `002_descricao.sql`, `003_descricao.sql` e assim por diante.

Ao abrir a conexão, `banco/conexao.py` confere a tabela `esquema_versao` e aplica, em ordem, só
as migrações que ainda não rodaram. Uma migração nunca é editada depois de aplicada: para corrigir,
crie a próxima.
