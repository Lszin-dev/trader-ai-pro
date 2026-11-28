import unittest
from unittest.mock import patch
import pandas as pd
from indicators import calculate_indicators
from reliability import advance_confirmation, validate_ohlc, closed_five_minute, quote_is_current
from backtest import replay, summarize

def frame(n=280):
    index=pd.date_range("2026-11-30T10:00:00Z",periods=n,freq="min")
    p=pd.Series([1+i*.0001 for i in range(n)],index=index)
    return pd.DataFrame({"open":p,"high":p+.0002,"low":p-.0001,"close":p+.0001})

class ReliabilityTests(unittest.TestCase):
    def test_duplicate_candle_never_confirms(self):
        t=pd.Timestamp("2026-11-30T10:00Z")
        state,_=advance_confirmation(None,"CALL",t)
        duplicate,advanced=advance_confirmation(state,"CALL",t)
        self.assertFalse(advanced)
        self.assertEqual(duplicate["count"],1)
        state,advanced=advance_confirmation(state,"CALL",t+pd.Timedelta(minutes=2))
        self.assertTrue(advanced)
        self.assertEqual(state["count"],2)
    def test_gap_resets(self):
        t=pd.Timestamp("2026-11-30T10:00Z")
        state,_=advance_confirmation(None,"CALL",t)
        state,_=advance_confirmation(state,"CALL",t+pd.Timedelta(minutes=10))
        self.assertEqual(state["count"],1)
    def test_bad_ohlc(self):
        f=frame()
        f.iloc[0,f.columns.get_loc("high")]=.5
        with self.assertRaises(ValueError): validate_ohlc(f)
    def test_missing_minute_does_not_form_5m(self):
        f=frame(10).drop(frame(10).index[2])
        self.assertEqual(len(closed_five_minute(f)),1)
    def test_quote_expires(self):
        q={"valid":True,"quote_timestamp":"2026-11-30T10:00:00Z"}
        self.assertTrue(quote_is_current(q, "2026-11-30T10:00:10Z"))
        self.assertFalse(quote_is_current(q, "2026-11-30T10:00:16Z"))
    def test_rsi_extremes(self):
        f=frame()
        self.assertEqual(calculate_indicators(f).RSI.iloc[-1],100)
        for c in f.columns: f[c]=1.0
        self.assertEqual(calculate_indicators(f).RSI.iloc[-1],50)
    @patch("backtest.analyze_market",return_value={"signal":"CALL","score":80})
    def test_replay_uses_future_only_for_outcomes(self, strategy):
        f=frame()
        trials=replay(f)
        self.assertEqual(len(trials),2)
        self.assertTrue((pd.to_datetime(trials.entry)>pd.to_datetime(trials.decision)).all())
        self.assertEqual(summarize(trials)["1"]["wins"],1)
        for call in strategy.call_args_list:
            a,b=call.args
            self.assertLessEqual(b.index[-1]+pd.Timedelta(minutes=5), a.index[-1]+pd.Timedelta(minutes=1))
    def test_empty_results_have_no_rate(self):
        self.assertIsNone(summarize(replay(frame(150)))["1"]["win_rate_excluding_ties"])
