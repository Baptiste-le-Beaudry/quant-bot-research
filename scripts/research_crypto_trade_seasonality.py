"""Calendar concentration audit for the adopted FIXED9 walk-forward ledger."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'docs'/'multi_crypto_portfolio_9sym_xrpp80_linkp95_trades.csv'
OUT=ROOT/'outputs'/'crypto_volatility_research'; OUT.mkdir(parents=True,exist_ok=True)

def main():
    x=pd.read_csv(SOURCE,parse_dates=['entry_time','exit_time']).sort_values('entry_time')
    x['year']=x.entry_time.dt.year; iso=x.entry_time.dt.isocalendar(); x['iso_year']=iso.year.astype(int); x['iso_week']=iso.week.astype(int)
    x['week_start']=(x.entry_time.dt.floor('D')-pd.to_timedelta(x.entry_time.dt.weekday,unit='D')).dt.date.astype(str)
    x['weekday']=x.entry_time.dt.day_name(); x['month']=x.entry_time.dt.month
    x['win']=x.raw_return>0
    annual=x.groupby('year').agg(trades=('raw_return','size'),symbols=('symbol','nunique'),win_rate=('win','mean'),mean_raw_return=('raw_return','mean'),median_raw_return=('raw_return','median'),sum_raw_return=('raw_return','sum'),first=('entry_time','min'),last=('entry_time','max')).reset_index()
    weekly=x.groupby('week_start').agg(trades=('raw_return','size'),symbols=('symbol','nunique'),win_rate=('win','mean'),mean_raw_return=('raw_return','mean'),sum_raw_return=('raw_return','sum')).reset_index()
    # Include zero-trade weeks inside the observed OOS envelope.
    all_weeks=pd.DataFrame({'week_start':pd.date_range(pd.Timestamp(x.entry_time.min()).floor('D')-pd.Timedelta(days=x.entry_time.min().weekday()),pd.Timestamp(x.entry_time.max()).floor('D'),freq='7D').date.astype(str)})
    weekly=all_weeks.merge(weekly,on='week_start',how='left'); weekly[['trades','symbols']]=weekly[['trades','symbols']].fillna(0).astype(int)
    monthly=x.groupby('month').agg(trades=('raw_return','size'),win_rate=('win','mean'),mean_raw_return=('raw_return','mean'),sum_raw_return=('raw_return','sum')).reset_index()
    weekday=x.groupby('weekday').agg(trades=('raw_return','size'),win_rate=('win','mean'),mean_raw_return=('raw_return','mean'),sum_raw_return=('raw_return','sum')).reindex(['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']).reset_index()
    annual.to_csv(OUT/'seasonality_annual.csv',index=False); weekly.to_csv(OUT/'seasonality_weekly.csv',index=False); monthly.to_csv(OUT/'seasonality_month_of_year.csv',index=False); weekday.to_csv(OUT/'seasonality_weekday.csv',index=False)
    q=weekly.trades.quantile([0,.25,.5,.75,.9,.95,1])
    concentration=(weekly.sort_values('trades',ascending=False).head(max(1,int(np.ceil(len(weekly)*.10)))).trades.sum()/max(1,weekly.trades.sum()))
    print('ANNUAL\n',annual.to_string(index=False)); print('\nWEEKLY TRADE QUANTILES\n',q.to_string()); print('zero_weeks',int((weekly.trades==0).sum()),'of',len(weekly),'top_10pct_share',concentration)
    print('\nMONTH\n',monthly.to_string(index=False)); print('\nWEEKDAY\n',weekday.to_string(index=False))
if __name__=='__main__': main()
