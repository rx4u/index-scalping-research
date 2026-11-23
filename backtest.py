"""Conservative single-position bar-based research runner; NOT an option backtest.

Signals on close(t); fills at next open(t+1), if same exchange session.
Stops/targets checked on subsequent bars; stop takes precedence if both touched.
Gap through stop fills at worse opening price; no trade execution at signal candle.
"""
import argparse
import pandas as pd
from strategies import generate

METHODS=['noise_band','momentum','exhaustion']

def run(df, strategy, stop_atr=1.0, target_r=1.5, cost_points=0.0, max_trades=2):
    d=generate(df,strategy)
    trades=[]; last_session=None; count=0; i=0
    while i<len(d)-1:
        r=d.iloc[i]
        if r.session!=last_session:
            last_session=r.session;count=0
        if count>=max_trades or r.signal==0 or pd.isna(r.atr) or r.atr<=0:
            i+=1;continue
        nextbar=d.iloc[i+1]
        if nextbar.session!=r.session:
            i+=1;continue
        direction=int(r.signal); entry=float(nextbar.open)
        risk=float(r.atr)*stop_atr
        sl=entry-direction*risk
        tp=entry+direction*risk*target_r
        # From entry bar: conservative if stop/target same bar. No entry at signal close.
        exit_px=None; exit_time=None; exit_reason=None
        j=i+1
        while j<len(d):
            b=d.iloc[j]
            if b.session!=r.session:
                # Last same-day bar exited at previous close (no overnight holding).
                prev=d.iloc[j-1];exit_px=float(prev.close);exit_time=prev.date;exit_reason='session_end';break
            hit_sl=(b.low<=sl) if direction==1 else (b.high>=sl)
            hit_tp=(b.high>=tp) if direction==1 else (b.low<=tp)
            if hit_sl:
                # Gap-open worse than stop: model worse fill.
                exit_px=min(sl,float(b.open)) if direction==1 else max(sl,float(b.open))
                exit_reason='stop'
            elif hit_tp:
                exit_px=tp;exit_reason='target'
            elif b.minute>=15*60+15:
                exit_px=float(b.close);exit_reason='time_exit'
            if exit_px is not None:
                exit_time=b.date;break
            j+=1
        if exit_px is None:
            b=d.iloc[-1];exit_px=float(b.close);exit_time=b.date;exit_reason='data_end'
        gross=(exit_px-entry)*direction
        trades.append({'strategy':strategy,'session':str(r.session),'signal_time':str(r.date),
                       'entry_time':str(nextbar.date),'exit_time':str(exit_time),
                       'side':'LONG' if direction==1 else 'SHORT','entry':round(entry,4),
                       'stop':round(sl,4),'target':round(tp,4),'exit':round(exit_px,4),
                       'reason':exit_reason,'gross_points':round(gross,4),
                       'net_points':round(gross-cost_points,4),'R_net':round((gross-cost_points)/risk,4)})
        count+=1
        # block entering same exit bar (next signal starts after completed exit bar)
        i=max(j+1,i+2)
    return pd.DataFrame(trades)

def summary(trades):
    if trades.empty:
        return {'trades':0,'win_rate':None,'avg_net_points':None,'net_points':None,'profit_factor':None,'max_drawdown_points':None}
    pnl=trades.net_points
    equity=pnl.cumsum()
    pos=pnl[pnl>0].sum();neg=-pnl[pnl<0].sum()
    return {'trades':len(trades),'win_rate':round(100*(pnl>0).mean(),2),
            'avg_net_points':round(pnl.mean(),3),'net_points':round(pnl.sum(),3),
            'profit_factor':round(float(pos/neg),3) if neg>0 else None,
            'max_drawdown_points':round(float((equity.cummax().clip(lower=0)-equity).max()),3)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--csv',required=True,help='Underlying 1m CSV with date,open,high,low,close')
    p.add_argument('--cost-points',type=float,default=1.,help='ROUND TRIP index points, proxy only')
    p.add_argument('--out',default='results')
    a=p.parse_args()
    df=pd.read_csv(a.csv)
    rows=[]
    for method in METHODS:
        t=run(df,method,cost_points=a.cost_points)
        t.to_csv(f'{a.out}_{method}_trades.csv',index=False)
        rows.append({'strategy':method,**summary(t)})
    s=pd.DataFrame(rows);s.to_csv(f'{a.out}_summary.csv',index=False)
    print(s.to_string(index=False))

if __name__=='__main__': main()
