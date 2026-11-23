# Nifty / Sensex intraday strategy research, v0.1

**Status:** Runnable research code. Not an independently verified profitable trading system. No live orders. No option backtest. No fabricated performance claims.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Get underlying minute data from Zerodha

Create Kite Connect credentials at https://developers.kite.trade/ . Set credentials in your **local terminal** (never share keys with anyone or paste into chat).

```bash
export KITE_API_KEY='YOUR_LOCAL_KEY'
export KITE_ACCESS_TOKEN='YOUR_LOCAL_TOKEN'
python kite_download.py --symbol 'NIFTY 50' --from-date 2026-01-01 --to-date 2026-11-20 --output nifty_1m.csv
python kite_download.py --symbol 'SENSEX' --from-date 2026-01-01 --to-date 2026-11-20 --output sensex_1m.csv
```

If an index token is unavailable in your instrument list, supply an independently obtained `date,open,high,low,close` CSV and skip the downloader. Kite historical minute data is not historical option tick data. Expired derivatives contracts are not generally reconstructed through the continuous-minute API.

## Run research proxies

```bash
python backtest.py --csv nifty_1m.csv --cost-points 1.5 --out nifty
python backtest.py --csv sensex_1m.csv --cost-points 5 --out sensex
```

These are **UNDERLYING POINTS ONLY**, not option rupees/P&L; `--cost-points` is a hypothetical cost stress test in index points, not a correct brokerage model. Do not convert them into option profits or trade the signals directly. The reported summaries are in-sample descriptive outcomes; split chronologically for out-of-sample evaluation.

The three candidate rules (not asserted to reproduce research papers exactly):

1. `noise_band`: at each minute, prior 14 sessions' rolling mean absolute move from that session's open at the same minute; breakout above/below today's open +/- historical normalised move. Requires 10 prior sessions. Entry next bar open.
2. `momentum`: 3-bar and 12-bar same-session return have same sign; close breaks preceding 8 completed bars' high/low. Entry next bar open.
3. `exhaustion`: directional prior 10-bar move, failed breakout of prior candle extreme, and minimum range condition. Countertrend candidate, **speculative**.

Single position at a time; max 2 entries per session; entries 09:45–14:45 IST; default 1x ATR20 stop, 1.5R target, exit by 15:15; hard stop wins if both target and stop hit in same bar. Fill next bar open. No intrabar future knowledge is used when forming signals. The ATR includes the completed signal candle. Stop fill is conservatively adjusted for gaps but **not** for microstructure slippage. No optimisation is conducted in this version.

## Before considering live signals

- Acquire timestamped historical CE/PE quotes or tick/bid-ask data with contract expiry and strike identifiers, ideally multiple years. Zerodha historical 1-minute index candles cannot verify 5/15-second option P&L.
- Backtest actual option contracts, realistic fills, fees, taxes, spread, slippage, and liquidity; paper-forward test.
- Split chronologically (development, validation, untouched test), compare to simple/no-trade baselines, and measure drawdowns and profitability stability.
- Implement actual MLMI formula only if the original algorithm and configuration can be verified.
- Implement safeguards and execution monitoring before any automation. Never use live order placement in v0.1.

## Official API references
- https://kite.trade/docs/connect/v3/historical/
- https://kite.trade/docs/connect/v3/websocket/
- https://kite.trade/docs/pykiteconnect/v4/
