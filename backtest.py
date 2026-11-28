"""Offline research replay. Never issues live signals or changes the database.

Input: one-minute OHLC with UTC candle OPEN timestamps. At each fixed sampling
time, only completed candles enter the strategy. A hypothetical fill uses the
next candle open after a configurable delay. Missing minute bars void a trial.
Results are provider-price simulations, NOT broker returns or live validation.
"""
from __future__ import annotations
import argparse
import json
import pandas as pd
from indicators import calculate_indicators
from strategy import analyze_market
from reliability import validate_ohlc, closed_five_minute, advance_confirmation

def replay(frame, scan_minutes=2, delay_minutes=1, expirations=(1,5), lookback=250):
    if scan_minutes < 1 or delay_minutes < 1 or lookback < 155:
        raise ValueError("Parâmetros de replay inválidos.")
    if any(e not in (1,5) for e in expirations):
        raise ValueError("Expirações suportadas: 1 e 5 minutos.")
    data = validate_ohlc(frame)
    results = []
    state = None
    for i in range(lookback, len(data)):
        decision = data.index[i-1] + pd.Timedelta(minutes=1)
        if int(decision.timestamp() // 60) % scan_minutes:
            continue
        history = data.iloc[i-lookback:i]
        # Require a contiguous observation window; never bridge a market gap.
        if (history.index[-1] - history.index[0]).total_seconds() != (lookback-1)*60:
            state = None
            continue
        five = closed_five_minute(history)
        analysis = analyze_market(calculate_indicators(history), calculate_indicators(five))
        state, advanced = advance_confirmation(state, analysis["signal"], history.index[-1], max_gap_seconds=scan_minutes*60)
        if not advanced or not state or state["count"] != 2:
            continue
        entry = decision + pd.Timedelta(minutes=delay_minutes)
        if entry not in data.index:
            continue
        price = float(data.at[entry,"open"])
        for expiration in expirations:
            end = entry + pd.Timedelta(minutes=expiration)
            expected = pd.date_range(decision, end, freq="min")
            if not expected.isin(data.index).all():
                continue
            final = float(data.at[end,"open"])
            change = (final-price) * (1 if state["signal"]=="CALL" else -1)
            results.append({"decision":decision.isoformat(),"entry":entry.isoformat(),"end":end.isoformat(),"direction":state["signal"],"expiration":expiration,"entry_price":price,"final_price":final,"score":analysis.get("score"),"result":"ACERTO" if change>0 else ("ERRO" if change<0 else "EMPATE")})
    return pd.DataFrame(results,columns=["decision","entry","end","direction","expiration","entry_price","final_price","score","result"])

def summarize(trials):
    out={}
    for expiry in (1,5):
        values=trials.loc[trials.expiration==expiry,"result"]
        wins=int((values=="ACERTO").sum())
        losses=int((values=="ERRO").sum())
        ties=int((values=="EMPATE").sum())
        out[str(expiry)]={"wins":wins,"losses":losses,"ties":ties,"sample_size":len(values),"win_rate_excluding_ties":wins/(wins+losses) if wins+losses else None}
    return out

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", help="CSV time,open,high,low,close; time UTC ISO8601")
    parser.add_argument("--output", default="replay_results.csv")
    args=parser.parse_args()
    frame=pd.read_csv(args.csv)
    frame.index=pd.to_datetime(frame.pop("time"),utc=True,errors="raise")
    trials=replay(frame)
    trials.to_csv(args.output,index=False)
    print(json.dumps(summarize(trials),indent=2))
if __name__=="__main__":
    main()
