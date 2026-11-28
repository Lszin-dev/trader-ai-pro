import unittest

import pandas as pd

from strategy import analyze_market


def make_frame(
    ema9=1.2,
    ema21=1.1,
    macd=0.02,
    macd_signal=0.01,
    close=1.21,
    rsi=55.0,
    atr=0.001,
):
    return pd.DataFrame(
        {
            "EMA9": [ema9] * 30,
            "EMA21": [ema21] * 30,
            "RSI": [rsi] * 30,
            "MACD": [macd] * 30,
            "MACD_SIGNAL": [macd_signal] * 30,
            "ATR": [atr] * 30,
            "close": [close] * 30,
        }
    )


class AnalyzeMarketTests(unittest.TestCase):
    def test_returns_call_when_both_timeframes_confirm_uptrend(self):
        result = analyze_market(make_frame(), make_frame())
        self.assertEqual(result["signal"], "CALL")

    def test_returns_put_when_both_timeframes_confirm_downtrend(self):
        bearish = make_frame(
            ema9=1.1,
            ema21=1.2,
            macd=-0.02,
            macd_signal=-0.01,
            close=1.09,
            rsi=45.0,
        )
        result = analyze_market(bearish, bearish)
        self.assertEqual(result["signal"], "PUT")

    def test_waits_when_timeframes_disagree(self):
        bullish = make_frame()
        bearish = make_frame(
            ema9=1.1,
            ema21=1.2,
            macd=-0.02,
            macd_signal=-0.01,
            close=1.09,
            rsi=45.0,
        )
        result = analyze_market(bullish, bearish)
        self.assertEqual(result["signal"], "AGUARDAR")

    def test_waits_when_data_is_insufficient(self):
        short = make_frame().head(10)
        result = analyze_market(short, make_frame())
        self.assertEqual(result["signal"], "AGUARDAR")

    def test_waits_when_indicators_are_missing(self):
        incomplete = make_frame()
        incomplete.loc[incomplete.index[-1], "RSI"] = float("nan")
        result = analyze_market(incomplete, make_frame())
        self.assertEqual(result["signal"], "AGUARDAR")


if __name__ == "__main__":
    unittest.main()
