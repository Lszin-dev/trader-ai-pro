
def analyze_market(data_1m, data_5m):

    if len(data_1m) < 30 or len(data_5m) < 30:
        return {
            "signal": "AGUARDAR",
            "reason": "Dados insuficientes para confirmar a tendência."
        }

    last_1m = data_1m.iloc[-1]
    last_5m = data_5m.iloc[-1]

    required = [
        "EMA9", "EMA21", "RSI",
        "MACD", "MACD_SIGNAL", "ATR"
    ]

    for candle in [last_1m, last_5m]:
        if candle[required].isna().any():
            return {
                "signal": "AGUARDAR",
                "reason": "Indicadores incompletos."
            }

        if candle["ATR"] <= 0:
            return {
                "signal": "AGUARDAR",
                "reason": "Volatilidade insuficiente."
            }

    alta_5m = (
        last_5m["EMA9"] > last_5m["EMA21"]
        and last_5m["MACD"] > last_5m["MACD_SIGNAL"]
    )

    baixa_5m = (
        last_5m["EMA9"] < last_5m["EMA21"]
        and last_5m["MACD"] < last_5m["MACD_SIGNAL"]
    )

    alta_1m = (
        last_1m["EMA9"] > last_1m["EMA21"]
        and last_1m["MACD"] > last_1m["MACD_SIGNAL"]
        and last_1m["close"] > last_1m["EMA9"]
        and 45 <= last_1m["RSI"] <= 68
    )

    baixa_1m = (
        last_1m["EMA9"] < last_1m["EMA21"]
        and last_1m["MACD"] < last_1m["MACD_SIGNAL"]
        and last_1m["close"] < last_1m["EMA9"]
        and 32 <= last_1m["RSI"] <= 55
    )

    if alta_5m and alta_1m:
        return {
            "signal": "CALL",
            "reason": "Tendência de alta confirmada em 5M e entrada alinhada em 1M."
        }

    if baixa_5m and baixa_1m:
        return {
            "signal": "PUT",
            "reason": "Tendência de baixa confirmada em 5M e entrada alinhada em 1M."
        }

    return {
        "signal": "AGUARDAR",
        "reason": "Os períodos de 1M e 5M não apresentam confirmação conjunta."
    }
