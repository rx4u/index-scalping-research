"""Compare the primary public index archive against a second distributor."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from backtest import simulate
from option_proxy import REVISION, SOURCE
from research import read_index, with_cost
from strategies import OHLC, prepare, signals, timestamps


def compare(config, inputs):
    results = {"source": SOURCE, "revision": REVISION, "instruments": {}}
    for instrument, symbol in [("NIFTY 50", "NIFTY"), ("SENSEX", "SENSEX")]:
        primary, _ = read_index(config["instruments"][instrument])
        path = Path(inputs) / f"{symbol}.parquet"
        reference = pd.read_parquet(path)
        reference["date"] = timestamps(reference.timestamp)

        def regular(frame):
            elapsed = frame.date.dt.hour * 60 + frame.date.dt.minute
            return frame.loc[frame.date.dt.strftime("%Y-%m-%d").between(config["start"], config["end"])
                             & elapsed.between(555, 929), ["date", *OHLC]]

        matched = regular(primary).merge(regular(reference), on="date", suffixes=("_primary", "_secondary"),
                                          validate="one_to_one")
        delta = (matched.close_primary - matched.close_secondary).abs()
        results["instruments"][instrument] = dict(
            secondary_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), matched_bars=len(delta),
            first=matched.date.min().isoformat() if len(delta) else None,
            last=matched.date.max().isoformat() if len(delta) else None,
            within_0_05_points=float(delta.le(.0500001).mean()) if len(delta) else None,
            median_absolute_close_diff=float(delta.median()) if len(delta) else None,
            p95_absolute_close_diff=float(delta.quantile(.95)) if len(delta) else None)
        paired = pd.DataFrame({"date": matched.date})
        for suffix in ("primary", "secondary"):
            results["instruments"][instrument][f"{suffix}_test"] = []
            values = matched[[f"{field}_{suffix}" for field in OHLC]].set_axis(OHLC, axis=1)
            frame = pd.concat([paired, values], axis=1)
            for minutes in config["signal_minutes"]:
                bars = prepare(frame, minutes)
                test = bars[bars.session >= config["test_start"]]
                for method in ("noise_band", "momentum", "exhaustion"):
                    candidates = signals(bars, method)
                    trades = simulate(candidates[candidates.session >= config["test_start"]],
                                      method, config["stop_atr"], config["target_r"],
                                      max_trades=config["max_trades"])
                    net = with_cost(trades, config["reference_bps"]).net_points.sum()
                    row = dict(minutes=minutes, strategy=method, sessions=test.session.nunique(),
                               trades=len(trades), net_points=float(net))
                    results["instruments"][instrument][f"{suffix}_test"].append(row)
    results["reference_bps"] = config["reference_bps"]
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--out", default="reports/source_crosscheck.json")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    Path(args.out).write_text(json.dumps(compare(config, args.inputs), indent=2) + "\n")
