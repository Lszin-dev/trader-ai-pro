
import streamlit as st

from data_feed import get_market_data
from indicators import calculate_indicators
from strategy import analyze_market

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

asset = st.selectbox(
    "Selecione o ativo",
    ["EURUSD"]
)

st.caption(
    "EUR/USD-OTC ainda não está disponível na fonte gratuita utilizada."
)

if st.button("ANALISAR MERCADO", type="primary"):

    try:
        with st.spinner("Analisando os dois períodos..."):

            # Busca os candles de 1 minuto
            data_1m = get_market_data(asset, 1)

            # Busca os candles de 5 minutos
            data_5m = get_market_data(asset, 5)

            # Calcula os indicadores
            data_1m = calculate_indicators(data_1m)
            data_5m = calculate_indicators(data_5m)

            # Analisa os dois períodos juntos
            result = analyze_market(data_1m, data_5m)

        st.divider()

        st.subheader("Resultado da análise")

        if result["signal"] == "CALL":
            st.success("🟢 POSSÍVEL ENTRADA: CALL")

        elif result["signal"] == "PUT":
            st.error("🔴 POSSÍVEL ENTRADA: PUT")

        else:
            st.warning("🟡 AGUARDAR — SEM ENTRADA")

        st.write("**Motivo:**", result["reason"])

        st.divider()

        st.subheader("Indicadores técnicos")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Gráfico de 1 minuto")

            last_1m = data_1m.iloc[-1]

            st.metric("RSI 1M", round(last_1m["RSI"], 2))
            st.metric("EMA 9", round(last_1m["EMA9"], 5))
            st.metric("EMA 21", round(last_1m["EMA21"], 5))

        with col2:
            st.markdown("### Gráfico de 5 minutos")

            last_5m = data_5m.iloc[-1]

            st.metric("RSI 5M", round(last_5m["RSI"], 2))
            st.metric("EMA 9", round(last_5m["EMA9"], 5))
            st.metric("EMA 21", round(last_5m["EMA21"], 5))

        st.divider()

        st.subheader("Histórico de preços")

        st.markdown("#### EUR/USD — 1 minuto")
        st.line_chart(data_1m["close"])

        st.markdown("#### EUR/USD — 5 minutos")
        st.line_chart(data_5m["close"])

        st.caption(
            "Dados consultados: Yahoo Finance. "
            "Não são cotações oficiais da IQ Option."
        )

    except Exception as error:
        st.error(f"Não foi possível realizar a análise: {error}")

st.divider()

st.caption(
    "TRADER AI PRO | Sistema experimental de análise. "
    "Não executa operações e não garante resultados financeiros."
)
