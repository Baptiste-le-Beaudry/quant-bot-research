"""Calendar-year FIXED results for the frozen paper risk profiles."""
from pathlib import Path
import sys
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quant_bot.config import RISK_PROFILES, TAKER_FEE_PCT, SLIPPAGE_PCT_EST
from quant_bot.risk import RiskLimits, ExecutionCosts, simulate_portfolio
from scripts.validate_fixed_candidate import annual

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'docs/forward_paper/fixed_validation_20260825/fixed_candidate_trades.csv'
OUT=ROOT/'docs/forward_paper/fixed_validation_20260825'

def main():
    trades=pd.read_csv(DATA,parse_dates=['entry_time','exit_time'])
    costs=ExecutionCosts(TAKER_FEE_PCT,SLIPPAGE_PCT_EST/2)
    all_rows=[]
    for name in ('aggressive','max-risk'):
        p=RISK_PROFILES[name]
        limits=RiskLimits(p['risk_pct'],p['max_portfolio_open_risk'],p['max_gross_exposure'],p['hard_leverage_ceiling'],True,0.01)
        log,_,metrics=simulate_portfolio(trades,limits,costs)
        years=annual(log,trades.entry_time.min(),trades.exit_time.max())
        years.insert(0,'profile',name)
        years['whole_period_cagr_pct']=metrics['cagr_pct']
        years['whole_period_max_dd_pct']=metrics['max_dd_pct']
        years['whole_period_calmar']=metrics['calmar']
        all_rows.append(years)
    result=pd.concat(all_rows,ignore_index=True)
    result.to_csv(OUT/'fixed_aggressive_maxrisk_calendar_years.csv',index=False)
    print(result[['profile','year','status','starting_capital','ending_capital','return_pct','executed_trades','profit_factor','win_rate_pct','max_dd_pct','net_pnl']].to_string(index=False))
if __name__=='__main__': main()
