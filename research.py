"""Run chronological index screening and exported analysis."""
import argparse
import glob
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import simulate, summary
from strategies import METHODS, TZ, prepare, signals, timestamps

GRID = {"noise_band": (0.8, 1.0, 1.2), "momentum": (0.8, 1.0, 1.2),
        "exhaustion": (0.8, 1.0, 1.2), "naive": (1.0,), "no_trade": (1.0,)}


def read_index(spec):
    paths = spec["csv"]
    files = sorted(paths if isinstance(paths, list) else glob.glob(paths, recursive=True))
    if not files:
        raise FileNotFoundError(spec["csv"])
    frames, hashes = [], {}
    for name in files:
        path = Path(name)
        frame = pd.read_csv(path)
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        frame.columns = frame.columns.str.lower()
        date = "date" if "date" in frame else "timestamp"
        frame["date"] = timestamps(frame[date], spec.get("timezone", TZ))
        if "epoch" in frame and not frame.date.eq(pd.to_datetime(frame.epoch, unit="s", utc=True)).all():
            raise ValueError(f"Epoch and local timestamp disagree in {path.name}")
        frames.append(frame)
    return pd.concat(frames, ignore_index=True), hashes


def with_cost(trades, cost):
    t = trades.copy()
    charge = t.turnover * cost / 20000
    t["net_points"] = t.gross_points - charge
    t["R_net"] = t.net_points / (t.entry - t.stop).abs()
    return t


def dates_between(sessions, start, stop):
    return [session for session in sessions if start <= session < stop]


def evaluate(config, destination):
    output = Path(destination)
    output.mkdir(parents=True, exist_ok=True)
    start, validation, test, end = (config[key] for key in ("start", "validation_start", "test_start", "end"))
    if not start < validation < test <= end:
        raise ValueError("Invalid chronological partition boundaries")
    stop = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    costs = config["round_trip_bps"]
    reference = config["reference_bps"]
    if reference not in costs or any(not np.isfinite(cost) or cost < 0 for cost in costs):
        raise ValueError("Cost grid must be nonnegative, finite and contain its reference")
    expected = 3 * len(config["instruments"]) * len(config["signal_minutes"])
    manifest = {"configuration": config, "python": platform.python_version(), "pandas": pd.__version__,
                "numpy": np.__version__, "timezone": TZ, "calendar": "Regular 09:15–15:30 IST",
                "bootstrap_draws": 4000, "bootstrap_block_sessions": 5,
                "primary_family_size": expected, "inputs": {}}
    rows, ledgers = [], []
    for instrument, spec in config["instruments"].items():
        raw, hashes = read_index(spec)
        day = raw.date.dt.strftime("%Y-%m-%d")
        calendar = None
        calendar_hash = None
        if spec.get("calendar"):
            calendar_file = Path(spec["calendar"])
            calendar_hash = hashlib.sha256(calendar_file.read_bytes()).hexdigest()
            dates = pd.read_csv(calendar_file, dtype=str).session
            calendar = dates[dates.between(start, end)]
        manifest["inputs"][instrument] = {"sha256": hashes, "calendar_sha256": calendar_hash, "intervals": {}}
        for minutes in config["signal_minutes"]:
            bars = prepare(raw[day.between(start, end)], minutes, calendar=calendar)
            manifest["inputs"][instrument]["intervals"][str(minutes)] = bars.attrs["coverage"]
            sessions = sorted(bars.session.unique())
            periods = {"development": dates_between(sessions, start, validation),
                       "validation": dates_between(sessions, validation, test),
                       "test": dates_between(sessions, test, stop)}
            walk_end = min(test, stop)
            quarters = pd.period_range(validation, pd.Timestamp(walk_end) - pd.Timedelta(days=1), freq="Q")
            for method in METHODS:
                variants = {}
                for factor in GRID[method]:
                    variant = factor if method != "momentum" else 1.
                    variants[factor] = simulate(signals(bars, method, variant), method,
                                                config["stop_atr"] * (factor if method == "momentum" else 1.),
                                                config["target_r"], max_trades=config["max_trades"])
                def record(phase, days, trades, factor, cost, fit_through=None):
                    chosen = with_cost(trades[trades.session.isin(days)], cost)
                    metrics = summary(chosen, days, config["seed"], .05 / expected if phase == "test" else .05)
                    outcome = "BENCHMARK" if method in ("naive", "no_trade") else "DIAGNOSTIC"
                    if phase == "test" and cost == reference and outcome != "BENCHMARK":
                        outcome = "INSUFFICIENT DATA"
                        if len(days) >= config["minimum_test_sessions"] and len(chosen) >= config["minimum_test_trades"]:
                            outcome = "PASS" if metrics["bootstrap_low"] is not None and metrics["bootstrap_low"] > 0 else "FAIL"
                    rows.append(dict(instrument=instrument, minutes=minutes, strategy=method, phase=phase,
                                     factor=factor, cost_bps=cost, fit_through=fit_through,
                                     first_session=days[0] if days else None, last_session=days[-1] if days else None,
                                     index_screen=outcome, **metrics))
                    return chosen

                for phase, days in periods.items():
                    for cost in costs:
                        chosen = record(phase, days, variants[1.], 1., cost)
                        if cost == reference:
                            ledgers.append(chosen.assign(instrument=instrument, minutes=minutes, phase=phase))
                for factor in GRID[method]:
                    if factor != 1.:
                        record("validation_stability", periods["validation"], variants[factor], factor, reference)
                for quarter in quarters:
                    first = max(validation, quarter.start_time.strftime("%Y-%m-%d"))
                    last = min(walk_end, (quarter + 1).start_time.strftime("%Y-%m-%d"))
                    history = dates_between(sessions, start, first)
                    forward = dates_between(sessions, first, last)
                    if not history or not forward:
                        continue
                    def score(factor):
                        t = variants[factor]
                        return with_cost(t[t.session.isin(history)], reference).net_points.sum()
                    best = max(GRID[method], key=lambda factor: (score(factor), -abs(factor - 1)))
                    record(f"walk_{quarter}", forward, variants[best], best, reference, history[-1])
    result = pd.DataFrame(rows)
    result.to_csv(output / "index_metrics.csv", index=False)
    populated = [ledger for ledger in ledgers if not ledger.empty]
    ledger = pd.concat(populated, ignore_index=True) if populated else ledgers[0]
    ledger.to_csv(output / "index_trades.csv", index=False)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    result[(result.phase == "test") & (result.cost_bps == reference)].sort_values(
        ["instrument", "net_points"], ascending=[True, False]).to_csv(output / "index_ranking.csv", index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--out", default="reports")
    args = parser.parse_args()
    evaluate(json.loads(Path(args.config).read_text()), args.out)


if __name__ == "__main__":
    main()
