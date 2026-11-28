# Backup e recuperação — TRADER AI PRO

## Escopo

Exportação lógica somente leitura de historico_sinais, monitoramento_estado e pesquisa_sinais. O arquivo é autenticado e cifrado com Fernet antes de ser gravado; nenhuma linha é enviada em texto puro para o armazenamento externo. O exportador verifica contagens e duplicatas e falha se a leitura está incompleta. Alterações simultâneas ainda podem causar inconsistência entre tabelas: não é um snapshot transacional do PostgreSQL, nem inclui funções, políticas, auth, storage ou configurações de projeto.

## Configuração

1. Execute a migração pesquisa_sinais no Supabase (se ainda não executou).
2. Em uma máquina confiável com Python, instale as dependências do projeto e de backup: `python -m pip install -r requirements.txt -r requirements-backup.txt`.
3. Configure SUPABASE_URL, SUPABASE_KEY (somente no servidor) e BACKUP_ENCRYPTION_KEY como segredos de ambiente. Gere a chave de criptografia localmente com `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Guarde-a em um gerenciador de senhas separado do destino; sem ela não há recuperação.
4. Teste: `python backup.py create`. Se pesquisa_sinais ainda não existe, use `python backup.py create --without-research` temporariamente.
5. Valide a cópia: `python backup.py verify CAMINHO_DO_ARQUIVO.fernet`. O comando só verifica e mostra contagens; nunca restaura ou altera a base.

## Cópia independente na nuvem

Configure um bucket S3 compatível privado, separado do projeto Supabase, com versionamento, acesso mínimo de put/get no prefixo trader-ai-pro/ e bloqueio de acesso público. Configure BACKUP_S3_BUCKET, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION e, se necessário, BACKUP_S3_ENDPOINT. Use credenciais temporárias quando disponíveis. Não armazene a chave de criptografia junto dos arquivos. Confirme custos, limites, direitos de retenção e licença dos dados do fornecedor antes de ativar a cópia.

Execute `python backup.py create --cloud`. O programa lê novamente o objeto cifrado e compara SHA-256. Se a nuvem falhar, a cópia local permanece e o processo termina com erro. Não exclui cópias antigas.

## Automatização

Em um servidor confiável independente do computador, agende o comando acima uma vez ao dia (por exemplo 03:00 UTC) com cron/serviço de agendamento e credenciais no gerenciador de segredos. O agendador deve alertar em caso de código de saída diferente de zero. Use retenção aprovada e faça verificações regulares. Não coloque segredos em logs, GitHub ou linha de comando. Não agende a rotina no worker de mercado: o backup não deve bloquear os ciclos de análise.

## Recuperação

Primeiro valide a cópia cifrada com verify e compare as contagens esperadas. Para restauração completa, prefira backup nativo PostgreSQL consistente e ensaie em projeto separado. Esta versão não possui importador destrutivo nem promete recuperação integral. Nenhuma rotina agendada, bucket ou backup real foi criado automaticamente.
