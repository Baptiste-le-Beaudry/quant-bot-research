"""Leakage-safe walk-forward screen of volatility-gate alternatives.

Research-only: does not import or modify the forward runtime configuration.
Every adaptive statistic is causal (uses the current/past window only).
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'/'strategy_a'/'mechanism2'))
from common import SYMBOLS_9,load_symbol,load_symbol_feats,get_folds,fold_layers,build_layer_trades,trades_to_metrics

OUT=ROOT/'outputs'/'crypto_volatility_research'; OUT.mkdir(parents=True,exist_ok=True)
PATH=OUT/'gate_variant_recent_folds.csv'
WINDOWS=(240,1440,10080,43200)

def causal_rank(s,w): return s.rolling(w,min_periods=max(60,w//4)).rank(pct=True)

def masks(res, train_feats, train_proba):
    tf=res['test_feats']; p=res['test_proba']; base=p.gt(.70)&tf.range_pos_60.lt(res['range_pos_cut'])
    yield 'baseline_absolute',base&tf.realized_vol_30.gt(res['vol_cut']),{}
    yield 'no_vol_filter',base,{}
    for w in WINDOWS:
        test_rank=causal_rank(tf.realized_vol_30,w)
        for q in (.50,.60,.70,.80):
            yield f'rolling_percentile_w{w}_q{int(q*100)}',base&test_rank.ge(q),{'window':w,'q':q}
        train_ratio=train_feats.realized_vol_30/train_feats.realized_vol_30.rolling(w,min_periods=max(60,w//4)).median()
        selected=train_proba.gt(.70)&train_feats.range_pos_60.lt(res['range_pos_cut'])
        for q in (.25,.50,.75):
            cut=float(train_ratio[selected].quantile(q))
            test_ratio=tf.realized_vol_30/tf.realized_vol_30.rolling(w,min_periods=max(60,w//4)).median()
            yield f'regime_ratio_w{w}_trainq{int(q*100)}',base&test_ratio.gt(cut),{'window':w,'q':q,'train_ratio_cut':cut}

def main():
    done=set()
    rows=[]
    if PATH.exists():
        old=pd.read_csv(PATH); rows=old.to_dict('records'); done=set(zip(old.symbol,old.fold))
    for symbol in SYMBOLS_9:
        full=load_symbol(symbol); feats=load_symbol_feats(symbol,full); folds,_=get_folds(full)
        for fi,(t0,te,xe) in list(enumerate(folds,1))[-2:]:
            if (symbol,fi) in done: continue
            train=full[(full.index>=t0)&(full.index<te)]; test=full[(full.index>=te)&(full.index<xe)]
            res=fold_layers(symbol,fi,train,test,full_feats=feats)
            if res is None: continue
            train_feats=res['train_feats']; train_proba=res['model'].predict_proba(train_feats)
            for name,mask,params in masks(res,train_feats,train_proba):
                trades=build_layer_trades(res['test_close'],mask.fillna(False),res['test_feats']); met=trades_to_metrics(trades)
                rows.append({'symbol':symbol,'fold':fi,'train_end':te,'test_end':xe,'variant':name,**params,**met})
            pd.DataFrame(rows).to_csv(PATH,index=False); print(symbol,fi,'/',len(folds),'done')
    x=pd.DataFrame(rows); summary=[]
    for name,g in x.groupby('variant'):
        n=int(g.n.sum()); summary.append({'variant':name,'folds':len(g),'trades':n,'zero_trade_folds':int((g.n==0).sum()),
            'weighted_winrate_10m_pct':float((g.winrate_10m_pct.fillna(0)*g.n).sum()/n) if n else np.nan,
            'median_fold_fwdret_10m_pct':float(g.median_fwdret_10m_pct.median()),
            'median_fold_mfe_mae':float(g.mfe_over_abs_mae.median())})
    s=pd.DataFrame(summary).sort_values(['weighted_winrate_10m_pct','median_fold_fwdret_10m_pct'],ascending=False)
    s.to_csv(OUT/'gate_variant_recent_summary.csv',index=False); print(s.to_string(index=False))
if __name__=='__main__': main()
