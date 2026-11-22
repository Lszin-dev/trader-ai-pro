
import streamlit as st
import pandas as pd

from data_feed import get_market_data
from indicators import calculate_indicators
from strategy import analyze_market

from historico import (
    registrar_sinal,
    avaliar_sinais_pendentes,
    obter_estatisticas
)


st.set_page_config(
    page_title="TRADER AI PRO",
    page_icon="📈",
    layout="wide"
)

st.title("📈 TRADER AI PRO")
st.subheader("Análise técnica inteligente")

st.info(
    "O gráfico de 5 minutos confirma a tendência. "
    "O gráfico de 1 minuto procura o momento de entrada."
)

# ==================================
# PAINEL DE ESTATÍSTICAS
# ==================================

st.divider()
st.header("📊 Desempenho dos sinais")

def mostrar_estatisticas(titulo, expiracao, semanal=False):

    st.subheader(titulo)

    dados = obter_estatisticas(
        expiracao,
        semanal=semanal
    )

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric(
        "Taxa de acerto",
        f"{dados['taxa']:.2f}%"
    )

    col2.metric(
        "Acertos",
        dados["acertos"]
    )

    col3.metric(
        "Erros",
        dados["erros"]
    )

    col4.metric(
        "Empates",
        dados["empates"]
    )

    col5.metric(
        "Pendentes",
        dados["pendentes"]
    )

    st.caption(
        f"Total de sinais avaliados: {dados['total']}"
    )


try:

    tab1, tab2 = st.tabs([
        "📅 Esta semana",
        "🌎 Histórico geral"
    ])

    with tab1:

        mostrar_estatisticas(
            "Expiração de 1 minuto",
            1,
            semanal=True
        )

        mostrar_estatisticas(
            "Expiração de 5 minutos",
            5,
            semanal=True
        )

    with tab2:

        mostrar_estatisticas(
            "Expiração de 1 minuto",
            1,
            semanal=False
        )

        mostrar_estatisticas(
            "Expiração de 5 minutos",
            5,
            semanal=False
        )

except Exception as erro:
    st.warning(
        f"Não foi possível carregar as estatísticas: {erro}"
    )


# ==================================
# ATIVOS
# ==================================

ativos = {
    "EUR/USD": "EURUSD",
    "GBP/USD": "GBPUSD",
    "USD/JPY": "USDJPY",
    "AUD/USD": "AUDUSD",
    "USD/CHF": "USDCHF",
    "EUR/GBP": "EURGBP"
}

nome_ativo = st.selectbox(
    "Selecione o ativo",
    list(ativos.keys())
)

asset = ativos[nome_ativo]

st.caption(
    "Fonte: Yahoo Finance. "
    "Cotações não oficiais da IQ Option. "
    "Pares OTC não disponíveis."
)


# ==================================
# ANÁLISE DO MERCADO
# ==================================

if st.button("ANALISAR MERCADO", type="primary"):

    try:

        with st.spinner(
            f"Analisando {nome_ativo} em 1M e 5M..."
        ):

            data_1m = get_market_data(asset, 1)
            data_5m = get_market_data(asset, 5)

            # Avalia sinais anteriores
            quantidade_avaliada = (
                avaliar_sinais_pendentes(
                    asset,
                    data_1m
                )
            )

            # Indicadores
            data_1m = calculate_indicators(data_1m)
            data_5m = calculate_indicators(data_5m)

            # Estratégia
            result = analyze_market(
                data_1m,
                data_5m
            )

        if quantidade_avaliada > 0:
            st.success(
                f"{quantidade_avaliada} "
                "registro(s) avaliado(s)."
            )

        st.divider()
        st.subheader(f"Resultado: {nome_ativo}")

        if result["signal"] == "CALL":

            st.success("🟢 POSSÍVEL ENTRADA: CALL")

        elif result["signal"] == "PUT":

            st.error("🔴 POSSÍVEL ENTRADA: PUT")

        else:

            st.warning("🟡 AGUARDAR — SEM ENTRADA")

        st.write("**Motivo:**", result["reason"])

        # Registra novos sinais
        if result["signal"] in ["CALL", "PUT"]:

            try:

                preco_entrada = float(
                    data_1m.iloc[-1]["close"]
                )

                horario_entrada = (
                    pd.to_datetime(
                        data_1m.index[-1],
                        utc=True
                    ) + pd.Timedelta(minutes=1)
                ).isoformat()

                registrar_sinal(
                    ativo=asset,
                    direcao=result["signal"],
                    horario_entrada=horario_entrada,
                    preco_entrada=preco_entrada
                )

                st.success(
                    "Sinal registrado para avaliação "
                    "independente de 1M e 5M."
                )

            except Exception as erro:
                st.warning(
                    f"Erro ao registrar sinal: {erro}"
                )

        # Indicadores técnicos
        st.divider()
        st.subheader("Indicadores técnicos")

        col1, col2 = st.columns(2)

        with col1:

            st.markdown("### Gráfico de 1 minuto")

            last_1m = data_1m.iloc[-1]

            st.metric(
                "RSI 1M",
                round(last_1m["RSI"], 2)
            )

            st.metric(
                "EMA 9",
                round(last_1m["EMA9"], 5)
            )

            st.metric(
                "EMA 21",
                round(last_1m["EMA21"], 5)
            )

        with col2:

            st.markdown("### Gráfico de 5 minutos")

            last_5m = data_5m.iloc[-1]

            st.metric(
                "RSI 5M",
                round(last_5m["RSI"], 2)
            )

            st.metric(
                "EMA 9",
                round(last_5m["EMA9"], 5)
            )

            st.metric(
                "EMA 21",
                round(last_5m["EMA21"], 5)
            )

        # Gráficos
        st.divider()
        st.subheader("Histórico de preços")

        st.markdown(f"#### {nome_ativo} — 1 minuto")
        st.line_chart(data_1m["close"])

        st.markdown(f"#### {nome_ativo} — 5 minutos")
        st.line_chart(data_5m["close"])

    except Exception as error:

        st.error(
            f"Não foi possível realizar a análise: {error}"
        )


st.divider()

st.caption(
    "TRADER AI PRO | Sistema experimental de análise. "
    "Não executa operações e não garante resultados financeiros."
)
