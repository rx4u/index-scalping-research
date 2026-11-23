import unittest

import pandas as pd

from forward_check import milestone


class ForwardCheckTests(unittest.TestCase):
    def test_first_date_meeting_both_thresholds(self):
        sessions = [f"{i:03}" for i in range(105)]
        trades = pd.DataFrame({"session": sessions[3:]})
        self.assertIsNone(milestone(sessions[:102], trades))
        self.assertEqual(milestone(sessions, trades), sessions[102])

    def test_extra_trades_cannot_replace_session_history(self):
        sessions = [f"{i:03}" for i in range(100)]
        trades = pd.DataFrame({"session": [sessions[0]] * 100})
        self.assertIsNone(milestone(sessions[:99], trades))
        self.assertEqual(milestone(sessions, trades), sessions[99])
