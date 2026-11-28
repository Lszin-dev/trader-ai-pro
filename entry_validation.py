"""Validação conservadora de preço e horário para entradas de sinais.

Este módulo não busca cotações. Ele valida uma cotação recebida de um provedor
com timestamp próprio. Sem cotação recente e identificável, a entrada deve
ser rejeitada.
"""

from datetime import datetime, timezone
import math


def validate_entry_quote(
    price,
    quote_timestamp,
    now=None,
    max_age_seconds=10,
    future_tolerance_seconds=2,
):
    """Valida preço e timestamp de uma cotação antes de registrar uma entrada.

    Args:
        price: preço da cotação recebida do provedor.
        quote_timestamp: timestamp da cotação (datetime ou ISO 8601).
        now: horário atual usado para validação; padrão UTC atual.
        max_age_seconds: idade máxima permitida para a cotação.
        future_tolerance_seconds: tolerância para pequenos desvios de relógio.

    Returns:
        dict com valid, price, entry_timestamp e reason.
    """
    try:
        numeric_price = float(price)
    except (TypeError, ValueError):
        return _rejected("Preço de entrada inválido.")

    if not math.isfinite(numeric_price) or numeric_price <= 0:
        return _rejected("Preço de entrada deve ser finito e maior que zero.")

    timestamp = _parse_timestamp(quote_timestamp)
    if timestamp is None:
        return _rejected("Cotação sem timestamp válido.")

    current_time = _parse_timestamp(now) if now is not None else datetime.now(timezone.utc)
    if current_time is None:
        return _rejected("Horário de referência inválido.")

    age_seconds = (current_time - timestamp).total_seconds()

    if age_seconds < -future_tolerance_seconds:
        return _rejected("Timestamp da cotação está no futuro; possível divergência de relógio.")

    if age_seconds > max_age_seconds:
        return _rejected(
            f"Cotação desatualizada ({age_seconds:.1f}s; limite {max_age_seconds}s)."
        )

    return {
        "valid": True,
        "price": numeric_price,
        "entry_timestamp": timestamp.isoformat(),
        "reason": "Cotação recente e timestamp validado.",
    }


def _parse_timestamp(value):
    if value is None:
        return None

    try:
        if isinstance(value, datetime):
            parsed = value
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        if parsed.tzinfo is None:
            return None

        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _rejected(reason):
    return {
        "valid": False,
        "price": None,
        "entry_timestamp": None,
        "reason": reason,
    }
