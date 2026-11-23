"""Download historical index minute candles using Kite Connect. Never store secrets in code."""
import os,argparse,time
import pandas as pd
from datetime import datetime,timedelta

def main():
    from kiteconnect import KiteConnect
    p=argparse.ArgumentParser()
    p.add_argument('--symbol',choices=['NIFTY 50','SENSEX'],required=True)
    p.add_argument('--from-date',required=True)
    p.add_argument('--to-date',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    key=os.environ.get('KITE_API_KEY');tok=os.environ.get('KITE_ACCESS_TOKEN')
    if not key or not tok: raise SystemExit('Set KITE_API_KEY and KITE_ACCESS_TOKEN locally (do not share them).')
    kite=KiteConnect(api_key=key);kite.set_access_token(tok)
    exch='NSE' if a.symbol=='NIFTY 50' else 'BSE'
    instruments=kite.instruments(exch)
    matches=[i for i in instruments if i['tradingsymbol']==a.symbol or i.get('name')==a.symbol]
    if len(matches)!=1:raise RuntimeError(f'Could not uniquely resolve {a.symbol} in {exch}. Matches: {matches[:5]}')
    token=matches[0]['instrument_token']
    start=datetime.strptime(a.from_date,'%Y-%m-%d')
    end=datetime.strptime(a.to_date,'%Y-%m-%d')
    if end<start: raise ValueError('to-date before from-date')
    out=[];current=start
    while current<=end:
        stop=min(current+timedelta(days=29),end)
        data=kite.historical_data(token,current,stop+timedelta(hours=23,minutes=59),interval='minute')
        out.extend(data);print(current.date(),stop.date(),len(data))
        current=stop+timedelta(days=1)
        time.sleep(.5)
    if not out: raise RuntimeError('No data received. Check subscription, token and instrument.')
    pd.DataFrame(out).drop_duplicates('date').sort_values('date').to_csv(a.output,index=False)
    print('Saved',a.output)
if __name__=='__main__':main()
