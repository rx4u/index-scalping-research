# Codex Cloud task: evidence-based Nifty / Sensex options scalping research

You are an independent quantitative researcher and Python engineer. Start by auditing the existing files in this repository. Treat all three existing strategies as unvalidated hypotheses, not reproductions of published studies or profitable signals.

## Mandatory research process
1. Find original primary sources for intraday noise-band breakout, intraday momentum, and short-term reversal. Record authors, publication, market, sample dates, precise signal rules, costs, reported results, limitations, and source links in docs/research.md. Distinguish peer-reviewed evidence from SSRN/preprints and commercial backtests. Never invent evidence.
2. Create a reproducible research manifest (data sources, versions, contract specifications, trading calendar, timestamp timezone, dependency versions, seed, configuration).
3. Audit strategies.py, backtest.py and kite_download.py for errors, missing bar/session handling, timezone bugs, look-ahead, data gaps, optimistic fills, entry-bar same-bar stop/target assumptions, gap handling, and invalid index cost proxies. Write unit tests, including adversarial synthetic cases.
4. Independently implement and test the candidate rules with explicit parameter configurations; do not imply that current prototype rules match papers. Add a naive baseline and a no-trade benchmark.
5. Collect or import authentic NIFTY 50 and SENSEX 1-minute OHLC data where accessible. Never fabricate historical data. Preserve provenance. If authenticated Kite Connect data is inaccessible in cloud, provide clear commands, data contract and blockers rather than invented results. Tokens must be sourced only from secret environment variables, never stored, logged or committed.
6. Chronological development, validation, untouched test partitions and expanding walk-forward evaluation, with no overlapping leakage. Report number of sessions and trades by period.
7. Report per strategy and instrument: trade count, win rate, gross/net expectancy, profit factor, max drawdown, median holding time, tail losses, turnover, sensitivity to costs, parameter stability, bootstrap uncertainty and trades/day. Disclose when sample sizes are too small.
8. Critical: underlying index points are NOT option P&L. Do not claim option profits from index-only candles. For actual options research, implement a separate CE/PE instrument loader keyed by strike, expiry, tick timestamps, bid/ask and contract specs. Require executable entry at ask and exit at bid, fees, taxes, spread, slippage, lot sizes, expiry, liquidity gates, latency and partial fills. If true bid/ask is unavailable, label proxy assumptions and do not call options profitability verified.
9. Explore 1-minute and 3-minute signal generation and 5-second/15-second option execution ONLY with appropriately granular data. Reconstruct streaming bars accurately with exchange timestamps and persist ticks for future replay. Never pretend 1-minute OHLC can validate 5-second fills.
10. Do not use MLMI as a verified signal without audited formula and parameter settings. If implemented as an experimental filter, assess its incremental out-of-sample benefit.
11. Build a compact CLI and a report/dashboard with evidence status, source provenance, strategies compared and explicit PASS / FAIL / INSUFFICIENT DATA outcomes. Deliver usable example configuration, setup documentation and all passing tests.
12. Never call a strategy profitable without genuine reproducible out-of-sample, net-of-cost evidence. Avoid post-hoc tuning, survivorship bias and multiple-comparison errors. Do not place or enable live trades, accept order permissions, or expose trading secrets.

## Deliverables
- docs/research.md with linked primary sources and faithful method descriptions.
- Audited engine and automated test suite with test outputs.
- Robust data import for index and options, plus Kite integration isolated behind credentials.
- Reproducible reports containing only actual available historical results, with missing data clearly identified.
- A PR from a feature branch describing the changes, test commands, evidence, limitations, and next data requirements.

Proceed autonomously with available public data and code. Do not block on credentials: complete all offline tasks and document authenticated-data gaps.
