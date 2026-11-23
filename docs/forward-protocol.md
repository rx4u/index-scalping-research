# Forward test protocol

Rules frozen on 23 November 2026 at revision `1567124`. Use the half-hour opposite-band breakout in `paper_rules.py` with the same 14-session warmup, unit exposure and minute-open fills. Include all complete regular sessions, account for flat days and costs, and use the previous complete session for the prior close. Preserve dated source revisions and file hashes.

- **Archive extension** begins 2 November 2026 after the earlier test ended 30 October 2026. It uses observations that predate this freeze. Report these separately as a check on data and execution.
- **Prospective test** begins 24 November 2026, the first calendar date after the protocol freeze. Evaluate each market once at its first session with at least 100 complete sessions and 100 round trips. Fewer observations remain insufficient. The session and trade minimums match the original research configuration.
- **Decision rule** uses the lower bound of the 97.5% two-sided circular five-session block-bootstrap interval for mean net index points per trade at 2 bp. This controls the two-index family at 5%. Keep the original seed and 4,000 draws. Report 1 and 5 bp as sensitivity checks. A positive lower bound supports follow-up on a tradable instrument. Simulated index points cannot establish option returns.

The replay uses delayed public archives and includes no orders. Keep the prospective result separate from any other strategy or parameter experiments.
