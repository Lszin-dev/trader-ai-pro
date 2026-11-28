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
