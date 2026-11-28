
import os
import pandas as pd
from supabase import create_client


# ==========================================
# CONEXÃO COM SUPABASE
# ==========================================

def obter_cliente():

    url = os.getenv("SUPABASE_URL")
    chave = os.getenv("SUPABASE_KEY")

    # No Streamlit, utiliza os Secrets como alternativa
    if not url or not chave:
        try:
            import streamlit as st
            url = st.secrets["SUPABASE_URL"]
            chave = st.secrets["SUPABASE_KEY"]
        except Exception:
            raise ValueError(
                "Configure SUPABASE_URL e SUPABASE_KEY."
            )

    return create_client(url, chave)


# ==========================================
# REGISTRAR SINAIS
# ==========================================

def registrar_sinal(
    ativo,
    direcao,
    horario_entrada,
    preco_entrada
):

    if direcao not in ["CALL", "PUT"]:
        raise ValueError("Direção inválida.")

    cliente = obter_cliente()

    registros = []

    for expiracao in [1, 5]:

        registros.append({
            "ativo": ativo,
            "direcao": direcao,
            "horario_entrada": horario_entrada,
            "preco_entrada": float(preco_entrada),
            "expiracao_minutos": expiracao,
            "resultado": "AGUARDANDO"
        })

    resposta = (
        cliente.table("historico_sinais")
        .insert(registros)
        .execute()
    )

    return resposta.data


# ==========================================
# AVALIAR SINAIS PENDENTES
# ==========================================

def avaliar_sinais_pendentes(ativo, data_1m):

    if data_1m.empty:
        return 0

    cliente = obter_cliente()

    dados = data_1m.copy()

    dados.index = pd.to_datetime(
        dados.index,
        utc=True
    )

    dados = dados.sort_index()

    resposta = (
        cliente.table("historico_sinais")
        .select("*")
        .eq("ativo", ativo)
        .eq("resultado", "AGUARDANDO")
        .execute()
    )

    avaliados = 0

    agora = pd.Timestamp.now(tz="UTC")

    for sinal in resposta.data:

        horario = pd.to_datetime(
            sinal["horario_entrada"],
            utc=True
        )

        expiracao = int(
            sinal["expiracao_minutos"]
        )

        horario_alvo = (
            horario + pd.Timedelta(minutes=expiracao)
        )

        # Aguarda a expiração
        if agora < horario_alvo:
            continue

        # Procura o candle iniciado exatamente
        # no horário da expiração
        candles = dados.loc[
            dados.index == horario_alvo
        ]

        if candles.empty:
            continue

        candle_final = candles.iloc[0]

        preco_entrada = float(
            sinal["preco_entrada"]
        )

        preco_final = float(
            candle_final["open"]
        )

        # Calcula o resultado
        if preco_final == preco_entrada:

            resultado = "EMPATE"

        elif sinal["direcao"] == "CALL":

            resultado = (
                "ACERTO"
                if preco_final > preco_entrada
                else "ERRO"
            )

        else:

            resultado = (
                "ACERTO"
                if preco_final < preco_entrada
                else "ERRO"
            )

        # Atualiza o Supabase
        (
            cliente.table("historico_sinais")
            .update({
                "preco_final": preco_final,
                "resultado": resultado,
                "horario_resultado": horario_alvo.isoformat()
            })
            .eq("id", sinal["id"])
            .eq("resultado", "AGUARDANDO")
            .execute()
        )

        avaliados += 1

    return avaliados


# ==========================================
# ESTATÍSTICAS SEMANAIS E GERAIS
# ==========================================

def obter_estatisticas(expiracao, semanal=False):

    cliente = obter_cliente()

    resposta = (
        cliente.table("historico_sinais")
        .select("resultado, horario_resultado")
        .eq("expiracao_minutos", expiracao)
        .execute()
    )

    dados = resposta.data or []

    df = pd.DataFrame(dados)

    if df.empty:

        return {
            "acertos": 0,
            "erros": 0,
            "empates": 0,
            "pendentes": 0,
            "total": 0,
            "taxa": 0.0
        }

    if semanal:

        df["horario_resultado"] = pd.to_datetime(
            df["horario_resultado"],
            utc=True,
            errors="coerce"
        )

        agora = pd.Timestamp.now(
            tz="America/Sao_Paulo"
        )

        inicio_semana = (
            agora.normalize()
            - pd.Timedelta(days=agora.weekday())
        )

        horarios_locais = (
            df["horario_resultado"]
            .dt.tz_convert("America/Sao_Paulo")
        )

        df = df[
            horarios_locais >= inicio_semana
        ]

    acertos = int(
        (df["resultado"] == "ACERTO").sum()
    )

    erros = int(
        (df["resultado"] == "ERRO").sum()
    )

    empates = int(
        (df["resultado"] == "EMPATE").sum()
    )

    pendentes = int(
        (df["resultado"] == "AGUARDANDO").sum()
    )

    total = acertos + erros + empates

    avaliados = acertos + erros

    taxa = (
        (acertos / avaliados) * 100
        if avaliados > 0
        else 0.0
    )

    return {
        "acertos": acertos,
        "erros": erros,
        "empates": empates,
        "pendentes": pendentes,
        "total": total,
        "taxa": round(taxa, 2)
    }
