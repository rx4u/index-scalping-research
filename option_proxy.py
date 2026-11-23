"""Compare historical premium opens with explicitly hypothetical friction."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from options import Charges
from strategies import timestamps

WEEKLY = {"NIFTY 50": ["2026-05-26", "2026-06-02"], "SENSEX": ["2026-05-14", "2026-05-21"]}
SPECS = {"NIFTY 50": ("NIFTY", 50, 65, .0003553), "SENSEX": ("SENSEX", 100, 20, .000325)}
REVISION = "0f4800e43e6f96cec0794369d78eb4d3c4211ef5"
SOURCE = f"https://huggingface.co/datasets/thetrademarkk/india-index-options-1m/tree/{REVISION}"
FRICTION = (0, 25, 100)


def study(index_trades, inputs):
    rows, provenance = [], {}
    tape = index_trades[index_trades.phase.eq("test")].copy()
    for field in ["signal_time", "exit_time"]:
        tape[field] = timestamps(tape[field])
    for instrument, expiries in WEEKLY.items():
        symbol, strike_step, lot_size, exchange = SPECS[instrument]
        charges = Charges(exchange=exchange, stt=.0015)
        for expiry in expiries:
            path = Path(inputs) / f"{symbol}_{expiry}.parquet"
            raw = pd.read_parquet(path)
            provenance[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            if not raw.expiry.eq(expiry).all() or not raw.symbol.eq(symbol).all():
                raise ValueError(f"Unexpected contract identity: {path.name}")
            raw["timestamp"] = timestamps(raw.timestamp)
            lookup = raw.set_index(["timestamp", "strike", "option_type"], verify_integrity=True).open
            start = (pd.Timestamp(expiry) - pd.Timedelta(days=6)).strftime("%Y-%m-%d")
            case = tape[tape.instrument.eq(instrument) & tape.session.between(start, expiry)]
            for trade in case.itertuples():
                strike = int(np.floor(trade.signal_close / strike_step + .5) * strike_step)
                option_type = "CE" if trade.side == "LONG" else "PE"
                # Require a fresh full minute after each decision. This is still a print proxy.
                enter = trade.signal_time.floor("min") + pd.Timedelta(minutes=1)
                leave = max(enter, trade.exit_time.floor("min")) + pd.Timedelta(minutes=1)
                entry_open = lookup.get((enter, strike, option_type), np.nan)
                exit_open = lookup.get((leave, strike, option_type), np.nan)
                row = dict(instrument=instrument, minutes=trade.minutes, strategy=trade.strategy,
                           session=trade.session, expiry=expiry, strike=strike, option_type=option_type,
                           lot_size=lot_size, entry_time=enter, exit_time=leave, entry_open=entry_open,
                           exit_open=exit_open, status="NO_ENTRY_PRINT", net_inr=None)
                for bps in FRICTION:
                    result = dict(row, friction_bps=bps)
                    if np.isfinite(entry_open) and entry_open > 0:
                        result["status"] = "NO_EXIT_PRINT"
                        if np.isfinite(exit_open) and exit_open > 0:
                            buy = lot_size * entry_open * (1 + bps / 10000)
                            sell = lot_size * exit_open * (1 - bps / 10000)
                            fees = charges.round_trip(buy, sell)
                            result.update(status="PRICE_PROXY", fees_inr=fees,
                                          gross_inr=lot_size * (exit_open - entry_open),
                                          net_inr=sell - buy - fees)
                    rows.append(result)
    return pd.DataFrame(rows), provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", default="reports")
    parser.add_argument("--inputs", required=True)
    args = parser.parse_args()
    out = Path(args.reports)
    results, hashes = study(pd.read_csv(out / "index_trades.csv"), args.inputs)
    results.to_csv(out / "option_proxy_trades.csv", index=False)
    results.groupby(["instrument", "minutes", "strategy", "friction_bps"], as_index=False).agg(
        attempts=("status", "size"), closed=("net_inr", "count"),
        net_inr=("net_inr", lambda x: x.sum(min_count=1))).to_csv(out / "option_proxy_metrics.csv", index=False)
    provenance = dict(source=SOURCE, sha256=hashes, expiries=WEEKLY, specs=SPECS,
                      friction_bps_per_side=FRICTION, sell_stt=.0015, status="INSUFFICIENT DATA")
    (out / "option_proxy_manifest.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
