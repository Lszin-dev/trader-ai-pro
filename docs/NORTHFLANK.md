# Northflank — worker de monitoramento

Selecione serviço Combined, branch development/automation-ai-foundation, Dockerfile do repositório, contexto / e caminho /Dockerfile. O CMD padrão já inicia python worker.py. O serviço não precisa de porta pública, domínio nem health check HTTP. Use uma única instância e o plano gratuito exibido no painel.

Variáveis de runtime (não de build):

- DATA_PROVIDER=twelvedata
- TWELVE_DATA_SYMBOLS=EUR/USD
- SCAN_INTERVAL_SECONDS=120
- DAILY_CREDIT_BUDGET=750
- MIN_CANDIDATE_CONFIRMATIONS=2
- REVALIDATION_COOLDOWN_SECONDS=600
- USAGE_CHECK_INTERVAL_SECONDS=900
- RESEARCH_ENABLED=true somente após migração e validação das permissões
- SUPABASE_URL, SUPABASE_KEY (credencial de escrita), TWELVE_DATA_API_KEY: segredos de runtime, nunca no GitHub ou no Dockerfile.

Após deploy, confira os logs e as linhas _WORKER e FOREX:EURUSD na tabela monitoramento_estado. No sábado, espera-se mercado fechado e heartbeat sem consumo da Twelve Data. Em mercado aberto, confira a atualização do candle e a resposta do provedor. O Streamlit deve usar a mesma base e a branch atualizada. Nenhum deploy ou cobrança foi realizado pelo commit.
