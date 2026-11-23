"""Historical bid/ask replay for long CE/PE only. No broker connection."""
import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from strategies import timestamps


@dataclass(frozen=True)
class Charges:
    exchange: float
    stt: float
    brokerage: float = 20.
    sebi: float = .000001
    stamp: float = .00003
    gst: float = .18
    ipft: float = 0.

    def round_trip(self, buy, sell, sell_orders=1):
        turnover = buy + sell
        broker = self.brokerage * (1 + sell_orders)
        exchange_sebi = turnover * (self.exchange + self.sebi + self.ipft)
        stt = np.floor(sell * self.stt + .5)
        return broker + exchange_sebi + (broker + exchange_sebi) * self.gst + buy * self.stamp + stt


def load_market(contracts, quotes):
    master = contracts.copy()
    ticks = quotes.copy()
    for field in ["listed_at", "expires_at"]:
        master[field] = timestamps(master[field])
    ticks["date"] = timestamps(ticks["date"])
    master[["strike", "lot_size", "tick_size"]] = master[["strike", "lot_size", "tick_size"]].apply(pd.to_numeric)
    fields = ["bid", "ask", "bid_size", "ask_size"]
    ticks[fields] = ticks[fields].apply(pd.to_numeric)
    if (master.contract.isna().any() or master.contract.duplicated().any()
            or not master.option_type.isin(["CE", "PE"]).all()
            or not np.isfinite(master[["strike", "lot_size", "tick_size"]]).all().all()
            or (master[["strike", "lot_size", "tick_size"]] <= 0).any().any()
            or master.lot_size.mod(1).ne(0).any()
            or master.expires_at.le(master.listed_at).any()):
        raise ValueError("Invalid point-in-time contract master")
    if (ticks.duplicated(["contract", "date"]).any() or not ticks.contract.isin(master.contract).all()
            or not np.isfinite(ticks[fields]).all().all() or (ticks[fields] < 0).any().any()
            or ticks.ask.lt(ticks.bid).any() or ticks[["bid_size", "ask_size"]].mod(1).ne(0).any().any()):
        raise ValueError("Invalid or ambiguous quote snapshots")
    checks = ticks.merge(master[["contract", "listed_at", "expires_at"]], on="contract")
    if (~checks.date.between(checks.listed_at, checks.expires_at, inclusive="left")).any():
        raise ValueError("Quote outside contract lifetime")
    return master, ticks.sort_values("date")


def option_schedule(trades):
    """Translate underlying trigger times into fixed option entry/exit decisions."""
    return trades.rename(columns={"entry": "underlying_open", "exit_time": "liquidation_time"})


def replay(schedule, contracts, quotes, rates, seconds, latency_ms=250, lots=1,
           max_spread=.05, slippage_ticks=1, max_exit_seconds=60):
    if (seconds not in (5, 15) or not np.isfinite([latency_ms, lots, max_spread, slippage_ticks, max_exit_seconds]).all()
            or not 0 < latency_ms < seconds * 1000 or lots < 1 or int(lots) != lots
            or max_spread <= 0 or slippage_ticks < 0 or max_exit_seconds < seconds):
        raise ValueError("Invalid execution parameters")
    master, ticks = load_market(contracts, quotes)
    for column in ["signal_time", "liquidation_time"]:
        schedule = schedule.assign(**{column: timestamps(schedule[column])})
    if (~schedule.side.isin(["LONG", "SHORT"]) | (schedule.liquidation_time < schedule.signal_time)).any():
        raise ValueError("Invalid execution schedule")
    books = {key: data for key, data in ticks.groupby("contract")}
    lag = pd.Timedelta(milliseconds=latency_ms)
    interval = pd.Timedelta(seconds=seconds)
    rows, pending = [], {}
    for order in schedule.sort_values("signal_time").itertuples(index=False):
        start, finish = order.signal_time, order.liquidation_time
        session_end = start.normalize() + pd.Timedelta(hours=15, minutes=30)
        key = (order.instrument, getattr(order, "strategy", ""), getattr(order, "minutes", 0))
        row = dict(order._asdict(), execution_seconds=seconds, status="NO_CONTRACT")
        if start < pending.get(key, start):
            rows.append(dict(row, status="POSITION_OPEN"))
            continue
        if finish >= session_end or finish <= start:
            rows.append(dict(row, status="NO_EXECUTION_WINDOW"))
            continue
        kind = "CE" if order.side == "LONG" else "PE"
        eligible = master[(master.instrument == order.instrument) & (master.option_type == kind)
                          & (master.listed_at <= start) & (master.expires_at >= session_end)]
        if eligible.empty:
            rows.append(row)
            continue
        # The signal's completed close is the only permitted underlying reference.
        eligible = eligible.assign(distance=(eligible.strike - order.signal_close).abs())
        contract = eligible.sort_values(["expires_at", "distance", "strike", "contract"]).iloc[0]
        row.update(contract=contract.contract, strike=contract.strike, expiry=contract.expires_at,
                   option_type=kind, lot_size=int(contract.lot_size))
        start_grid = (start + lag).ceil(f"{seconds}s")
        exit_grid = (finish + lag).ceil(f"{seconds}s")
        book = books.get(contract.contract, ticks.iloc[:0])
        entry_limit = min(start_grid + interval, contract.expires_at, session_end)
        entry_quotes = book[(book.date >= start_grid) & (book.date < entry_limit)]
        entry_quotes = entry_quotes[(entry_quotes.bid > 0)
                                    & ((entry_quotes.ask - entry_quotes.bid) <= max_spread * entry_quotes.ask)
                                    & (entry_quotes.ask_size >= contract.lot_size)]
        if entry_quotes.empty:
            rows.append(dict(row, status="NO_ENTRY_QUOTE"))
            continue
        entry = entry_quotes.iloc[0]
        quantity = int(min(lots, entry.ask_size // contract.lot_size) * contract.lot_size)
        tick_slip = slippage_ticks * contract.tick_size
        buy_px = entry.ask + tick_slip
        deadline = min(exit_grid + pd.Timedelta(seconds=max_exit_seconds), contract.expires_at, session_end)
        liquid = book[(book.date >= max(exit_grid, entry.date + lag)) & (book.date < deadline)
                      & (book.bid > tick_slip) & (book.bid_size >= contract.lot_size)]
        remaining, sell, sells, bid_value, ask_value, exit_time = quantity, 0., 0, 0., 0., None
        # At most one liquidity snapshot per grid interval.
        for quote in liquid.groupby(liquid.date.dt.floor(f"{seconds}s")).head(1).itertuples(index=False):
            units = int(min(remaining, (quote.bid_size // contract.lot_size) * contract.lot_size))
            remaining -= units
            sell += units * (quote.bid - tick_slip)
            bid_value += units * quote.bid
            ask_value += units * quote.ask
            sells += 1
            exit_time = quote.date
            if not remaining:
                break
        pending[key] = session_end if remaining else exit_time
        row.update(entry_time=entry.date, exit_time=exit_time, quantity=quantity, remaining=remaining,
                   requested_quantity=int(lots * contract.lot_size), entry_bid=entry.bid,
                   entry_ask=entry.ask, buy_price=buy_px, sell_orders=sells,
                   partial_exit_proceeds=sell)
        if remaining:
            rows.append(dict(row, status="UNRESOLVED_EXIT"))
            continue
        buy = buy_px * quantity
        fees = rates.round_trip(buy, sell, sells)
        rows.append(dict(row, status="CLOSED", exit_bid_vwap=bid_value / quantity,
                         exit_ask_vwap=ask_value / quantity, sell_price=sell / quantity,
                         gross_inr=sell - buy, fees_inr=fees,
                         spread_inr=((entry.ask - entry.bid) * quantity + ask_value - bid_value) / 2,
                         slippage_inr=2 * tick_slip * quantity, net_inr=sell - buy - fees,
                         turnover_inr=buy + sell))
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ["schedule", "contracts", "quotes", "out"]:
        parser.add_argument("--" + field, required=True)
    parser.add_argument("--exchange-rate", type=float, required=True)
    parser.add_argument("--stt-rate", type=float, required=True)
    parser.add_argument("--ipft-rate", type=float, default=0.)
    parser.add_argument("--seconds", type=int, choices=[5, 15], required=True)
    parser.add_argument("--lots", type=int, default=1)
    parser.add_argument("--latency-ms", type=int, default=250)
    parser.add_argument("--slippage-ticks", type=int, default=1)
    args = parser.parse_args()
    if not np.isfinite([args.exchange_rate, args.stt_rate, args.ipft_rate]).all() or min(args.exchange_rate, args.stt_rate, args.ipft_rate) < 0:
        parser.error("Provide nonnegative finite period-specific fee rates")
    result = replay(option_schedule(pd.read_csv(args.schedule)), pd.read_csv(args.contracts),
                    pd.read_csv(args.quotes), Charges(args.exchange_rate, args.stt_rate, ipft=args.ipft_rate),
                    args.seconds, args.latency_ms, args.lots, slippage_ticks=args.slippage_ticks)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
