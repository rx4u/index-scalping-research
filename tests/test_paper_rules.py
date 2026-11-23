import unittest
from unittest.mock import patch

import pandas as pd

from paper_rules import replay
from strategies import prepare


def bars():
    frames = []
    for session in ("2026-01-05", "2026-01-06"):
        opening = pd.Timestamp(f"{session} 09:15", tz="Asia/Kolkata")
        frames.append(pd.DataFrame({"date": pd.date_range(opening, periods=375, freq="min"),
                                    "open": 100., "high": 110., "low": 90., "close": 100.}))
    return prepare(pd.concat(frames, ignore_index=True))


class PaperRuleTests(unittest.TestCase):
    def test_gao_uses_prior_close_and_only_trades_final_half_hour(self):
        data = bars()
        data.loc[375 + 29, "close"] = 99.
        data.loc[375 + 30, "close"] = 109.
        data.loc[749, "close"] = 95.
        trade = replay(data, "gao_sign").iloc[0]
        self.assertEqual(trade.side, -1)
        self.assertEqual(trade.holding_seconds, 1800)
        self.assertEqual(trade.entry_time.strftime("%H:%M"), "15:00")
        self.assertEqual(trade.gross_points, 5)

    def test_noise_reverses_only_at_clock_boundary_and_flattens_at_close(self):
        data = bars()
        data.loc[[14, 44, 74], "close"] = [106., 100., 94.]
        data.loc[50, "close"] = 92.
        data.loc[75, "open"] = 97.
        with patch("paper_rules.noise_bands", return_value=data.assign(upper=105., lower=95.)):
            result = replay(data, "noise_opposite_band")
        self.assertEqual(result.side.tolist(), [1, -1])
        self.assertEqual(result.entry_time.dt.strftime("%H:%M").tolist(), ["09:30", "10:30"])
        self.assertEqual(result.exit_time.dt.strftime("%H:%M").tolist(), ["10:30", "15:30"])
        self.assertEqual(result.gross_points.tolist(), [-3., -3.])
