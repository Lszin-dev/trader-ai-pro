"""Prospective paper research, not broker fills or executable trade signals."""
from __future__ import annotations
from datetime import datetime, timezone
import math
import pandas as pd
from reliability import validate_ohlc

STRATEGY_VERSION = "technical-v2.1"
TABLE = "pesquisa_sinais"
KEYS = ("provider", "ativo", "strategy_version", "candle_time", "expiration_minutes")

def _utc(value):
    stamp = pd.Timestamp(value)
    if pd.isna(stamp) or stamp.tzinfo is None:
        raise ValueError("Timestamp exige fuso horário.")
    return stamp.tz_convert("UTC")

def create_trials(provider, asset, candle_time, observed_at, direction, score, features):
    """Schedule an entry at a strictly future minute; no observed close is a fill."""
    candle = _utc(candle_time)
    observed = _utc(observed_at)
    if candle != candle.floor("min") or candle + pd.Timedelta(minutes=1) > observed:
        raise ValueError("Candle ainda não fechado ou desalinhado.")
    if direction not in ("CALL", "PUT") or not math.isfinite(float(score)) or not 0 <= float(score) <= 100:
        raise ValueError("Candidato inválido.")
    entry = observed.floor("min") + pd.Timedelta(minutes=1)
    return [{
        "provider": provider, "ativo": asset, "strategy_version": STRATEGY_VERSION,
        "candle_time": candle.isoformat(), "observed_at": observed.isoformat(),
        "direction": direction, "expiration_minutes": expiry,
        "entry_at": entry.isoformat(), "target_at": (entry + pd.Timedelta(minutes=expiry)).isoformat(),
        "score": float(score), "features": features, "status": "PENDENTE",
    } for expiry in (1, 5)]

def evaluate_trial(row, frame, now=None):
    """Evaluate only exact opens from completed bars of the same supplied feed.

    Missing historical bars are not substituted. A missing trial remains pending
    until a 15-minute grace period after target closure, then becomes SEM_DADOS.
    """
    if row.get("status") != "PENDENTE":
        return None
    current = _utc(datetime.now(timezone.utc) if now is None else now)
    entry, target = _utc(row["entry_at"]), _utc(row["target_at"])
    if target + pd.Timedelta(minutes=1) > current:
        return None
    data = validate_ohlc(frame)
    data = data.loc[data.index + pd.Timedelta(minutes=1) <= current]
    required = pd.date_range(entry, target, freq="min")
    if not required.isin(data.index).all():
        if current < target + pd.Timedelta(minutes=16):
            return None
        return {"status":"SEM_DADOS","evaluated_at":current.isoformat()}
    first, final = float(data.at[entry,"open"]), float(data.at[target,"open"])
    difference = (final-first) * (1 if row["direction"]=="CALL" else -1)
    return {"status":"ACERTO" if difference>0 else ("ERRO" if difference<0 else "EMPATE"),
            "entry_price":first,"final_price":final,"evaluated_at":current.isoformat()}

def _client():
    from historico import obter_cliente
    return obter_cliente()

def record_trials(rows, client=None):
    db = client if client is not None else _client()
    return db.table(TABLE).upsert(rows, on_conflict=",".join(KEYS), ignore_duplicates=True).execute()

def settle_pending(provider, asset, frame, now=None, client=None, limit=200):
    db = client if client is not None else _client()
    current = _utc(datetime.now(timezone.utc) if now is None else now)
    due = current - pd.Timedelta(minutes=1)
    rows = (db.table(TABLE).select("*").eq("provider", provider).eq("ativo",asset)
            .eq("status","PENDENTE").lte("target_at",due.isoformat())
            .order("target_at").limit(limit).execute()).data or []
    settled=0
    for row in rows:
        # Never apply the current algorithm to a differently versioned setup;
        # settlement is price-only and version remains part of the primary key.
        update=evaluate_trial(row,frame,current)
        if update is None:
            continue
        query=db.table(TABLE).update(update).eq("status","PENDENTE")
        for key in KEYS:
            query=query.eq(key,row[key])
        response=query.execute()
        settled+=len(response.data or [])
    return settled

def summarize_research(provider, asset, version=STRATEGY_VERSION, client=None):
    """Exact server-side counts, not a capped list of records."""
    db=client if client is not None else _client()
    report={}
    for expiry in (1,5):
        counts={}
        for status in ("PENDENTE","ACERTO","ERRO","EMPATE","SEM_DADOS"):
            response=(db.table(TABLE).select("provider",count="exact",head=True)
                .eq("provider",provider).eq("ativo",asset).eq("strategy_version",version)
                .eq("expiration_minutes",expiry).eq("status",status).execute())
            if response.count is None:
                raise RuntimeError("Contagem exata indisponível.")
            counts[status]=int(response.count)
        decisive=counts["ACERTO"]+counts["ERRO"]
        counts["taxa"]=100*counts["ACERTO"]/decisive if decisive else None
        report[expiry]=counts
    return report
