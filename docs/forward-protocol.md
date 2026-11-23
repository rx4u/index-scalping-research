# Forward test protocol

Rules frozen on 23 November 2026 at revision `1567124`. Use the half-hour opposite-band breakout in `paper_rules.py` with the same 14-session warmup, unit exposure and minute-open fills. Include all complete regular sessions, account for flat days and costs, and use the previous complete session for the prior close. Preserve dated source revisions and file hashes.

- **Archive extension** begins 2 November 2026 after the earlier test ended 30 October 2026. It uses observations that predate this freeze. Report these separately as a check on data and execution.
- **Prospective test** begins 24 November 2026, the first calendar date after the protocol freeze. Evaluate each market once at its first session with at least 100 complete sessions and 100 round trips. Fewer observations remain insufficient. The session and trade minimums match the original research configuration.
- **Decision rule** uses the lower bound of the 97.5% two-sided circular five-session block-bootstrap interval for mean net index points per trade at 2 bp. This controls the two-index family at 5%. Keep the original seed and 4,000 draws. Report 1 and 5 bp as sensitivity checks. A positive lower bound supports follow-up on a tradable instrument. Simulated index points cannot establish option returns.

The replay uses delayed public archives and includes no orders. Keep the prospective result separate from any other strategy or parameter experiments.

## Archive extension results

The pinned public archives end on 20 November 2026. Both contain 14 complete regular sessions from 2–20 November. The shortened 8 November session was excluded by the same completeness rule.

| Index | Round trips | Net points at 1 bp | Net points at 2 bp | Net points at 5 bp |
|---|---:|---:|---:|---:|
| Nifty 50 | 13 | +546.01 | +513.57 | +416.24 |
| Sensex | 10 | +717.45 | +635.80 | +390.87 |

The period is short and both indices rose sharply during November. The archive closes on 20 November match published closing levels. There are zero prospective sessions in these revisions. [Metrics](../evidence/forward_metrics.csv) · [Source manifest](../evidence/forward_manifest.json) · [Reported closing levels](https://www.reuters.com/world/india/indian-stocks-seen-falling-nine-month-highs-asia-market-rout-deepens-2026-11-20/)

The public runner includes this extension. To evaluate a new pinned set of files, copy the generated `reports/forward_config.json` and replace its file lists with the September–November warmup and extension archives plus subsequent files. Update the source revisions to match the input and run `python forward_check.py --config <config> --out reports`. The runner publishes only counts for the prospective phase until each market reaches the threshold.
