import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from backtest import exit_bar, simulate, summary
from kite_download import download, local_login
from options import Charges, load_market, replay
from research import dates_between, with_cost
from strategies import METHODS, TZ, prepare, signals
from tick_bars import bars


def start(stamp):
    return pd.Timestamp(stamp, tz=TZ)


def sample(days=16):
    frames = []
    for day in pd.bdate_range("2024-01-01", periods=days):
        dates = pd.date_range(f"{day.date()} 09:15", periods=375, freq="min", tz=TZ)
        close = 100 + np.arange(375) / 100
        frames.append(pd.DataFrame(dict(date=dates, open=close, high=close + .1, low=close - .1, close=close)))
    return pd.concat(frames, ignore_index=True)


class IndexTests(unittest.TestCase):
    def test_utc_alignment_and_three_minute_open_close(self):
        frame = sample(1)
        frame["date"] = frame.date.dt.tz_convert("UTC")
        out = prepare(frame, 3)
        self.assertEqual(len(out), 125)
        self.assertEqual(out.iloc[0].date, start("2024-01-01 09:15"))
        self.assertEqual(out.iloc[0].available, start("2024-01-01 09:18"))
        self.assertEqual(out.iloc[0].close, frame.iloc[2].close)

    def test_gap_and_missing_calendar_day_are_counted(self):
        frame = sample(2).drop(index=10)
        out = prepare(frame, 1, calendar=["2024-01-01", "2024-01-02", "2024-01-03"])
        self.assertEqual(out.attrs["coverage"]["excluded"], ["2024-01-01", "2024-01-03"])
        self.assertEqual(out.session.unique().tolist(), ["2024-01-02"])

    def test_reject_duplicate_nan_and_impossible_ohlc(self):
        frame = sample(1)
        for bad in [pd.concat([frame, frame.iloc[:1]]), frame.assign(close=np.nan), frame.assign(high=1)]:
            with self.assertRaises(ValueError):
                prepare(bad)

    def test_signals_do_not_change_on_future_price_mutation(self):
        past = sample()
        altered = past.copy()
        altered.loc[altered.index >= len(past) - 200, ["open", "high", "low", "close"]] *= 10
        for method in METHODS:
            first, second = signals(prepare(past), method), signals(prepare(altered), method)
            pd.testing.assert_series_equal(first.signal.iloc[:-200], second.signal.iloc[:-200])

    def test_noise_needs_fourteen_previous_sessions(self):
        out = signals(prepare(sample(15)), "noise_band")
        self.assertTrue(out[out.session < out.session.iloc[-1]].band.isna().all())
        self.assertTrue(out[out.session == out.session.iloc[-1]].band.notna().all())

    def test_gap_precedes_intrabar_range(self):
        time = start("2024-01-01 10:00")
        bar = SimpleNamespace(open=95, high=111, low=92, date=time, available=time + pd.Timedelta(minutes=1))
        self.assertEqual(exit_bar(bar, 1, 99, 110), (95, time, "stop_gap"))
        self.assertEqual(exit_bar(bar, -1, 101, 96), (96, time, "target_gap"))
        bar.open = 100
        self.assertEqual(exit_bar(bar, 1, 99, 110), (99, bar.available, "stop"))

    def test_no_fill_across_gap_and_entry_bar_stop_is_causal(self):
        data = prepare(sample(1))
        data["signal"] = 0
        data.loc[39, "signal"] = 1
        data.loc[40, "low"] = 88
        self.assertTrue(simulate(data.drop(index=40), "momentum").empty)
        trade = simulate(data, "momentum").iloc[0]
        self.assertEqual(trade.entry_time, data.loc[39, "available"])
        self.assertEqual(trade.exit_time, data.loc[40, "available"])
        self.assertEqual(trade.signal_close, data.loc[39, "close"])

    def test_cost_metrics_and_partitions(self):
        data = signals(prepare(sample(2)), "naive")
        trades = simulate(data, "naive")
        cost = with_cost(trades, 2)
        np.testing.assert_allclose(cost.gross_points - cost.net_points, cost.turnover / 10000)
        self.assertEqual(len(trades), 2)
        self.assertEqual(summary(cost, list(data.session.unique()))["trades_per_day"], 1)
        self.assertEqual(dates_between(["2024-01-01", "2024-01-02"], "2024-01-01", "2024-01-02"), ["2024-01-01"])


class OptionTests(unittest.TestCase):
    def setUp(self):
        self.market = pd.DataFrame([dict(contract="c", instrument="NIFTY 50", strike=100,
                                        option_type="CE", lot_size=10, tick_size=.05,
                                        listed_at="2024-01-01 09:15", expires_at="2024-01-01 15:30")])
        self.book = pd.DataFrame(
            [dict(contract="c", date=f"2024-01-01 {time}", bid=10, ask=10.2,
                  ask_size=20, bid_size=10) for time in
             ["10:00:00", "10:00:05", "10:00:15", "10:01:05", "10:01:06", "10:01:15", "10:01:30"]])
        self.order = pd.DataFrame([dict(instrument="NIFTY 50", side="LONG", signal_close=100,
                                        signal_time="2024-01-01 10:00", liquidation_time="2024-01-01 10:01")])
        self.rates = Charges(.0003553, .0015)

    def test_latency_spread_charges_and_partial_depth(self):
        trade = replay(self.order, self.market, self.book, self.rates, 5, lots=3).iloc[0]
        self.assertEqual(trade.entry_time, start("2024-01-01 10:00:05"))
        self.assertEqual(trade.exit_time, start("2024-01-01 10:01:15"))
        self.assertEqual(trade.quantity, 20)
        self.assertEqual(trade.requested_quantity, 30)
        self.assertEqual(trade.sell_orders, 2)
        self.assertAlmostEqual(trade.buy_price, 10.25)
        self.assertAlmostEqual(trade.sell_price, 9.95)
        self.assertAlmostEqual(trade.net_inr, -6 - self.rates.round_trip(205, 199, 2))

    def test_fifteen_seconds_and_missing_exit(self):
        full = replay(self.order, self.market, self.book, self.rates, 15, lots=2)
        self.assertEqual(full.iloc[0].entry_time, start("2024-01-01 10:00:15"))
        result = replay(self.order, self.market, self.book.iloc[:3], self.rates, 15)
        self.assertEqual(result.iloc[0].status, "UNRESOLVED_EXIT")
        self.assertNotIn("net_inr", result.columns)

    def test_no_future_quote_contract_or_spread(self):
        market = self.market.assign(listed_at="2024-01-01 10:00:01")
        future = self.book.iloc[1:]
        self.assertEqual(replay(self.order, market, future, self.rates, 5).iloc[0].status, "NO_CONTRACT")
        wide = self.book.assign(ask=20)
        self.assertEqual(replay(self.order, self.market, wide, self.rates, 5).iloc[0].status, "NO_ENTRY_QUOTE")
        with self.assertRaises(ValueError):
            load_market(self.market, self.book.assign(bid=30))

    def test_tick_boundary_and_sequence(self):
        tape = pd.DataFrame(dict(instrument=["NIFTY"] * 3, sequence=[2, 1, 3], price=[2, 1, 3],
                                 date=["2024-01-01 09:15:01", "2024-01-01 09:15:01", "2024-01-01 09:15:05"]))
        result = bars(tape, 5)
        self.assertEqual(result.open.to_list(), [1, 3])
        self.assertEqual(result.close.to_list(), [2, 3])
        self.assertEqual(result.iloc[0].available, result.iloc[1].date)


class KiteTests(unittest.TestCase):
    def test_read_only_kite_download_and_local_exchange(self):
        client = Mock()
        client.instruments.return_value = [{"tradingsymbol": "SENSEX", "segment": "INDICES", "instrument_token": 265}]
        client.historical_data.return_value = sample(1).to_dict("records")
        result, manifest = download(client, "SENSEX", date(2024, 1, 1), date(2024, 1, 1))
        self.assertEqual(len(result), 375)
        self.assertEqual(manifest["coverage"]["complete"], 1)
        self.assertEqual(client.historical_data.call_args.args[1].hour, 9)
        client.generate_session.return_value = {"access_token": "local-example"}
        with patch("kite_download.getpass", side_effect=["example-secret", "http://127.0.0.1:8000/callback?request_token=local-request"]), patch("builtins.print"), patch.dict("os.environ", {}, clear=True):
            self.assertEqual(local_login(client), "local-example")
        client.generate_session.assert_called_once_with("local-request", api_secret="example-secret")


if __name__ == "__main__":
    unittest.main()
