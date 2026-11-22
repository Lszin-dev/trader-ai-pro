
import streamlit as st
import pandas as pd
from supabase import create_client


def obter_cliente():
    url = st.secrets["SUPABASE_URL"]
    chave = st.secrets["SUPABASE_KEY"]

    return create_client(url, chave)


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

        agora = pd.Timestamp.now(tz="UTC")

        # Aguarda chegar ao horário da expiração
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

        # Compara os preços
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

        # Atualiza o registro no Supabase
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
