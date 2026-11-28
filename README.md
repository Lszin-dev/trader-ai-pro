# TRADER AI PRO

Sistema experimental de monitoramento técnico para Forex/opções binárias, com foco em leitura de mercado, rastreabilidade e validação conservadora. O projeto não executa ordens.

## Arquitetura

- `worker.py`: motor contínuo de monitoramento.
- `twelvedata_feed.py`: candles Forex + exchange rate com timestamp e controle de qualidade.
- `strategy.py`: confluência 5M/1M com score técnico explicável.
- `market_guard.py`: evita consumir API durante o fechamento semanal do Forex.
- `monitor_state.py`: publica o estado atual no Supabase, separado do histórico.
- `app.py`: painel Streamlit responsivo para PC/celular, com modo simples e detalhado.
- `historico.py`: histórico legado e estatísticas existentes.

## Fluxo de um candidato

1. O worker lê somente candles fechados e recentes.
2. O 5M precisa manter tendência consistente; o 1M precisa confirmar direção, RSI, momentum e posição do preço.
3. O motor calcula um **score técnico** de 0 a 100. Esse número mede confluência das regras e **não é probabilidade de acerto**.
4. CALL/PUT precisa aparecer em ciclos consecutivos antes da revalidação.
5. No modo Twelve Data, o exchange rate com timestamp é checado antes de marcar o candidato como revalidado no provedor.
6. A cotação da corretora ainda é necessária para considerar uma entrada real executável.

## Variáveis de ambiente

Obrigatórias para o worker Twelve Data:

- `SUPABASE_URL`
- `SUPABASE_KEY` (chave de escrita mantida somente como secret)
- `TWELVE_DATA_API_KEY`
- `DATA_PROVIDER=twelvedata`

Controles principais:

- `TWELVE_DATA_SYMBOLS=EUR/USD`
- `SCAN_INTERVAL_SECONDS=120`
- `MIN_CANDIDATE_CONFIRMATIONS=2`
- `REVALIDATION_COOLDOWN_SECONDS=600`
- `USAGE_CHECK_INTERVAL_SECONDS=900`
- `DAILY_CREDIT_BUDGET=750` (estimativa conservadora por processo, reconciliada com o uso informado pelo provedor; não garante o limite de toda a conta se houver outros consumidores ou reinícios)

Nunca grave chaves no código ou no GitHub.

## Rodar testes

```bash
python -m unittest discover -s tests -v
```

O GitHub Actions também compila os arquivos Python antes de executar os testes.

## Limitações importantes

Twelve Data fornece mercado Forex agregado; não é a cotação oficial da IQ Option e não fornece os mercados OTC exclusivos da corretora. Por isso o sistema mantém candidatos como observação e não transforma automaticamente uma leitura externa em entrada executável.

## Replay histórico experimental (offline)

`python backtest.py dados.csv --output replay_results.csv`

CSV com colunas time,open,high,low,close (time = abertura do candle 1M em UTC). O replay usa somente candles encerrados na decisão, entrada hipotética com atraso de um minuto, expirações 1 e 5 minutos, e rejeita lacunas. Não reproduz latência real, cotação da corretora, payout ou slippage; não comprova lucratividade. Valide com dados fora da amostra e registre a origem do CSV. Nenhum dado real foi coletado automaticamente por esse comando.
