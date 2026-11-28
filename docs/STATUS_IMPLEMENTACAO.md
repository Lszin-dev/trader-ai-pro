# TRADER AI PRO — Status de implementação

## Entregue nesta etapa

- Validador independente de preço e timestamp de cotação em `entry_validation.py`.
- Testes unitários do validador em `tests/test_entry_validation.py`.
- Adaptador de dados OTCharts em `otcharts_feed.py`, com catálogo de ativos, candles 1M/5M, conversão de timestamp, validação de mercado aberto, lacunas e atualidade.
- Worker independente em `worker.py`, com modo OTCharts opcional e fallback para a fonte antiga Yahoo Finance.
- Scanner de símbolos configurável por venue e lista dinâmica, com limite inicial de cinco ativos.
- Construção local de candles 5M a partir dos candles 1M para reduzir consumo de requisições.
- Avaliação automática de sinais pendentes pelo worker, sem depender do botão do Streamlit.
- Configuração inicial do Background Worker da Render em `render.yaml`, sem deploy automático.
- Pipeline de testes no GitHub Actions.

## Fonte de dados e limites comerciais

A IQ Option não publica uma API oficial para desenvolvedores. OTCharts é um serviço independente, somente leitura, que afirma disponibilizar candles e preços da própria plataforma sem exigir senha ou sessão da corretora. Ele não executa operações nem acessa saldo.

A documentação consultada informa que o plano gratuito tem 200 requisições no primeiro mês, sem streaming; os planos pagos começam em US$ 15/mês. Para IQ Option, cada stream aceita um único instrumento por conexão. Portanto, monitorar muitos ativos simultaneamente exige dimensionar plano, quantidade de streams ou requisições. O worker começa limitado a cinco símbolos e uma consulta por símbolo a cada ciclo; não se deve ativar uma lista ampla sem verificar a cota diária da conta.

O catálogo deve ser consultado dinamicamente. Um ativo listado não significa que esteja aberto para negociação. Candles com lacunas, mercado fechado, histórico insuficiente ou feed atrasado são rejeitados.

## Bloqueio de segurança

O worker **não publica nem registra novos sinais CALL/PUT**. Ele identifica candidatos e os registra no log como não publicados. A publicação depende da integração de uma cotação ao vivo com timestamp próprio, revalidação no instante da entrada e persistência idempotente. Não se deve usar o fechamento do candle anterior como preço de uma entrada futura.

## Antes de ativar o monitoramento 24/7

1. Definir a venue correta (IQ Option, Pocket Option, Quotex ou mercado Forex) e validar os símbolos no catálogo.
2. Obter uma chave OTCharts e selecionar um plano que suporte a cobertura desejada; nenhuma assinatura foi contratada.
3. Dimensionar requisições/streams antes de aumentar o número de ativos.
4. Completar a rotina de entrada com preço/timestamp do tick ao vivo e revalidação imediatamente antes da publicação.
5. Validar a regra de preço de expiração com candles da mesma venue.
6. Executar testes automatizados e observação; não considerar a estratégia validada apenas por testes unitários.
7. Configurar `SUPABASE_URL`, `SUPABASE_KEY` e `OTCHARTS_API_KEY` nos segredos da Render.
8. Só então contratar/ativar o Background Worker. O arquivo de configuração não faz deploy nem contrata serviço.

## Limites atuais

- Sem chave OTCharts, o worker usa apenas seis pares Forex via Yahoo Finance.
- Com OTCharts, o padrão é venue `iq` e no máximo cinco ativos por ciclo.
- Não há execução automática de ordens.
- `main` permanece preservada; desenvolvimento ocorre somente na branch de automação.
