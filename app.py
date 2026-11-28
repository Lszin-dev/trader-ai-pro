import json

import pandas as pd
import streamlit as st

from data_feed import get_market_data
from historico import obter_estatisticas
from indicators import calculate_indicators
from monitor_state import listar_estado_monitoramento
from strategy import analyze_market
from reliability import quote_is_current
from research import summarize_research, STRATEGY_VERSION


st.set_page_config(
    page_title="TRADER AI PRO",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 1.4rem; padding-bottom: 3rem;}
    [data-testid="stMetricValue"] {font-size: 1.45rem;}
    .tap-note {opacity: .75; font-size: .9rem;}
    @media (max-width: 760px) {
        .block-container {padding-left: .85rem; padding-right: .85rem; padding-top: .75rem;}
        h1 {font-size: 1.85rem !important;}
        h2 {font-size: 1.35rem !important;}
        [data-testid="stMetricValue"] {font-size: 1.2rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("📈 TRADER AI PRO")
st.caption("Motor experimental de monitoramento técnico • foco em confirmação, rastreabilidade e leitura simples")

modo_detalhado = st.toggle(
    "Modo detalhado",
    value=False,
    help="Mostra score, métricas, confirmações, revalidação e gráfico recente.",
)

st.info(
    "O 5M confirma a tendência e o 1M procura o momento. "
    "CALL/PUT exibidos aqui são candidatos técnicos; só uma cotação da corretora no instante da entrada pode validar execução real."
)


def _formatar_horario(value):
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


def _details(row):
    value = row.get("detalhes") or {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _recent_chart(details):
    points = details.get("recent_prices") or []
    if not isinstance(points, list) or len(points) < 2:
        return None
    try:
        frame = pd.DataFrame(points)
        frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="coerce")
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = frame.dropna().set_index("time").sort_index()
        return frame[["close"]] if len(frame) >= 2 else None
    except Exception:
        return None


def _score_label(score):
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "—"
    return f"{value:.0f}/100"


st.divider()
st.header("📡 Monitoramento automático")
st.caption("Atualiza esta área a cada 15 segundos enquanto a página estiver aberta. O worker roda separadamente.")


@st.fragment(run_every="15s")
def render_monitoramento():
    try:
        rows = listar_estado_monitoramento(limit=30)
    except Exception as error:
        st.error(
            "Não foi possível consultar o monitoramento compartilhado. "
            f"Detalhe: {error}"
        )
        return

    if not rows:
        st.warning("A tabela existe, mas ainda não recebeu ciclos do worker.")
        return

    worker_rows = [row for row in rows if row.get("ativo") == "_WORKER"]
    asset_rows = [row for row in rows if row.get("ativo") != "_WORKER"]

    if worker_rows:
        worker = worker_rows[0]
        worker_details = _details(worker)
        updated = pd.to_datetime(worker.get("atualizado_em"), utc=True, errors="coerce")
        age_seconds = (
            (pd.Timestamp.now(tz="UTC") - updated).total_seconds()
            if not pd.isna(updated)
            else None
        )
        market = worker_details.get("market") or {}
        market_open = market.get("open")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Fonte", str(worker.get("provider", "—")).upper())
        col2.metric("Último ciclo", _formatar_horario(worker.get("ultimo_ciclo")))
        if age_seconds is None:
            health = "Indeterminada"
        elif age_seconds > 300:
            health = "Desatualizado"
        elif worker.get("status") == "error":
            health = "Erro"
        elif worker.get("status") == "running":
            health = "Executando"
        else:
            health = "Atualizado"
        col3.metric("Motor", health)
        col4.metric("Forex", "Aberto" if market_open is True else ("Fechado" if market_open is False else "—"))

        if age_seconds is not None and age_seconds > 300:
            st.error("O worker não atualiza há mais de 5 minutos. Não use o estado abaixo como atual.")
        elif worker.get("status") == "error":
            st.error(worker.get("motivo") or "O último ciclo terminou com erro.")
        elif market_open is False:
            st.info("Mercado Forex fechado no fim de semana. O worker preserva a cota da API e aguarda a reabertura.")

        if modo_detalhado:
            usage = worker_details.get("api_usage") or {}
            cycle_duration = worker_details.get("cycle_duration_seconds")
            budget = worker_details.get("credit_budget") or {}
            if usage or budget or cycle_duration is not None:
                with st.expander("Detalhes do motor", expanded=False):
                    if cycle_duration is not None:
                        st.write(f"Duração do último ciclo: **{cycle_duration}s**")
                    if budget:
                        st.write("Orçamento local estimado de créditos", budget)
                    if usage:
                        st.write(
                            "Uso da API: ",
                            {
                                "plano": usage.get("plan_category"),
                                "uso_minuto": usage.get("current_usage"),
                                "limite_minuto": usage.get("plan_limit"),
                                "uso_dia": usage.get("daily_usage"),
                                "limite_dia": usage.get("plan_daily_limit"),
                            },
                        )

    if not asset_rows:
        st.info("O worker ainda não publicou nenhum ativo.")
        return

    for row in asset_rows:
        details = _details(row)
        status = row.get("status", "error")
        candidate = row.get("sinal_candidato", "AGUARDAR")
        score = details.get("technical_score", 0)
        confirmations = details.get("candidate_confirmations", 0)
        required = details.get("required_confirmations", 2)
        revalidation = details.get("provider_revalidation") or {}
        updated = pd.to_datetime(row.get("atualizado_em"), utc=True, errors="coerce")
        age_seconds = (
            (pd.Timestamp.now(tz="UTC") - updated).total_seconds()
            if not pd.isna(updated)
            else None
        )
        stale = age_seconds is None or age_seconds > 300

        with st.container(border=True):
            title_col, signal_col, score_col = st.columns([2.2, 1.4, 1])
            title_col.markdown(f"### {row.get('ativo', 'Ativo desconhecido')}")
            title_col.caption(f"Fonte: {str(row.get('provider', '—')).upper()}")

            if status == "error":
                signal_col.error("Feed indisponível")
            elif stale:
                signal_col.warning("Dados desatualizados")
            elif candidate in ("CALL", "PUT"):
                revalidation_state = revalidation.get("state")
                if quote_is_current(revalidation):
                    signal_col.warning(f"{candidate} • cotação recente no provedor")
                elif revalidation.get("valid"):
                    signal_col.warning(f"{candidate} • cotação expirada")
                elif revalidation_state == "persistent_candidate":
                    signal_col.warning(f"{candidate} • aguardando novo gatilho")
                elif int(confirmations or 0) >= int(required or 2):
                    signal_col.warning(f"{candidate} • sem revalidação atual")
                else:
                    signal_col.warning(f"{candidate} • confirmando {confirmations}/{required}")
            else:
                signal_col.success("AGUARDAR")

            score_col.metric("Score técnico", _score_label(score))
            st.caption("Score técnico mede confluência das regras do sistema; não é probabilidade de acerto.")
            st.write(row.get("motivo") or "Sem detalhe adicional.")
            st.caption(
                f"Ciclo: {_formatar_horario(row.get('ultimo_ciclo'))} • "
                f"último candle: {_formatar_horario(row.get('ultimo_dado'))}"
            )

            if candidate in ("CALL", "PUT"):
                st.warning(
                    "Candidato técnico detectado. Mesmo com revalidação na Twelve Data, "
                    "a entrada real continua bloqueada até conferir a cotação da corretora no instante da operação."
                )

            if modo_detalhado:
                chart = _recent_chart(details)
                if chart is not None:
                    st.markdown("**Últimos preços recebidos pelo worker**")
                    st.line_chart(chart, height=220)

                d1, d2, d3, d4 = st.columns(4)
                d1.metric("Qualidade", str(details.get("quality", "—")))
                d2.metric("Confirmações", f"{confirmations}/{required}")
                lag = details.get("feed_lag_seconds")
                d3.metric("Atraso do feed", f"{lag}s" if lag is not None else "—")
                d4.metric("Último preço", str(details.get("last_close", "—")))

                metrics = details.get("metrics") or {}
                checks = details.get("checks") or {}
                with st.expander("Indicadores e filtros", expanded=False):
                    if metrics:
                        st.write("Métricas", metrics)
                    if checks:
                        st.write("Filtros", checks)
                    if revalidation:
                        st.write("Última revalidação no provedor (registro histórico)", revalidation)


render_monitoramento()


st.divider()
st.header("🧪 Pesquisa simulada")
st.caption("Resultados hipotéticos de abertura de candles da Twelve Data; não são resultados da corretora. Versão: " + STRATEGY_VERSION)
if st.button("Consultar resultados simulados"):
    try:
        report = summarize_research("twelvedata", "FOREX:EURUSD")
        for expiry, counts in report.items():
            st.markdown(f"**Expiração {expiry}M**")
            c1,c2,c3 = st.columns(3)
            c1.metric("Acertos / erros", f"{counts['ACERTO']} / {counts['ERRO']}")
            rate = counts["taxa"]
            c2.metric("Taxa sem empates", "Sem amostra" if rate is None else f"{rate:.1f}%")
            c3.metric("Pendentes", counts["PENDENTE"])
            st.caption(f"Empates: {counts['EMPATE']} • Sem dados: {counts['SEM_DADOS']}")
    except Exception:
        st.info("Pesquisa ainda não disponível: confira a migração e as permissões do servidor.")

st.divider()
st.header("📊 Desempenho histórico")
st.caption(
    "Esta seção usa a base histórica já existente. O novo monitor Forex ainda não mistura candidatos da Twelve Data com esse histórico."
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


st.divider()
st.header("🔎 Consulta manual de referência")
st.caption("Yahoo Finance é usado somente como referência técnica; não publica nem registra uma entrada.")

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

if st.button("ANALISAR MERCADO", type="primary", use_container_width=True):
    try:
        with st.spinner(f"Analisando {nome_ativo} em 1M e 5M..."):
            data_1m = calculate_indicators(get_market_data(asset, 1))
            data_5m = calculate_indicators(get_market_data(asset, 5))
            result = analyze_market(data_1m, data_5m)

        st.subheader(f"Resultado técnico: {nome_ativo}")
        r1, r2 = st.columns(2)
        r1.metric("Leitura", result["signal"])
        r2.metric("Score técnico", _score_label(result.get("score")))
        st.write(result["reason"])
        st.caption("Esse score não representa chance estatística de vitória.")

        if modo_detalhado:
            with st.expander("Detalhamento técnico", expanded=True):
                st.write("Métricas", result.get("metrics", {}))
                st.write("Filtros", result.get("checks", {}))
            st.markdown(f"#### {nome_ativo} — 1 minuto")
            st.line_chart(data_1m["close"])
            st.markdown(f"#### {nome_ativo} — 5 minutos")
            st.line_chart(data_5m["close"])

    except Exception as error:
        st.error(f"Não foi possível realizar a análise: {error}")


st.divider()
st.caption(
    "TRADER AI PRO • sistema experimental de análise e monitoramento. "
    "Não executa operações e não garante resultados financeiros."
)
