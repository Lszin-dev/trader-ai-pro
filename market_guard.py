"""Regras de disponibilidade do mercado usadas pelo worker.

O Forex spot normalmente fecha no fim da tarde de sexta-feira em Nova York e
reabre no fim da tarde de domingo. A regra abaixo usa America/New_York para
acompanhar automaticamente horário de verão/inverno.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")


def _to_utc_datetime(value: Any = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("O horário precisa conter fuso horário.")
    return parsed.astimezone(timezone.utc)


def forex_market_status(now: Any = None) -> Dict[str, object]:
    """Retorna se o mercado Forex deve estar aberto segundo a janela semanal.

    Regra operacional: fechamento sexta 17:00 de Nova York e reabertura domingo
    17:00 de Nova York. Feriados específicos continuam sendo detectados pela
    validação de atualidade do feed, não por este módulo.
    """
    utc_now = _to_utc_datetime(now)
    ny_now = utc_now.astimezone(NEW_YORK)
    weekday = ny_now.weekday()
    hour = ny_now.hour + ny_now.minute / 60 + ny_now.second / 3600

    closed = False
    if weekday == 4 and hour >= 17:
        closed = True
    elif weekday == 5:
        closed = True
    elif weekday == 6 and hour < 17:
        closed = True

    return {
        "open": not closed,
        "utc": utc_now.isoformat(),
        "new_york": ny_now.isoformat(),
        "reason": (
            "Mercado Forex dentro da janela semanal de negociação."
            if not closed
            else "Mercado Forex fechado na janela semanal de fim de semana."
        ),
    }
