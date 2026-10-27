"""Replay the frozen FIXED9 paper strategy over a complete Binance week."""
from __future__ import annotations
import glob, sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; PAPER=ROOT/'paper_trading_bot'
sys.path.insert(0,str(PAPER))
from quant_bot.features.build import build_feature_matrix
from quant_bot.forward.data import ReadOnlyMarketDataAdapter
from quant_bot.forward.runner import ForwardPaperRunner
from quant_bot.forward.signal_engine import load_bundle
from quant_bot.forward.store import ForwardStateStore
from quant_bot.forward.types import FinalizedBar,MarketQuote,SignalEvent

START=pd.Timestamp('2026-08-10T00:00:00Z'); END=pd.Timestamp('2026-08-17T00:00:00Z')
WARM=START-pd.Timedelta(minutes=1000)

def load(symbol):
    path=sorted(glob.glob(str(ROOT/'data'/f'{symbol}_1m_*.csv')))[-1]; parts=[]
    for x in pd.read_csv(path,index_col=0,parse_dates=True,chunksize=250_000):
        x.index=pd.to_datetime(x.index,utc=True); y=x[(x.index>=WARM)&(x.index<END)]
        if len(y): parts.append(y)
        if len(x) and x.index[-1]>=END: break
    z=pd.concat(parts).sort_index(); expected=pd.date_range(WARM,END-pd.Timedelta(minutes=1),freq='min',tz='UTC')
    missing=expected.difference(z.index)
    if len(missing): raise RuntimeError(f'{symbol}: {len(missing)} missing minutes')
    return z

class Adapter(ReadOnlyMarketDataAdapter):
    bar=None
    def finalized_bars(self,*a,**k): return []
    def quote(self,symbol):
        b=self.bar; h=.0001
        return MarketQuote(symbol,b.close_time,b.close_time,b.processing_timestamp,b.close*(1-h),b.close*(1+h))

class Precomputed:
    def __init__(self,bundle,signals): self.strategy_id=bundle.strategy_id; self.signals=signals
    def on_finalized_bar(self,bar,history): return self.signals.get((bar.symbol,bar.open_time))

def main():
    out=ROOT/'outputs'/'reliable_crypto_week'; out.mkdir(parents=True,exist_ok=True)
    db=out/'replay.sqlite3'
    if db.exists(): db.unlink()
    bundle=load_bundle(PAPER/'docs'/'forward_paper'/'strategy_a_bundle.pkl')
    frames={s:load(s) for s in bundle.configs}; signals={}; gate=[]
    for s,x in frames.items():
        cfg=bundle.configs[s]; X=build_feature_matrix(x); p=cfg.model.predict_proba(X)
        chosen=(p>cfg.threshold)&(X.range_pos_60<cfg.range_pos_cut)&(X.realized_vol_30>cfg.realized_vol_cut)&(X.index>=START)&(X.index<END)
        gate.append({'symbol':s,'bars':int(((X.index>=START)&(X.index<END)).sum()),'probability_pass':int(((p>cfg.threshold)&(X.index>=START)&(X.index<END)).sum()),'signals':int(chosen.sum())})
        for ts,prob in p[chosen].items():
            close=ts+pd.Timedelta(minutes=1)
            signals[(s,ts)]=SignalEvent(bundle.strategy_id,s,'LONG',ts,close,close,float(prob),float(x.at[ts,'close']),cfg.stop_distance,cfg.leverage_safe,cfg.max_holding_bars,cfg.trailing_activate,cfg.trailing_distance)
    store=ForwardStateStore(db)
    # Disposable backtest DB: durability is irrelevant and synchronous disk
    # flushes per minute would dominate runtime.
    store.connection.execute('PRAGMA synchronous=OFF')
    store.connection.execute('PRAGMA journal_mode=MEMORY')
    adapter=Adapter(); runner=ForwardPaperRunner(adapter,Precomputed(bundle,signals),store)
    store.recent_bars=lambda symbol, limit: pd.DataFrame()
    # Full minute snapshots are unnecessary for a fixed-window backtest and make
    # SQLite replay quadratic. Drawdown is reconstructed from realized trades.
    runner._snapshot_all=lambda timestamp: None
    events=[]
    for s,x in frames.items():
        for ts,r in x[(x.index>=START)&(x.index<END)].iterrows(): events.append((ts,s,r))
    for ts,s,r in sorted(events,key=lambda v:(v[0],v[1])):
        close=ts+pd.Timedelta(minutes=1)
        b=FinalizedBar(s,'1m',ts,close,close,close,close,float(r.open),float(r.high),float(r.low),float(r.close),float(r.volume),float(r.taker_buy_volume),float(r.taker_sell_volume))
        adapter.bar=b; runner.process_bar(b)
    accounts=pd.read_sql_query('select profile,initial_equity,realized_equity,100*(realized_equity/initial_equity-1) return_pct from accounts',store.connection)
    trades=pd.read_sql_query("select profile,count(*) closed_trades,sum(paper_pnl) pnl,sum(case when paper_pnl>0 then 1 else 0 end) wins from executions where paper_pnl is not null group by profile",store.connection)
    ledger=pd.read_sql_query("select profile,exit_time,paper_pnl from executions where paper_pnl is not null order by exit_time",store.connection)
    dd=[]
    for profile in accounts.profile:
        pnl=ledger.loc[ledger.profile.eq(profile),'paper_pnl']; curve=100000+pnl.cumsum(); peak=curve.cummax()
        dd.append({'profile':profile,'max_drawdown_pct':float((100*(curve/peak-1)).min()) if len(curve) else 0.0})
    result=accounts.merge(trades,on='profile',how='left').merge(pd.DataFrame(dd),on='profile'); result[['closed_trades','wins']]=result[['closed_trades','wins']].fillna(0); result['pnl']=result.pnl.fillna(0)
    pd.DataFrame(gate).to_csv(out/'gate_counts.csv',index=False); result.to_csv(out/'summary.csv',index=False)
    print(pd.DataFrame(gate).to_string(index=False)); print(result.to_string(index=False)); store.close()
if __name__=='__main__': main()
