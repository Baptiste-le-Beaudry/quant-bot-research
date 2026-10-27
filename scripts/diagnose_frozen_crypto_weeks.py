"""Weekly signal-gate audit for the frozen FIXED9 crypto model."""
from __future__ import annotations
import glob, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; PAPER=ROOT/'paper_trading_bot'
sys.path.insert(0,str(PAPER))
from quant_bot.features.build import build_feature_matrix
from quant_bot.forward.signal_engine import load_bundle

END=pd.Timestamp('2026-08-17T00:00:00Z'); START=END-pd.Timedelta(weeks=12)
WARM=START-pd.Timedelta(minutes=1000)

def load(symbol):
    path=sorted(glob.glob(str(ROOT/'data'/f'{symbol}_1m_*.csv')))[-1]; parts=[]
    for x in pd.read_csv(path,index_col=0,parse_dates=True,chunksize=250_000):
        x.index=pd.to_datetime(x.index,utc=True); y=x[(x.index>=WARM)&(x.index<END)]
        if len(y): parts.append(y)
        if len(x) and x.index[-1]>=END: break
    z=pd.concat(parts).sort_index()
    expected=pd.date_range(WARM,END-pd.Timedelta(minutes=1),freq='min',tz='UTC')
    missing=expected.difference(z.index); duplicates=int(z.index.duplicated().sum())
    if len(missing) or duplicates: raise RuntimeError(f'{symbol}: missing={len(missing)} duplicates={duplicates}')
    return z

def main():
    out=ROOT/'outputs'/'crypto_weekly_gate_audit'; out.mkdir(parents=True,exist_ok=True)
    bundle=load_bundle(PAPER/'docs'/'forward_paper'/'strategy_a_bundle.pkl'); rows=[]; distributions=[]
    for symbol,cfg in bundle.configs.items():
        raw=load(symbol); X=build_feature_matrix(raw); p=cfg.model.predict_proba(X)
        active=(X.index>=START)&(X.index<END); X=X.loc[active]; p=p.loc[active]
        pg=p>cfg.threshold; rg=X.range_pos_60<cfg.range_pos_cut; vg=X.realized_vol_30>cfg.realized_vol_cut
        week=((X.index-START)//pd.Timedelta(weeks=1)).astype(int)
        for w in range(12):
            m=week==w
            rows.append({'week_start':(START+pd.Timedelta(weeks=w)).date().isoformat(),'symbol':symbol,'bars':int(m.sum()),
                'probability_pass':int((pg&m).sum()),'range_pass':int((rg&m).sum()),'volatility_pass':int((vg&m).sum()),
                'prob_range_pass':int((pg&rg&m).sum()),'prob_vol_pass':int((pg&vg&m).sum()),
                'all_gates_pass':int((pg&rg&vg&m).sum()),'max_probability':float(p[m].max())})
        distributions.append({'symbol':symbol,'prob_threshold':cfg.threshold,'prob_p50':float(p.quantile(.5)),'prob_p90':float(p.quantile(.9)),'prob_p99':float(p.quantile(.99)),'prob_max':float(p.max()),
            'range_cut':cfg.range_pos_cut,'recent_range_p50':float(X.range_pos_60.quantile(.5)),'range_pass_pct':100*float(rg.mean()),
            'vol_cut':cfg.realized_vol_cut,'recent_vol_p50':float(X.realized_vol_30.quantile(.5)),'vol_pass_pct':100*float(vg.mean()),
            'prob_pass_pct':100*float(pg.mean()),'all_pass_pct':100*float((pg&rg&vg).mean())})
    detail=pd.DataFrame(rows); summary=detail.groupby('week_start',as_index=False).agg(bars=('bars','sum'),probability_pass=('probability_pass','sum'),prob_range_pass=('prob_range_pass','sum'),prob_vol_pass=('prob_vol_pass','sum'),signals=('all_gates_pass','sum'))
    detail.to_csv(out/'weekly_by_symbol.csv',index=False); summary.to_csv(out/'weekly_summary.csv',index=False); pd.DataFrame(distributions).to_csv(out/'distribution_diagnostic.csv',index=False)
    print(summary.to_string(index=False)); print('\nTOTALS'); print(summary.sum(numeric_only=True).to_string()); print('\nDISTRIBUTIONS'); print(pd.DataFrame(distributions).to_string(index=False))
if __name__=='__main__': main()
