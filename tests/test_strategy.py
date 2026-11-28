import unittest

import pandas as pd

from strategy import MIN_TECHNICAL_SCORE, analyze_market


def make_frame(direction="up", rsi=None, atr=0.001):
    size = 30
    if direction == "up":
        closes = [1.2000 + i * 0.0001 for i in range(size)]
        opens = [value - 0.00005 for value in closes]
        ema9, ema21 = 1.2005, 1.1995
        macd, macd_signal = 0.02, 0.01
        rsi = 55.0 if rsi is None else rsi
    else:
        closes = [1.2000 - i * 0.0001 for i in range(size)]
        opens = [value + 0.00005 for value in closes]
        ema9, ema21 = 1.1980, 1.2000
        macd, macd_signal = -0.02, -0.01
        rsi = 45.0 if rsi is None else rsi

    return pd.DataFrame(
        {
            "open": opens,
            "close": closes,
            "EMA9": [ema9] * size,
            "EMA21": [ema21] * size,
            "RSI": [rsi] * size,
            "MACD": [macd] * size,
            "MACD_SIGNAL": [macd_signal] * size,
            "ATR": [atr] * size,
        }
    )


class AnalyzeMarketTests(unittest.TestCase):
    def test_returns_call_when_both_timeframes_confirm_uptrend(self):
        result = analyze_market(make_frame("up"), make_frame("up"))
        self.assertEqual(result["signal"], "CALL")
        self.assertGreaterEqual(result["score"], MIN_TECHNICAL_SCORE)
        self.assertIn("metrics", result)
        self.assertIn("checks", result)

    def test_returns_put_when_both_timeframes_confirm_downtrend(self):
        result = analyze_market(make_frame("down"), make_frame("down"))
        self.assertEqual(result["signal"], "PUT")
        self.assertGreaterEqual(result["score"], MIN_TECHNICAL_SCORE)

    def test_waits_when_timeframes_disagree(self):
        result = analyze_market(make_frame("up"), make_frame("down"))
        self.assertEqual(result["signal"], "AGUARDAR")

    def test_waits_when_data_is_insufficient(self):
        short = make_frame("up").head(10)
        result = analyze_market(short, make_frame("up"))
        self.assertEqual(result["signal"], "AGUARDAR")

    def test_waits_when_indicators_are_missing(self):
        incomplete = make_frame("up")
        incomplete.loc[incomplete.index[-1], "RSI"] = float("nan")
        result = analyze_market(incomplete, make_frame("up"))
        self.assertEqual(result["signal"], "AGUARDAR")

    def test_waits_when_short_term_momentum_reverses(self):
        frame = make_frame("up")
        frame.loc[frame.index[-4:], "close"] = [1.2040, 1.2030, 1.2020, 1.2010]
        result = analyze_market(frame, make_frame("up"))
        self.assertEqual(result["signal"], "AGUARDAR")

    def test_waits_when_volatility_is_too_low(self):
        result = analyze_market(make_frame("up", atr=0.000001), make_frame("up"))
        self.assertEqual(result["signal"], "AGUARDAR")
        self.assertIn("Volatilidade", result["reason"])


if __name__ == "__main__":
    unittest.main()
