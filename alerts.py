
def generate_alert(signal, asset, timeframe, reason):

    if signal == "CALL":
        title = "POSSÍVEL ALTA"

    elif signal == "PUT":
        title = "POSSÍVEL BAIXA"

    else:
        title = "SEM ENTRADA"

    return {
        "title": title,
        "asset": asset,
        "timeframe": timeframe,
        "signal": signal,
        "reason": reason
    }
