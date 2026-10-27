"""Registered diagnostics for the frozen A-Equity portfolio candidates."""
from __future__ import annotations

import hashlib, json, sys, warnings
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quant_bot.strategy_a_equity.portfolio import PortfolioLimits, simulate
from scripts.strategy_a_equity.run_portfolio_frontier import Prices, metrics

ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'outputs'/'strategy_a_equity'/'portfolio'
PROFILES={'CONSERVATIVE':(.0025,.05,1.),'NORMAL':(.005,.05,1.5),'AGGRESSIVE':(.0075,.075,2.)}
ACTIVATE=.0063; TRAIL=.008
warnings.filterwarnings('ignore', message='Converting to Period')

def period_rows(states,ledger,freq,universe,model):
    s=states.sort_values(['timestamp','phase']).set_index('timestamp'); rows=[]
    for period,g in s.groupby(s.index.to_period(freq)):
        vals=g.equity.to_numpy(); start=float(vals[0]); end=float(vals[-1]); peaks=np.maximum.accumulate(vals)
        sub=ledger[pd.to_datetime(ledger.exit_time,utc=True).dt.to_period(freq)==period]; pnl=sub.pnl
        wins=pnl[pnl>0].sum(); losses=-pnl[pnl<0].sum()
        rows.append({'universe':universe,'model':model,'period':str(period),'start_equity':start,
          'end_equity':end,'return_pct':(end/start-1)*100,'max_dd_pct':float((vals/peaks-1).min()*100),
          'trades':len(sub),'profit_factor':wins/losses if losses else np.inf,
          'win_rate_pct':100*(pnl>0).mean() if len(pnl) else np.nan,'pnl_contribution':pnl.sum(),
          'partial_period':True if (period==s.index.min().to_period(freq) or period==s.index.max().to_period(freq)) else False})
    return rows

def bootstrap(x,n=2000,block=1,seed=42,years=None):
    x=np.asarray(x,float); rng=np.random.default_rng(seed); dds=[]; ends=[]; cagrs=[]
    years=max(float(years if years is not None else len(x)/252),1/252)
    for _ in range(n):
        if block==1: sample=rng.choice(x,len(x),replace=True)
        else:
            starts=rng.integers(0,len(x),size=int(np.ceil(len(x)/block)))
            sample=np.concatenate([x[(np.arange(a,a+block)%len(x))] for a in starts])[:len(x)]
        eq=np.cumprod(1+sample); path=np.r_[1., eq]
        dd=path/np.maximum.accumulate(path)-1
        ends.append(eq[-1]); dds.append(dd.min()*100); cagrs.append((eq[-1]**(1/years)-1)*100 if eq[-1]>0 else -100)
    d=np.array(dds); e=np.array(ends); c=np.array(cagrs)
    return {'median_cagr':np.median(c),'p5_cagr':np.percentile(c,5),'p95_maxdd':np.percentile(d,5),
      'p99_maxdd':np.percentile(d,1),'p_dd_gt20':(d<-20).mean(),'p_dd_gt30':(d<-30).mean(),
      'p_dd_gt40':(d<-40).mean(),'p_final_below_initial':(e<1).mean(),'simulations':n,'seed':seed,'block':block}

def delayed(data,minutes,prices):
    out=data.copy(); raws=np.full(len(out),np.nan); exits=np.full(len(out),np.datetime64('NaT'),dtype='datetime64[us]'); new_prices=np.full(len(out),np.nan)
    for symbol, positions in out.groupby('symbol',sort=False).indices.items():
      idx,values=prices.data[symbol]; pos=np.asarray(positions); locs=idx.get_indexer(pd.DatetimeIndex(out.iloc[pos].entry_time))
      if (locs<0).any(): raise RuntimeError(f'missing stress entry index: {symbol}')
      for target,loc in zip(pos,locs):
        r=out.iloc[target]; path=values[loc:loc+51]
        if len(path)<51 or minutes>=len(path)-1: continue
        path=path/path[minutes]-1; protective=float(r.stop_distance); peak=-np.inf; active=False; raw=None; off=len(path)-1
        for j,x in enumerate(path):
            if x<=-protective: raw=-protective; off=j; break
            peak=max(peak,x); active=active or peak>=ACTIVATE
            if active and x<=peak-TRAIL: raw=peak-TRAIL; off=j; break
        raws[target]=path[-1] if raw is None else raw; exits[target]=(r.entry_time+pd.Timedelta(minutes=minutes+off)).to_datetime64(); new_prices[target]=values[loc+minutes]
    out.raw_return=raws; out.exit_time=pd.to_datetime(exits,utc=True); out.entry_time+=pd.Timedelta(minutes=minutes); out.entry_price=new_prices
    out=out.dropna(subset=['raw_return','exit_time','entry_price']); out.exec_return=out.raw_return-.0002
    return out

def main():
    data={m:pd.read_pickle(OUT/f'audited_candidates_{m}.pkl') for m in ('rf','logistic')}; prices=Prices(sorted(set(pd.concat(data.values()).symbol)))
    prices.prepare(pd.concat(list(data.values())).entry_time)
    ledgers=[]; rejects=[]; yearly=[]; monthly=[]; summaries={}; symbol_rows=[]; daily_corr=[]; marginal=[]; profitable_rows=[]
    marginal_path=OUT/'equity_portfolio_marginal_contribution.csv'; have_marginal=marginal_path.exists()
    for universe,label in {'DISCOVERY':'discovery','CONFIRMATION':'confirmation','COMBINED':None}.items():
      for model,d0 in data.items():
        d=d0 if label is None else d0[d0.universe==label]
        lim=PortfolioLimits(*PROFILES['NORMAL']); ledger,states,rejected=simulate(d,lim,prices); key=f'{universe}_{model}'
        summaries[key]=metrics(ledger,states,rejected); ledger['universe_view']=universe; ledger['model']=model; rejected['universe_view']=universe; rejected['model']=model
        yearly+=period_rows(states,ledger,'Y',universe,model); monthly+=period_rows(states,ledger,'M',universe,model)
        if universe=='COMBINED':
          ledgers.append(ledger); rejects.append(rejected)
          total=ledger.pnl.sum(); pos=ledger.groupby('symbol').pnl.sum().clip(lower=0); hhi=float(((pos/pos.sum())**2).sum())
          for symbol,g in ledger.groupby('symbol'):
            wins=g.loc[g.pnl>0,'pnl'].sum(); losses=-g.loc[g.pnl<0,'pnl'].sum(); vals=100000+g.sort_values('exit_time').pnl.cumsum(); dd=(vals/vals.cummax()-1).min()*100
            symbol_rows.append({'model':model,'symbol':symbol,'trades':len(g),'pnl':g.pnl.sum(),'profit_factor':wins/losses if losses else np.inf,
              'expectancy':g.pnl.mean(),'win_rate_pct':100*(g.pnl>0).mean(),'contribution_pct':100*g.pnl.sum()/total,'max_dd_solo_pct':dd,'positive_contribution_hhi':hhi})
          piv=ledger.assign(day=pd.to_datetime(ledger.exit_time,utc=True).dt.floor('D')).pivot_table(index='day',columns='symbol',values='pnl',aggfunc='sum',fill_value=0)
          corr=piv.corrwith(piv.sum(axis=1)); daily_corr += [{'model':model,'symbol':s,'daily_pnl_corr_portfolio':v} for s,v in corr.items()]
          base=summaries[key]
          if not have_marginal:
            for symbol in sorted(d.symbol.unique()):
              l2,s2,r2=simulate(d[d.symbol!=symbol],lim,prices); mm=metrics(l2,s2,r2)
              marginal.append({'model':model,'excluded_symbol':symbol,'delta_cagr':mm['cagr_pct']-base['cagr_pct'],
                'delta_maxdd':mm['max_dd_pct']-base['max_dd_pct'],'delta_calmar':mm['calmar']-base['calmar'],'delta_pnl':mm['total_pnl']-base['total_pnl']})
        if universe=='COMBINED':
          # Explicitly post-hoc diagnostic only: symbol-level mean modeled return > 0.
          winners=sorted(d.groupby('symbol').exec_return.mean().loc[lambda x: x>0].index)
          pdia=d[d.symbol.isin(winners)]; lp,sp,rp=simulate(pdia,lim,prices)
          profitable_rows.append({'model':model,'view':'PROFITABLE_ONLY_DIAGNOSTIC','symbols':len(winners),**metrics(lp,sp,rp)})
    pd.concat(ledgers).to_csv(OUT/'equity_portfolio_trade_ledger.csv',index=False); pd.concat(rejects).to_csv(OUT/'equity_portfolio_signal_rejections.csv',index=False)
    pd.DataFrame(yearly).to_csv(OUT/'equity_portfolio_yearly_returns.csv',index=False); pd.DataFrame(monthly).to_csv(OUT/'equity_portfolio_monthly_returns.csv',index=False)
    pd.DataFrame(symbol_rows).to_csv(OUT/'equity_portfolio_symbol_contribution.csv',index=False)
    if not have_marginal: pd.DataFrame(marginal).to_csv(marginal_path,index=False)
    pd.DataFrame(daily_corr).to_csv(OUT/'equity_portfolio_daily_correlation.csv',index=False)
    pd.DataFrame(profitable_rows).to_csv(OUT/'equity_portfolio_profitable_only_diagnostic.csv',index=False)
    # Stress NORMAL combined. Cost-only scenarios preserve raw paths.
    stress=[]; scenarios={'BASE':.0002,'2X_SLIPPAGE':.0003,'3X_SLIPPAGE':.0004,'SPREAD_EXPANSION':.0003,'COMBINED_COST_ONLY':.0004}
    for model,d in data.items():
      for name,cost in scenarios.items():
        l,s,r=simulate(d,PortfolioLimits(.005,.05,1.5,round_trip_cost=cost),prices); stress.append({'model':model,'scenario':name,**metrics(l,s,r)})
      shifted1=delayed(d,1,prices); shifted2=delayed(d,2,prices)
      for mins,shifted in ((1,shifted1),(2,shifted2)):
        l,s,r=simulate(shifted,PortfolioLimits(.005,.05,1.5),prices); stress.append({'model':model,'scenario':f'ENTRY_PLUS_{mins}MIN',**metrics(l,s,r)})
      l,s,r=simulate(shifted1,PortfolioLimits(.005,.05,1.5,round_trip_cost=.0004),prices); stress.append({'model':model,'scenario':'COMBINED_MODERATE',**metrics(l,s,r)})
    pd.DataFrame(stress).to_csv(OUT/'equity_portfolio_execution_stress.csv',index=False)
    # Bootstrap each registered risk at NORMAL caps from executed daily returns.
    boots=[]
    for model,d in data.items():
      for risk in (.0025,.005,.0075,.01,.0125,.015,.02):
        l,s,r=simulate(d,PortfolioLimits(risk,.05,1.5),prices); st=s.sort_values(['timestamp','phase']).set_index('timestamp').equity.resample('D').last().dropna(); x=st.pct_change().dropna().to_numpy(); years=max(len(x)/252,1/252)
        trade_x=(l.pnl/l.entry_equity).to_numpy()
        for method,arr,block in [('IID_TRADE',trade_x,1),('BLOCK_TRADE_20',trade_x,20),('CLUSTERED_DAY_5',x,5)]:
          boots.append({'model':model,'risk_pct':risk,'method':method,**bootstrap(arr,2000,block,years=years)})
    pd.DataFrame(boots).to_csv(OUT/'equity_portfolio_drawdown_bootstrap.csv',index=False)
    summary={'profiles':{k:{'risk_pct':v[0],'open_risk_cap':v[1],'gross_cap':v[2]} for k,v in PROFILES.items()},'normal':summaries,
      'cost_reconciliation':{'expected_cost':.0002,'commission':0,'spread':.0001,'slippage':.0001,'regulatory_fees':0,'observed_modeled_cost':.0002},
      'sector_analysis':'NOT AVAILABLE: no authoritative sector metadata artifact in repository'}
    (OUT/'equity_portfolio_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')

if __name__=='__main__': main()
