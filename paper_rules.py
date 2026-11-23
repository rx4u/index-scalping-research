"""Exploratory spot-index transfers of two published intraday rule sets."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import summary
from research import read_index
from strategies import noise_bands, prepare

METHODS = ("gao_sign", "noise_opposite_band", "close_long")
COLUMNS = ["session", "entry_time", "exit_time", "side", "entry", "exit",
           "gross_points", "turnover", "holding_seconds"]


def replay(bars, method):
    if method not in METHODS:
        raise ValueError(f"Unknown paper rule: {method}")
    if method == "noise_opposite_band":
        bars = noise_bands(bars)
    trades = []

    def record(session, entry, exit_time, price, side):
        trades.append((session, entry.date, exit_time, side, entry.open, price,
                       side * (price - entry.open), price + entry.open,
                       (exit_time - entry.date).total_seconds()))

    previous_close = None
    for session, day in bars.groupby("session", sort=False):
        day = day.set_index("minute")
        closing = day.iloc[-1]
        if method == "noise_opposite_band":
            side, entry = 0, None
            # 09:30–15:00 IST, exactly on clock half-hours.
            for minute in range(15, 375, 30):
                signal, fill = day.loc[minute - 1], day.loc[minute]
                direction = int(signal.close > signal.upper) - int(signal.close < signal.lower)
                if direction and direction != side:
                    if side:
                        record(session, entry, fill.date, fill.open, side)
                    side, entry = direction, fill
            if side:
                record(session, entry, closing.available, closing.close, side)
        else:
            side = 1
            if method == "gao_sign":
                side = int(np.sign(day.loc[29, "close"] - previous_close)) if previous_close is not None else 0
            if side:
                record(session, day.loc[345], closing.available, closing.close, side)
        previous_close = closing.close
    return pd.DataFrame(trades, columns=COLUMNS)


def evaluate(config, output):
    rows, ledger = [], []
    end_exclusive = (pd.Timestamp(config["end"]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    for instrument, spec in config["instruments"].items():
        raw, _ = read_index(spec)
        day = raw.date.dt.strftime("%Y-%m-%d")
        bars = prepare(raw[day.between(config["start"], config["end"])])
        sessions = sorted(bars.session.unique())
        for method in METHODS:
            trades = replay(bars, method)
            ledger.append(trades.assign(instrument=instrument, strategy=method))
            for period, start, stop in [
                ("development", config["start"], config["validation_start"]),
                ("validation", config["validation_start"], config["test_start"]),
                ("reused_test", config["test_start"], end_exclusive),
            ]:
                days = [day for day in sessions if start <= day < stop]
                subset = trades[trades.session.isin(days)]
                for cost in config["round_trip_bps"]:
                    net = subset.assign(net_points=subset.gross_points - subset.turnover * cost / 20000)
                    rows.append(dict(instrument=instrument, strategy=method, period=period, cost_bps=cost,
                                     **summary(net, days, config["seed"], alpha=.05 / 4)))
    pd.DataFrame(rows).to_csv(output / "paper_metrics.csv", index=False)
    pd.concat(ledger, ignore_index=True).to_csv(output / "paper_trades.csv", index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    evaluate(json.loads(args.config.read_text()), args.out)
