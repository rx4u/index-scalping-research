# Nifty and Sensex intraday research

The fixed held-out index screen failed for all tested candidates at the reference stress. Five- and fifteen-second options profitability is **INSUFFICIENT DATA**. This repository contains historical analysis and no order-placement code. See the [research report](docs/research.md) and [evidence](evidence/).

## Reproduce the public-data run

Use Python 3.11 or 3.12 and run from the repository root. This workflow downloads free, pinned files, verifies their SHA-256 checksums, runs both index studies and the CE/PE premium comparison, and builds the offline dashboard. It uses no broker credentials.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run_public.py
```

Open `reports/dashboard.html` in a browser. It works offline and includes filterable index metrics, cumulative P&L, trade detail and provenance. Cached inputs live under `data/public`. Use `--cache` and `--out` to choose different directories. To download the report built by GitHub Actions, open the **Public data research** workflow run and download **public-research-report** from its Artifacts section.

To run your own index inputs, copy `config.example.json`, update the paths and date ranges, and call `python research.py --config <path>`. CSV imports require minute **opening** timestamps in `date` or `timestamp` and `open,high,low,close` columns. Naive timestamps default to Asia/Kolkata. To flag absent regular sessions, supply a `calendar` CSV with a `session` column of exchange dates. Paths are relative to the shell's working directory.

## Zerodha Connect setup

1. In the [Kite developer console](https://developers.kite.trade/), select **Connect** for historical candles and live market-data WebSocket access. The app form displays the current credit cost. Enter app name **Index Scalping Research**, your Zerodha Client ID, Redirect URL `http://127.0.0.1:8000/callback`, and description **Historical index candles and market-data replay for research**. Leave Postback URL and icon blank. Connect includes brokerage API capabilities at the platform level. This repository calls historical market data and the session exchange only.
2. In your own local Bash terminal, enter the API key without echoing it. Run the command below and enter your API secret at its hidden prompt. Open the Kite login URL in your browser, sign in, then paste the redirected URL or its request token into the hidden prompt. The callback may display a connection error with the URL still visible. Complete this promptly because the request token is short-lived. Keep the API key, secret, request token and access token in your local environment or hidden input. [Desktop redirects](https://kite.trade/docs/connect/v3/apps/) · [Login and token exchange](https://kite.trade/docs/connect/v3/user/)
3. Start with a short historical download. Use 2026-11-16–2026-11-20, for example. Swap the symbol/output to download the other index. If your local workflow already provides an access token, export `KITE_ACCESS_TOKEN` through your local secret manager or hidden prompt and omit `--login`. The token normally expires at 06:00 IST the following day.

```bash
read -rsp 'Kite API key: ' KITE_API_KEY
export KITE_API_KEY
printf '\n'
python kite_download.py --login --symbol 'NIFTY 50' --from-date 2026-11-16 --to-date 2026-11-20 --output data/nifty_1m.csv
python kite_download.py --login --symbol SENSEX --from-date 2026-11-16 --to-date 2026-11-20 --output data/sensex_1m.csv
unset KITE_API_KEY KITE_API_SECRET KITE_ACCESS_TOKEN
```

Use the downloads by replacing the `csv` paths and source labels in a local copy of the config and setting appropriate split dates. Each download writes its own JSON sidecar with range, exchange, token identifier, coverage and hash.

## Exchange quote and tick replay

Prepare two CSVs, preferably with ISO 8601 timestamps and explicit offsets.

| Input | Required columns |
|---|---|
| Contracts | `contract,instrument,option_type,strike,listed_at,expires_at,lot_size,tick_size` |
| Quotes | `contract,date,bid,ask,bid_size,ask_size` |
| Last-trade tick export | `instrument,date,sequence,price` |

Contract IDs must uniquely identify an exchange series, including strike and exact expiry. Use the same underlying symbol strings as the config, CE or PE, and quote sizes in units. Supply the actual contract existence times from the historical master. Normalize multiple events at the same timestamp into an explicitly ordered snapshot upstream. Preserve the raw event log and event-time resolution. Do not forward-fill missing depth or build quotes from OHLC. Give the replay a single exchange and fee period per run. Slice `index_trades.csv` to the intended instrument, date range, phase and documented test before replay. Run both 5 and 15 seconds to compare, using the same holdout. The engine emits a status per signal including missing contracts, unfilled entries and unresolved exits. For verified results use an audited spread/depth feed and evaluate unresolved positions in the denominator.

```bash
python tick_bars.py --input data/trade_ticks.csv --archive data/normalized_ticks.csv --out data/bars_5s.csv --seconds 5
python options.py --schedule data/selected_index_trades.csv --contracts data/contracts.csv --quotes data/quotes.csv --seconds 5 --exchange-rate 0.0003553 --stt-rate 0.0015 --out reports/nifty_replay_5s.csv
```

The sample rate flags are for NSE options at the post-April-2026 schedule used in the proxy. Use the period-appropriate values for a real tape and reconcile against contract notes. The quote mode replays an underlying-derived schedule, with its bar-level stop trigger resolution. Minute premium proxies have their own clearly labeled report.
