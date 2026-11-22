
import streamlit as st
from supabase import create_client


def obter_cliente():

    try:
        url = st.secrets["SUPABASE_URL"]
        chave = st.secrets["SUPABASE_KEY"]

        return create_client(url, chave)

    except Exception as erro:
        raise RuntimeError(
            f"Erro ao conectar ao Supabase: {erro}"
        )


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
        cliente
        .table("historico_sinais")
        .insert(registros)
        .execute()
    )

    return resposta.data
