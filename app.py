import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from data_feed import get_market_data
from indicators import calculate_indicators
from strategy import analyze_market
from historico import obter_estatisticas
from monitor_state import listar_estado_monitoramento


st.set_page_config(
    page_title="TRADER AI PRO",
    page_icon="📈",
    layout="wide",
)

st.title("📈 TRADER AI PRO")
st.subheader("Análise técnica inteligente")
st.info(
    "O gráfico de 5 minutos confirma a tendência. "
    "O gráfico de 1 minuto procura o momento de entrada. "
    "Somente sinais com cotação ao vivo revalidada poderão ser publicados."
)


# ==========================================
# MONITORAMENTO COMPARTILHADO PC + CELULAR
# ==========================================

st.divider()
st.header("📡 Monitoramento automático")
st.caption(
    "Este painel consulta o estado compartilhado no Supabase. "
    "A atualização visual ocorre a cada 15 segundos; isso não inicia o worker."
)

st_autorefresh(interval=15_000, key="trader_ai_monitor_refresh")


def formatar_horario(value):
    if not value:
        return "Sem registro"
    try:
        return (
            pd.to_datetime(value, utc=True)
            .tz_convert("America/Sao_Paulo")
            .strftime("%d/%m/%Y %H:%M:%S")
        )
    except Exception:
        return str(value)


def render_monitoramento():
    try:
        rows = listar_estado_monitoramento(limit=30)
    except Exception as error:
        st.error(
            "Não foi possível consultar o monitoramento compartilhado. "
            "Verifique se a tabela monitoramento_estado foi criada no Supabase "
            f"e se as permissões estão configuradas. Detalhe: {error}"
        )
        return

    if not rows:
        st.warning(
            "Ainda não há ciclos registrados. O worker precisa estar configurado "
            "e em execução para preencher este painel."
        )
        return

    worker_rows = [row for row in rows if row.get("ativo") == "_WORKER"]
    asset_rows = [row for row in rows if row.get("ativo") != "_WORKER"]

    if worker_rows:
        worker = worker_rows[0]
        updated = pd.to_datetime(worker.get("atualizado_em"), utc=True, errors="coerce")
        age_seconds = (
            (pd.Timestamp.now(tz="UTC") - updated).total_seconds()
            if not pd.isna(updated) else None
        )
        col1, col2, col3 = st.columns(3)
        col1.metric("Fonte do motor", str(worker.get("provider", "—")).upper())
        col2.metric("Último ciclo", formatar_horario(worker.get("ultimo_ciclo")))
        if age_seconds is None:
            col3.metric("Saúde do motor", "Indeterminada")
        elif age_seconds > 300:
            col3.metric("Saúde do motor", "Desatualizado")
            st.error(
                "O último ciclo do worker tem mais de 5 minutos. "
                "Não considere os dados atuais."
            )
        elif worker.get("status") == "running":
            col3.metric("Saúde do motor", "Executando ciclo")
        else:
            col3.metric("Saúde do motor", "Atualizado")
        if worker.get("motivo"):
            st.caption(worker["motivo"])

    if not asset_rows:
        st.info("O worker ainda não publicou o estado de nenhum ativo.")
        return

    for row in asset_rows:
        with st.container(border=True):
            title_col, status_col = st.columns([2, 1])
            title_col.markdown(f"**{row.get('ativo', 'Ativo desconhecido')}**")
            title_col.caption(f"Fonte: {str(row.get('provider', '—')).upper()}")
            status = row.get("status", "error")
            candidate = row.get("sinal_candidato", "AGUARDAR")
            updated = pd.to_datetime(row.get("atualizado_em"), utc=True, errors="coerce")
            age_seconds = (
                (pd.Timestamp.now(tz="UTC") - updated).total_seconds()
                if not pd.isna(updated) else None
            )
            stale = age_seconds is None or age_seconds > 300

            if status == "error":
                status_col.error("Feed indisponível")
            elif stale:
                status_col.warning("Dados desatualizados")
            elif candidate in ("CALL", "PUT"):
                status_col.warning(f"Candidato {candidate} — não confirmado")
            else:
                status_col.success("Aguardar")

            st.caption(
                f"Último ciclo: {formatar_horario(row.get('ultimo_ciclo'))} | "
                f"Último candle: {formatar_horario(row.get('ultimo_dado'))}"
            )
            if row.get("motivo"):
                st.write(row["motivo"])
            if candidate in ("CALL", "PUT"):
                st.warning(
                    "Confluência técnica detectada, mas isto NÃO é um sinal de entrada. "
                    "Falta cotação ao vivo e revalidação obrigatória."
                )


render_monitoramento()


# ==========================================
# DESEMPENHO HISTÓRICO
# ==========================================

st.divider()
st.header("📊 Desempenho dos sinais")
st.caption(
    "Estatísticas da tabela histórica existente. A integração Forex nova "
    "não insere nem altera registros históricos nesta fase."
)


def mostrar_estatisticas(titulo, expiracao, semanal=False):
    st.subheader(titulo)
    dados = obter_estatisticas(expiracao, semanal=semanal)
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Taxa de acerto", f"{dados['taxa']:.2f}%")
    col2.metric("Acertos", dados["acertos"])
    col3.metric("Erros", dados["erros"])
    col4.metric("Empates", dados["empates"])
    col5.metric("Pendentes", dados["pendentes"])
    st.caption(f"Total de sinais avaliados: {dados['total']}")


try:
    tab1, tab2 = st.tabs(["📅 Esta semana", "🌎 Histórico geral"])
    with tab1:
        mostrar_estatisticas("Expiração de 1 minuto", 1, semanal=True)
        mostrar_estatisticas("Expiração de 5 minutos", 5, semanal=True)
    with tab2:
        mostrar_estatisticas("Expiração de 1 minuto", 1, semanal=False)
        mostrar_estatisticas("Expiração de 5 minutos", 5, semanal=False)
except Exception as erro:
    st.warning(f"Não foi possível carregar as estatísticas: {erro}")


# ==========================================
# ANÁLISE MANUAL DE REFERÊNCIA (YAHOO)
# ==========================================

st.divider()
st.header("🔎 Análise manual de referência")
st.caption(
    "Esta área usa Yahoo Finance apenas para consulta técnica. "
    "Não publica sinais, não registra entradas e não substitui o monitoramento "
    "Forex da Twelve Data nem a cotação da corretora."
)

ativos = {
    "EUR/USD": "EURUSD",
    "GBP/USD": "GBPUSD",
    "USD/JPY": "USDJPY",
    "AUD/USD": "AUDUSD",
    "USD/CHF": "USDCHF",
    "EUR/GBP": "EURGBP",
}

nome_ativo = st.selectbox("Selecione o ativo", list(ativos.keys()))
asset = ativos[nome_ativo]

if st.button("ANALISAR MERCADO", type="primary"):
    try:
        with st.spinner(f"Analisando {nome_ativo} em 1M e 5M via Yahoo Finance..."):
            data_1m = get_market_data(asset, 1)
            data_5m = get_market_data(asset, 5)
            data_1m = calculate_indicators(data_1m)
            data_5m = calculate_indicators(data_5m)
            result = analyze_market(data_1m, data_5m)

        st.subheader(f"Resultado técnico: {nome_ativo}")
        if result["signal"] in ("CALL", "PUT"):
            st.warning(
                f"Confluência técnica {result['signal']} detectada. "
                "Não é sinal confirmado e não deve ser usado como entrada."
            )
        else:
            st.info("AGUARDAR — sem confirmação conjunta.")
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
        st.markdown(f"#### {nome_ativo} — 1 minuto")
        st.line_chart(data_1m["close"])
        st.markdown(f"#### {nome_ativo} — 5 minutos")
        st.line_chart(data_5m["close"])

    except Exception as error:
        st.error(f"Não foi possível realizar a análise: {error}")


st.divider()
st.caption(
    "TRADER AI PRO | Sistema experimental de análise. "
    "Não executa operações e não garante resultados financeiros."
)
