# TRADER AI PRO — Status de implementação

## Etapa atual: integração inicial Twelve Data (Forex)

- Adaptador de leitura Twelve Data em `twelvedata_feed.py`, autenticando por cabeçalho HTTP; a chave não é gravada no código nem enviada nos parâmetros da URL.
- Validação de candles OHLC, timestamps UTC, exclusão do candle ainda aberto, histórico mínimo e atualidade máxima.
- Testes unitários simulados para autenticação, conversão UTC, candle aberto, dados atrasados, histórico insuficiente e erros de cota.
- Worker com seleção explícita/automática de fonte: OTCharts, Twelve Data ou Yahoo.
- Twelve Data inicia com EUR/USD e intervalo mínimo configurado de 120 segundos para manter o consumo estimado dentro do limite diário Basic de 800 créditos, caso cada consulta consuma um crédito.
- Candles Twelve Data são usados apenas para análise técnica. Não fornecem, nesta etapa, preço executável de entrada.
- O worker não avalia registros antigos do histórico com preços de outra fonte; isso evita misturar resultados Yahoo/OTC com Forex agregado.
- Nenhum novo sinal CALL/PUT é publicado ou inserido no histórico nesta etapa.
- `render.yaml` foi preparado, mas não foi feito deploy nem contratado serviço.

## Bloqueios de segurança ainda ativos

1. Cotação ao vivo com timestamp próprio e revalidação obrigatória antes de qualquer entrada.
2. Persistência compartilhada e idempotente do estado do worker/candidatos no Supabase.
3. Painel Streamlit com atualização automática para PC e celular.
4. Validação real do acesso Twelve Data e da lista de símbolos liberados no plano do usuário.
5. Teste de mercado aberto/fechado e observação prolongada antes de considerar qualquer sinal elegível.

## Regras do projeto

- Desenvolvimento somente em `development/automation-ai-foundation`; `main` permanece intocada.
- Não apagar nem alterar o histórico existente.
- Não contratar nem ativar serviços pagos sem autorização expressa.
- Nenhum resultado de teste é considerado aprovado até execução real do pipeline.
