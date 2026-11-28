# TRADER AI PRO — Status de implementação

## Entregue nesta etapa

- Validador independente de preço e timestamp de cotação em `entry_validation.py`.
- Testes unitários do validador em `tests/test_entry_validation.py`.
- Worker independente em `worker.py`, sem depender da interface Streamlit para executar ciclos de monitoramento.
- Configuração inicial do Background Worker da Render em `render.yaml`, com deploy automático desativado e segredos configurados para preenchimento no painel.
- Monitoramento inicial dos seis símbolos atualmente suportados pelo adaptador Yahoo Finance.
- Avaliação automática de sinais pendentes pelo worker, sem depender do clique no botão da aplicação.

## Bloqueio de segurança identificado

O provedor atual retorna candles históricos e não fornece, no contrato atual do projeto, uma cotação executável independente com timestamp próprio para registrar o preço real no instante da entrada. Portanto, o worker **não publica nem registra novos sinais CALL/PUT**. Ele identifica candidatos e os registra no log como não publicados.

Isso é intencional: usar o fechamento do candle anterior como preço de uma entrada futura produziria resultados potencialmente incorretos. O módulo `entry_validation.py` está pronto para validar uma cotação quando um adaptador compatível for integrado.

## Antes de ativar a assinatura da Render

1. Integrar um provedor de cotações adequado à plataforma/mercado pretendido, com timestamp e preço verificáveis.
2. Integrar revalidação imediatamente antes da publicação e persistência idempotente.
3. Validar a regra de preço de expiração e a convenção de horário com dados reais da fonte escolhida.
4. Executar testes automatizados e ciclos de observação; não considerar a estratégia validada apenas por testes unitários.
5. Confirmar variáveis `SUPABASE_URL` e `SUPABASE_KEY` no ambiente privado da Render.
6. Só então contratar/ativar o Background Worker. O arquivo de configuração não faz deploy nem contrata serviço.

## Limites atuais

- Seis pares Forex do Yahoo Finance; sem OTC, índices ou cobertura global.
- O worker opera em modo de observação e avaliação de histórico.
- Nenhuma ordem é enviada e nenhum resultado financeiro é garantido.
- `main` permanece preservada; desenvolvimento ocorre nesta branch.
