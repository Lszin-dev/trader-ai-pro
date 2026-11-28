# TRADER AI PRO — Status de implementação

Atualizado em 28/11/2026.

## Estrutura concluída na branch de desenvolvimento

- Migração `monitoramento_estado` executada no Supabase e mantida separada de `historico_sinais`.
- Feed Twelve Data com autenticação por header, validação de candles fechados, atualidade e integridade OHLC.
- Revalidação adicional por `exchange_rate`, com preço e timestamp próprios do provedor.
- Estratégia 5M/1M revisada: persistência de tendência, momentum, RSI, posição do preço, volatilidade e score técnico explicável.
- Confirmações consecutivas obrigatórias antes de tentar revalidar um candidato CALL/PUT.
- Guard de horário de Forex baseado em Nova York, evitando consumo da API durante o fechamento semanal.
- Guard de cota diária para evitar consumir o restante do plano Basic quando o uso se aproxima do limite.
- Estado compartilhado leva score, métricas, confirmações, atraso do feed, revalidação e até 60 preços recentes no JSON `detalhes`, sem nova migração.
- Painel Streamlit revisado para celular/PC, com modo simples e modo detalhado e atualização isolada a cada 15 segundos.
- Gráfico recente pode ser renderizado a partir do estado do worker, sem colocar a API key no navegador/app.
- Worker registra falha de ciclo no estado `_WORKER`, evitando ficar aparentemente “executando” após exceção de inicialização.
- CI compila os arquivos Python e executa a suíte unitária.

## Segurança e integridade mantidas

- Nenhum segredo é gravado no repositório.
- Nenhum novo CALL/PUT da Twelve Data é inserido automaticamente em `historico_sinais`.
- O histórico existente não é apagado nem migrado.
- O score técnico não é tratado como probabilidade de acerto.
- Revalidação na Twelve Data não é tratada como cotação oficial da corretora.
- Operações reais continuam fora do escopo do worker.

## Próximo passo operacional

O código está preparado para receber no ambiente do worker `SUPABASE_URL`, `SUPABASE_KEY` e `TWELVE_DATA_API_KEY`. Depois do deploy, a validação deve ser feita em mercado Forex aberto, começando por EUR/USD e observação/paper trading.

A configuração `render.yaml` permanece com `autoDeploy: false`; nenhum serviço externo é contratado ou ativado pelo código do repositório.

## Revisão de confiabilidade adicional

- Confirmações exigem candles distintos e dentro do intervalo esperado; dados OHLC inconsistentes são rejeitados.
- RSI trata corretamente tendências sem perdas e séries sem movimento.
- Revalidação expira na interface conforme o timestamp da cotação, não o horário do último ciclo.
- Guard local de orçamento diário (750 créditos estimados por processo, sincronizado com snapshots da API; não é uma garantia de uso global).
- Worker em observação não atualiza nem insere histórico legado, inclusive nas fontes alternativas.
- Replay offline em `backtest.py`, com candles fechados, atraso hipotético e avaliações 1M/5M. Ainda não há avaliação ao vivo dos novos candidatos, coleta de dataset real, backup recorrente ou modelo ML treinado.

## Pesquisa prospectiva (nova fase, desligada por padrão)

- Migração separada `supabase/migrations/20261128_pesquisa_sinais.sql`; precisa ser executada no Supabase. Dataset privado com RLS, sem acesso anon/authenticated.
- `research.py` registra duas avaliações por candidato revalidado, com versão, fonte, ativo, features, horário de observação e próxima abertura de minuto estritamente futura. Chave composta evita duplicatas.
- Avaliação usa somente aberturas exatas de candles encerrados da mesma fonte; falta de dados não vira erro/acerto. Sem histórico suficiente após tolerância, marca SEM_DADOS. Não equivale a uma operação real nem usa preços da IQ Option.
- `RESEARCH_ENABLED=true` somente após migração e confirmação de permissão de escrita no worker. O painel consulta contagens exatas com credencial de serviço no servidor, sem expor a chave.
- Machine learning, backup recorrente e testes reais de conexão ainda pendentes; não há dataset de mercado coletado por esta alteração.

- Exportador `dataset_export.py` prepara amostras locais por fonte/ativo/versão, com corte cronológico e expurgo de horizontes que cruzam o início do teste. Nenhum modelo treinado ou dataset real exportado nesta etapa. O CSV é privado e ignorado pelo Git.
- A migração também exige que a abertura hipotética seja posterior ao registro no servidor, para evitar cadastrar entradas retroativas.

## Backup — preparação

- `backup.py` exporta as tabelas de aplicação sem modificar dados, cifra e autentica a cópia, valida contagens/chaves e permite envio opcional a bucket privado com verificação por leitura. Limite de 100 mil linhas por tabela e 64 MiB de JSON; não é backup transacional nem inclui todo o projeto. `docs/BACKUP.md` documenta configuração, agendamento e recuperação. Ainda não há bucket, credenciais, backup real, agendamento ou ensaio de restauração.
