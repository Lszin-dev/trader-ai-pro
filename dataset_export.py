"""Private offline dataset export and chronological research split.

Run on a trusted machine with SUPABASE_URL / SUPABASE_KEY set as environment
variables. The export contains research features and simulated outcomes, not
broker trades. Do not upload it to the public repository.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import tempfile
import pandas as pd
from research import TABLE, STRATEGY_VERSION

FEATURES = ("rsi_1m","atr_pct_1m","atr_pct_5m","trend_consistency_5m","ema_gap_5m_atr","momentum_3m")

def _time(value):
    t=pd.Timestamp(value)
    if pd.isna(t) or t.tzinfo is None:
        raise ValueError("Timestamp inválido.")
    return t.tz_convert("UTC")

def prepare_rows(rows, split_at):
    """Exclude pending/missing/ties and purge training labels overlapping test."""
    boundary=_time(split_at)
    prepared=[]
    for row in rows:
        if row["status"] not in ("ACERTO","ERRO"):
            continue
        decision,target=_time(row["observed_at"]),_time(row["target_at"])
        if decision>=boundary:
            split="test"
        elif target+pd.Timedelta(minutes=1)<boundary:
            split="train"
        else:
            continue
        metrics=(row.get("features") or {}).get("metrics") or {}
        item={k:row.get(k) for k in ("provider","ativo","strategy_version","direction","expiration_minutes","observed_at","target_at","score")}
        item.update({name:metrics.get(name) for name in FEATURES})
        item.update({"split":split,"label":int(row["status"]=="ACERTO")})
        prepared.append(item)
    return sorted(prepared,key=lambda r:_time(r["observed_at"]))

def fetch_rows(client, provider, asset, version, cutoff):
    """Retrieve only the selected version and source; paginate deterministic key."""
    offset=0
    while True:
        response=(client.table(TABLE).select("*").eq("provider",provider)
            .eq("ativo",asset).eq("strategy_version",version)
            .in_("status",["ACERTO","ERRO"]).lt("target_at",cutoff)
            .order("candle_time").order("expiration_minutes")
            .range(offset,offset+499).execute())
        rows=response.data or []
        yield from rows
        if len(rows)<500:
            break
        offset+=len(rows)

def write_csv(rows, destination):
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    fields=["provider","ativo","strategy_version","direction","expiration_minutes","observed_at","target_at","score",*FEATURES,"split","label"]
    # Write a private temporary file, then atomically replace the output.
    fd,temp=tempfile.mkstemp(prefix=".research-",dir=destination.parent)
    try:
        with os.fdopen(fd,"w",newline="",encoding="utf-8") as stream:
            writer=csv.DictWriter(stream,fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp,destination)
    finally:
        if os.path.exists(temp): os.unlink(temp)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-at",required=True,help="UTC ISO timestamp; decide before evaluating test.")
    parser.add_argument("--cutoff",required=True,help="UTC ISO timestamp; fixed dataset end.")
    parser.add_argument("--output",default="private_data/research_dataset.csv")
    parser.add_argument("--asset",default="FOREX:EURUSD")
    args=parser.parse_args()
    if _time(args.cutoff)<=_time(args.split_at):
        parser.error("cutoff precisa ser posterior ao split.")
    from historico import obter_cliente
    rows=prepare_rows(fetch_rows(obter_cliente(),"twelvedata",args.asset,STRATEGY_VERSION,_time(args.cutoff).isoformat()),args.split_at)
    write_csv(rows,args.output)
    print(json.dumps({"rows":len(rows),"train":sum(r["split"]=="train" for r in rows),"test":sum(r["split"]=="test" for r in rows)},indent=2))

if __name__=="__main__":
    main()
