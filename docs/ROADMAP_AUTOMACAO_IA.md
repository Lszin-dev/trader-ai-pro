# TRADER AI PRO — Plano de evolução

## Estado da base (auditoria inicial)

A branch de desenvolvimento parte da `main`, preservada sem alterações.

Arquivos identificados:
- `app.py`: interface Streamlit e análise iniciada manualmente por botão.
- `data_feed.py`: Yahoo Finance, seis pares Forex e candles de 1m/5m.
- `indicators.py`: EMA 9/21, RSI, MACD e ATR.
- `strategy.py`: confirmação da tendência em 5m e gatilho em 1m.
- `historico.py`: grava sinais no Supabase, cria registros para expiração de 1 e 5 minutos, avalia pendências e calcula estatísticas.
- `alerts.py`: formata dados de alerta; ainda não envia notificações.
- `requirements.txt`: dependências atuais.

## Objetivo

Evoluir o produto sem interromper a versão Streamlit existente. O sistema deverá identificar oportunidades em múltiplos mercados, comparar a qualidade dos sinais, revalidar antes da entrada, publicar somente sinais confirmados e avaliar os resultados. O módulo de aprendizado só poderá promover modelos após validação fora da amostra.

## Arquitetura proposta

1. **Coletor de mercado**: adaptadores independentes por provedor e classe de ativo. Cada feed deve informar símbolo, mercado, horário, fuso, timeframe, origem e qualidade/atraso dos dados.
2. **Scanner**: percorre uma lista configurável de ativos e registra candidatos e motivos de rejeição, sem transformar toda análise em operação.
3. **Motor de estratégia**: calcula indicadores e pontuação; separa análise de tendência (5m) do gatilho (1m).
4. **Revalidador**: antes de publicar, verifica candle fechado, atualidade do feed, alinhamento temporal e preço efetivo disponível para a entrada.
5. **Registro e avaliador**: persiste candidato, sinal confirmado, preço/horário efetivos e resultado para expirações de 1 e 5 minutos, com idempotência para evitar duplicações.
6. **Worker 24/7**: processo independente da interface, preparado para serviço contínuo na Render. A interface pode ser fechada sem interromper o worker.
7. **Dashboard**: consome dados do banco e mostra sinais, ranking, saúde dos feeds, histórico e estatísticas.
8. **Aprendizado**: começa em modo sombra; treina com resultados concluídos, mantém conjunto temporal de validação, compara com baseline e só promove uma versão após critérios mínimos documentados.
9. **Resiliência**: logs, health checks, retry com limites, controle de duplicidade e backups/exportações testáveis.

## Riscos técnicos que precisam ser tratados antes de sinais ao vivo

- O feed atual contém apenas seis pares Forex via Yahoo Finance; não representa todos os mercados nem garante cotação executável na plataforma de operação.
- O Yahoo Finance não deve ser assumido como fonte de execução ou como cobertura confiável de OTC, índices e todos os criptoativos.
- A rotina atual calcula o horário de entrada como o próximo minuto, mas grava como preço de entrada o fechamento do candle anterior. Isso pode criar divergência entre preço e horário. A nova rotina deve capturar o preço do candle de entrada no instante correto ou descartar a oportunidade.
- A avaliação atual procura o candle iniciado no horário de expiração e usa sua abertura como preço final. A regra deve ser validada contra a convenção da plataforma e o feed escolhido.
- O avaliador atual é chamado durante uma análise manual. No novo desenho, ele será executado pelo worker independentemente da interface.
- O histórico atual grava duas linhas (1m e 5m) para cada sinal; a nova implementação deve preservar essa semântica ou migrar com cuidado, usando identificador de grupo para relacionar as duas expirações.
- A chave Supabase usada pelo servidor deve ser segredo de ambiente; nunca deve ser publicada no repositório ou no frontend.

## Fases de implementação

### Fase 0 — Segurança e compatibilidade
- Manter `main` intocada.
- Criar branch de desenvolvimento.
- Revisar schema, políticas/permissões e comportamento atual do histórico.
- Definir contratos de dados e testes.

### Fase 1 — Motor automático limitado
- Worker independente.
- Scanner inicial somente para os seis pares já cadastrados.
- Revalidação obrigatória e controle de duplicidade.
- Registro de candidatos, sinais e resultados.
- Modo de observação/paper trading; sem execução financeira automática.

### Fase 2 — Cobertura de mercados
- Adicionar provedores e ativos por classe (Forex, cripto, índices etc.) somente quando houver fonte adequada, timestamps consistentes e disponibilidade documentada.
- Não misturar símbolos de provedores diferentes sem normalização e validação.

### Fase 3 — Dashboard e operação
- Dashboard separado do worker.
- Ranking comparativo, métricas por ativo/estratégia/expiração e monitoramento de saúde.
- Alertas e controles de pausa.

### Fase 4 — Aprendizado validado
- Dataset de candidatos e resultados.
- Treino temporal sem vazamento de dados.
- Comparação com estratégia-base e teste em modo sombra.
- Promoção manual/registrada de versões; rollback disponível.

## Critérios de segurança

- Nenhuma ordem será enviada automaticamente nesta etapa.
- Ausência de dados, feed atrasado, candle incompleto ou divergência de relógio implica não emitir sinal.
- O sistema não deve prometer taxa de acerto nem rentabilidade.
- Alterações de banco serão aditivas e acompanhadas de migrações reversíveis sempre que possível.
- Segredos ficam exclusivamente nas variáveis de ambiente/secret manager.
