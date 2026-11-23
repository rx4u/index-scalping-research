"""Completed-bar research signals on regular Indian index sessions."""
import numpy as np
import pandas as pd

TZ = "Asia/Kolkata"
OHLC = ["open", "high", "low", "close"]
METHODS = ("noise_band", "momentum", "exhaustion", "naive", "no_trade")


def timestamps(values, timezone=TZ):
    parsed = pd.to_datetime(values, format="mixed")
    if parsed.isna().any():
        raise ValueError("Missing timestamp")
    if isinstance(parsed.dtype, pd.DatetimeTZDtype):
        return parsed.dt.tz_convert(TZ)
    if pd.api.types.is_datetime64_dtype(parsed):
        return parsed.dt.tz_localize(timezone, ambiguous="raise", nonexistent="raise").dt.tz_convert(TZ)
    raise ValueError("Use a consistent timestamp offset or uniform local timestamps")


def prepare(frame, minutes=1, timezone=TZ, calendar=None):
    """Return complete regular sessions and attach exclusion metadata."""
    if minutes not in (1, 3):
        raise ValueError("Signal intervals must be 1 or 3 minutes")
    data = frame.copy()
    data.columns = data.columns.str.strip().str.lower()
    data = data.rename(columns={"timestamp": "date"}) if "date" not in data else data
    data["date"] = timestamps(data["date"], timezone)
    data = data.sort_values("date")
    if data.date.duplicated().any() or not data.date.eq(data.date.dt.floor("min")).all():
        raise ValueError("Expected unique, minute-aligned bar opening timestamps")
    data[OHLC] = data[OHLC].apply(pd.to_numeric)
    if (not np.isfinite(data[OHLC]).all().all() or (data[OHLC] <= 0).any().any()
            or (data.high < data[OHLC].max(axis=1)).any()
            or (data.low > data[OHLC].min(axis=1)).any()):
        raise ValueError("Invalid OHLC")
    data["session"] = data.date.dt.strftime("%Y-%m-%d")
    data["minute"] = data.date.dt.hour * 60 + data.date.dt.minute - 555
    data = data[data.minute.between(0, 374)]
    observed = data.groupby("session").size()
    expected = sorted(set(observed.index if calendar is None else calendar))
    complete = observed[observed.eq(375)].index.intersection(expected)
    data = data[data.session.isin(complete)].copy()
    if minutes > 1:
        data["minute"] = data.minute // minutes * minutes
        data = data.groupby(["session", "minute"], as_index=False).agg(
            date=("date", "first"), open=("open", "first"), high=("high", "max"),
            low=("low", "min"), close=("close", "last"))
    data["available"] = data.date + pd.Timedelta(minutes=minutes)
    previous = data.groupby("session").close.shift()
    true_range = pd.concat([data.high - data.low, (data.high - previous).abs(),
                            (data.low - previous).abs()], axis=1).max(axis=1)
    data["atr"] = true_range.groupby(data.session).transform(lambda x: x.rolling(20).mean())
    data.attrs["coverage"] = {"expected": len(expected), "complete": len(complete),
                              "excluded": sorted(set(expected) - set(complete)),
                              "outside_calendar": sorted(set(observed.index) - set(expected))}
    return data.reset_index(drop=True)


def signals(data, method, width=1.0):
    """Causal local adaptations. Width controls the noise and reversal thresholds."""
    if not np.isfinite(width) or width <= 0:
        raise ValueError("Width must be positive")
    d = data.copy()
    group = d.groupby("session")
    if method == "noise_band":
        opening = group.open.transform("first")
        previous = group.close.last().shift().reindex(d.session).to_numpy()
        movement = d.assign(move=(d.close / opening - 1).abs())
        history = movement.pivot(index="session", columns="minute", values="move")
        bands = history.shift().rolling(14, min_periods=14).mean().stack().rename("band")
        d = d.join(bands, on=["session", "minute"])
        upper = np.maximum(opening, previous) * (1 + width * d.band)
        lower = np.minimum(opening, previous) * (1 - width * d.band)
        direction = np.select([d.close > upper, d.close < lower], [1, -1], 0)
    elif method == "momentum":
        fast = group.close.pct_change(3)
        slow = group.close.pct_change(12)
        high = group.high.transform(lambda x: x.shift().rolling(8).max())
        low = group.low.transform(lambda x: x.shift().rolling(8).min())
        direction = np.select([(fast > 0) & (slow > 0) & (d.close > high),
                               (fast < 0) & (slow < 0) & (d.close < low)], [1, -1], 0)
    elif method == "exhaustion":
        prior = group.close.shift()
        trend = group.close.shift() / group.close.shift(11) - 1
        low, high = group.low.shift(), group.high.shift()
        span = group.high.transform(lambda x: x.shift().rolling(20).max()) - group.low.transform(
            lambda x: x.shift().rolling(20).min())
        valid = (d.high - d.low > .1 * span) & prior.notna()
        direction = np.select([valid & (trend < -.001 * width) & (d.low < low) & (d.close > low),
                               valid & (trend > .001 * width) & (d.high > high) & (d.close < high)],
                              [1, -1], 0)
    elif method == "naive":
        bars = (d.available - d.date).dt.total_seconds() / 60
        direction = np.where(d.minute + bars == 60, 1, 0)
    elif method == "no_trade":
        direction = 0
    else:
        raise ValueError(f"Unknown strategy {method}")
    d["signal"] = direction
    elapsed = d.available.dt.hour * 60 + d.available.dt.minute - 555
    d.loc[~elapsed.between(30, 330), "signal"] = 0
    return d


def generate(df, method):
    return signals(prepare(df), method)
