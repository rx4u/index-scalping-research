"""Index-point screening with conservative OHLC execution."""
import argparse

import numpy as np
import pandas as pd

from strategies import METHODS, prepare, signals

COLUMNS = ["strategy", "session", "signal_time", "entry_time", "exit_time", "side",
           "signal_close", "entry", "stop", "target", "exit", "reason", "gross_points", "net_points",
           "R_net", "turnover", "holding_seconds"]


def exit_bar(bar, side, stop, target):
    if side * (bar.open - stop) <= 0:
        return bar.open, bar.date, "stop_gap"
    if side * (bar.open - target) >= 0:
        return target, bar.date, "target_gap"
    if (bar.low <= stop if side == 1 else bar.high >= stop):
        return stop, bar.available, "stop"
    if (bar.high >= target if side == 1 else bar.low <= target):
        return target, bar.available, "target"
    if bar.available.hour * 60 + bar.available.minute >= 915:
        return bar.close, bar.available, "time_exit"
    return None


def simulate(data, strategy, stop_atr=1.0, target_r=1.5, cost_points=0.0, max_trades=2):
    if not np.isfinite([stop_atr, target_r, cost_points]).all() or min(stop_atr, target_r) <= 0 or cost_points < 0 or max_trades < 1:
        raise ValueError("Invalid execution assumptions")
    trades = []
    for session, rows in data.groupby("session", sort=False):
        bars = list(rows.itertuples(index=False))
        count, i = 0, 0
        while i < len(bars) - 1 and count < max_trades:
            signal, entry = bars[i:i + 2]
            i += 1
            if not signal.signal or not np.isfinite(signal.atr) or signal.atr <= 0 or entry.date != signal.available:
                continue
            side, risk = int(signal.signal), stop_atr * signal.atr
            stop, target = entry.open - side * risk, entry.open + side * risk * target_r
            for j in range(i, len(bars)):
                result = exit_bar(bars[j], side, stop, target)
                if result is not None:
                    break
            else:
                raise ValueError("Session has no executable exit")
            fill, time, reason = result
            gross = side * (fill - entry.open)
            trades.append((strategy, session, signal.available, entry.date, time,
                           "LONG" if side == 1 else "SHORT", signal.close, entry.open, stop, target, fill, reason,
                           gross, gross - cost_points, (gross - cost_points) / risk,
                           entry.open + fill, (time - entry.date).total_seconds()))
            count += 1
            i = j + 1
    return pd.DataFrame(trades, columns=COLUMNS)


def run(df, strategy, stop_atr=1., target_r=1.5, cost_points=0., max_trades=2):
    return simulate(signals(prepare(df), strategy), strategy, stop_atr, target_r, cost_points, max_trades)


def summary(trades, sessions=None, seed=20261123, alpha=.05):
    pnl = trades.net_points.astype(float)
    count = len(pnl)
    pos, neg = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    equity = np.r_[0., pnl.cumsum()]
    result = {"sessions": None if sessions is None else len(sessions), "trades": count,
              "trades_per_day": count / len(sessions) if sessions is not None and len(sessions) else None,
              "net_points": float(pnl.sum()), "win_rate_pct": 100 * (pnl > 0).mean() if count else None,
              "net_expectancy": pnl.mean() if count else None,
              "gross_expectancy": trades.gross_points.mean() if count else None,
              "profit_factor": pos / neg if neg else None,
              "max_drawdown": float((np.maximum.accumulate(equity) - equity).max()),
              "median_holding_seconds": trades.holding_seconds.median() if count else None,
              "trade_p05": pnl.quantile(.05) if count else None,
              "worst_trade": pnl.min() if count else None, "turnover": float(trades.turnover.sum()),
              "bootstrap_low": None, "bootstrap_high": None}
    if sessions is not None and len(sessions) >= 20 and count >= 20:
        daily = trades.groupby("session").net_points.agg(["sum", "size"]).reindex(sessions, fill_value=0).to_numpy()
        # Sample adjacent blocks to retain short-horizon session dependence.
        rng = np.random.default_rng(seed)
        length = len(daily)
        starts = rng.integers(0, length, (4000, (length + 4) // 5, 1))
        sample = daily[((starts + np.arange(5)) % length).reshape(4000, -1)[:, :length]].sum(axis=1)
        valid = sample[:, 1] > 0
        result["bootstrap_low"], result["bootstrap_high"] = np.quantile(
            sample[valid, 0] / sample[valid, 1], [alpha / 2, 1 - alpha / 2])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--cost-points", type=float, default=1.)
    parser.add_argument("--out", default="results")
    args = parser.parse_args()
    data = prepare(pd.read_csv(args.csv))
    rows = []
    for method in METHODS:
        trades = simulate(signals(data, method), method, cost_points=args.cost_points)
        trades.to_csv(f"{args.out}_{method}_trades.csv", index=False)
        rows.append(dict(strategy=method, **summary(trades, data.session.unique())))
    pd.DataFrame(rows).to_csv(f"{args.out}_summary.csv", index=False)


if __name__ == "__main__":
    main()
