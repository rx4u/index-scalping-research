"""Research candidate signals. Every signal uses completed bars only."""
import numpy as np
import pandas as pd


def prepare(df):
    d = df.copy()
    d.columns = [str(c).lower().strip() for c in d.columns]
    if 'date' not in d and 'timestamp' in d:
        d = d.rename(columns={'timestamp':'date'})
    required = ['date','open','high','low','close']
    missing = [x for x in required if x not in d]
    if missing: raise ValueError(f'Missing fields: {missing}')
    d['date'] = pd.to_datetime(d['date'])
    d = d.sort_values('date').drop_duplicates('date').reset_index(drop=True)
    for c in ['open','high','low','close']:
        d[c] = pd.to_numeric(d[c], errors='raise')
    if (d.high < d[['open','close','low']].max(axis=1)).any() or (d.low > d[['open','close','high']].min(axis=1)).any():
        raise ValueError('Invalid OHLC')
    d['session'] = d.date.dt.date
    d['minute'] = d.date.dt.hour*60+d.date.dt.minute
    # Indian exchange session: avoid external premarket and closing bars
    d = d[(d.minute >= 9*60+15) & (d.minute <= 15*60+29)].copy().reset_index(drop=True)
    d['prev_close'] = d.close.shift(1).where(d.session.eq(d.session.shift(1)))
    d['tr'] = pd.concat([(d.high-d.low), (d.high-d.prev_close).abs(), (d.low-d.prev_close).abs()],axis=1).max(axis=1)
    # ATR uses ONLY past observations at each completed bar (current bar included).
    d['atr'] = d.groupby('session')['tr'].transform(lambda x: x.rolling(20,min_periods=20).mean())
    return d


def generate(df, method):
    """Return signal at completed bar close: +1 buy underlying proxy, -1 sell, 0 none.
    Parameters fixed ex ante, not optimized. One can test and then discard.
    """
    d = prepare(df)
    d['signal'] = 0
    d['reason'] = ''
    if method == 'noise_band':
        # Prior days' average ABSOLUTE movement from same-session open by minute.
        # A fixed time of day threshold, shifted by full session: no future leakage.
        d['open_session'] = d.groupby('session').open.transform('first')
        d['abs_move'] = (d.close-d.open_session).abs()/d.open_session
        byminute = d.pivot(index='session',columns='minute',values='abs_move')
        # 14 preceding SESSIONS, require 10 historical observations.
        # Shift on sessions before computing signal boundary.
        bands = byminute.shift(1).rolling(14,min_periods=10).mean().stack().rename('band')
        d = d.join(bands, on=['session','minute'])
        d['upper'] = d.open_session*(1+d.band)
        d['lower'] = d.open_session*(1-d.band)
        d['signal'] = np.select([d.close>d.upper,d.close<d.lower],[1,-1],default=0)
        # Use first valid breakout per direction per session; main engine limits positions.
        d['reason'] = 'prior-session time-of-day noise band breakout'
    elif method == 'momentum':
        # 3-bar return with 12-bar trend direction and recent range confirmation.
        # all indicators use completed candles.
        g=d.groupby('session')
        d['ret3'] = d.close/g.close.shift(3)-1
        d['ret12'] = d.close/g.close.shift(12)-1
        d['prior_high'] = g.high.transform(lambda x: x.shift(1).rolling(8,min_periods=8).max())
        d['prior_low'] = g.low.transform(lambda x: x.shift(1).rolling(8,min_periods=8).min())
        long=(d.ret3>0)&(d.ret12>0)&(d.close>d.prior_high)
        short=(d.ret3<0)&(d.ret12<0)&(d.close<d.prior_low)
        d['signal']=np.select([long,short],[1,-1],0)
        d['reason']='3/12-bar momentum with prior 8-bar breakout'
    elif method == 'exhaustion':
        # Counter-trend failed extension: prior candle extreme then reject and close
        # back inside its range; highly speculative, explicitly unvalidated.
        g=d.groupby('session')
        priorhigh=g.high.shift(1)
        priorlow=g.low.shift(1)
        range20 = g.high.transform(lambda x:x.shift(1).rolling(20,min_periods=20).max()) - g.low.transform(lambda x:x.shift(1).rolling(20,min_periods=20).min())
        # trend prior to reversal
        ret10 = d.close/g.close.shift(10)-1
        long=(ret10<-.001)&(d.low<priorlow)&(d.close>priorlow)&((d.high-d.low)>.1*range20)
        short=(ret10>.001)&(d.high>priorhigh)&(d.close<priorhigh)&((d.high-d.low)>.1*range20)
        d['signal']=np.select([long,short],[1,-1],0)
        d['reason']='failed extension / reversal candidate'
    else:
        raise ValueError(f'Unknown strategy {method}')
    # Wait until the first 30 minutes; no new entries after 14:45.
    d.loc[(d.minute<9*60+45)|(d.minute>14*60+45),'signal']=0
    return d
