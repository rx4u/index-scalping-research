"""Persist and replay read-only exchange-timestamped last-trade events."""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from strategies import timestamps


def normalize(frame):
    ticks = frame[["instrument", "date", "sequence", "price"]].copy()
    ticks["date"] = timestamps(ticks.date)
    ticks[["sequence", "price"]] = ticks[["sequence", "price"]].apply(pd.to_numeric)
    if (ticks.instrument.isna().any() or not np.isfinite(ticks[["sequence", "price"]]).all().all()
            or ticks.price.le(0).any() or ticks.sequence.mod(1).ne(0).any()
            or ticks.duplicated(["instrument", "date", "sequence"]).any()):
        raise ValueError("Invalid or ambiguous trade ticks")
    return ticks.sort_values(["instrument", "date", "sequence"]).reset_index(drop=True)


def bars(frame, seconds):
    if seconds not in (5, 15, 60, 180):
        raise ValueError("Unsupported interval")
    ticks = normalize(frame)
    session_open = ticks.date.dt.normalize() + pd.Timedelta(hours=9, minutes=15)
    elapsed = (ticks.date - session_open).dt.total_seconds()
    ticks = ticks[elapsed.between(0, 375 * 60, inclusive="left")].copy()
    ticks["date"] = session_open + pd.to_timedelta(elapsed // seconds * seconds, unit="s")
    result = ticks.groupby(["instrument", "date"]).price.agg(
        open="first", high="max", low="min", close="last", ticks="size").reset_index()
    result["available"] = result.date + pd.Timedelta(seconds=seconds)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seconds", required=True, type=int)
    args = parser.parse_args()
    ticks = normalize(pd.read_csv(args.input))
    result = bars(ticks, args.seconds)
    with Path(args.archive).open("x") as file:
        ticks.to_csv(file, index=False)
    result.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
