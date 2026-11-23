"""Replay the frozen half-hour rule on dates following the original study."""
import argparse
import json
from pathlib import Path

import pandas as pd

from backtest import summary
from paper_rules import replay
from research import read_index
from strategies import prepare

EXTENSION_START = "2026-11-02"
PROSPECTIVE_START = "2026-11-24"
MIN_SESSIONS = 100
MIN_TRADES = 100
COSTS = (1, 2, 5)


def milestone(sessions, trades):
    counts = trades.groupby("session").size().reindex(sessions, fill_value=0)
    reached = counts.cumsum().iloc[MIN_SESSIONS - 1:]
    eligible = reached[reached >= MIN_TRADES]
    return eligible.index[0] if len(eligible) else None


def run(config, output):
    output.mkdir(parents=True, exist_ok=True)
    rows, provenance = [], {}
    for instrument, spec in config["instruments"].items():
        raw, hashes = read_index(spec)
        bars = prepare(raw)
        trades = replay(bars, "noise_opposite_band")
        dates = sorted(bars.session.unique())
        if sum(day < EXTENSION_START for day in dates) < 14:
            raise ValueError(f"{instrument} needs 14 complete sessions before the archive extension")
        extension = [day for day in dates if EXTENSION_START <= day < PROSPECTIVE_START]
        future = [day for day in dates if day >= PROSPECTIVE_START]
        end = milestone(future, trades)
        provenance[instrument] = dict(sha256=hashes, source=spec.get("source"), revision=spec.get("revision"),
                                      coverage=bars.attrs["coverage"], prospective_sessions=len(future),
                                      prospective_trades=int(trades.session.isin(future).sum()),
                                      prospective_milestone=end)
        for phase, sessions in [("archive_extension", extension),
                                ("prospective", [day for day in future if end and day <= end])]:
            selected = trades[trades.session.isin(sessions)]
            for cost in COSTS:
                row = dict(instrument=instrument, phase=phase, cost_bps=cost)
                if phase == "prospective" and end is None:
                    rows.append(dict(row, status="INSUFFICIENT DATA", sessions=len(future),
                                     trades=provenance[instrument]["prospective_trades"]))
                    continue
                net = selected.assign(net_points=selected.gross_points - selected.turnover * cost / 20000)
                metrics = summary(net, sessions, alpha=.025)
                status = "EXPLORATORY" if phase == "archive_extension" and sessions else "INSUFFICIENT DATA"
                if phase == "prospective":
                    status = "SENSITIVITY" if cost != 2 else (
                        "PASS" if metrics["bootstrap_low"] > 0 else "FAIL")
                rows.append(dict(row, status=status, first_session=sessions[0] if sessions else None,
                                 last_session=sessions[-1] if sessions else None, **metrics))
    pd.DataFrame(rows).to_csv(output / "forward_metrics.csv", index=False)
    (output / "forward_manifest.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("reports"))
    args = parser.parse_args()
    run(json.loads(args.config.read_text()), args.out)
