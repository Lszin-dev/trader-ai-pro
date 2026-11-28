import unittest
from unittest.mock import Mock

import pandas as pd

from otcharts_feed import OTChartsFeed, OTChartsError


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {}
        self.last_url = None
        self.last_params = None

    def get(self, url, params=None, timeout=None):
        self.last_url = url
        self.last_params = params
        return FakeResponse(self.payload)


def make_candles(now, timeframe=60, count=40):
    end = int(pd.Timestamp(now).timestamp())
    start = end - count * timeframe
    return [
        {
            "time": start + i * timeframe,
            "open": 1.1 + i * 0.0001,
            "high": 1.101 + i * 0.0001,
            "low": 1.099 + i * 0.0001,
            "close": 1.1005 + i * 0.0001,
        }
        for i in range(count)
    ]


class OTChartsFeedTests(unittest.TestCase):
    def setUp(self):
        self.now = pd.Timestamp("2026-11-28T12:00:00Z")

    def test_lists_symbols_using_exact_venue(self):
        session = FakeSession({
            "symbols": [
                {"symbol": "EURUSD-OTC", "name": "EUR/USD OTC", "open": True}
            ]
        })
        feed = OTChartsFeed(api_key="test", session=session)
        symbols = feed.list_symbols("iq")
        self.assertEqual(symbols[0]["symbol"], "EURUSD-OTC")
        self.assertEqual(session.last_params, {"venue": "iq"})

    def test_converts_unix_candles_to_utc_dataframe(self):
        session = FakeSession({
            "open": True,
            "gaps": {"missingBars": 0},
            "candles": make_candles(self.now),
        })
        feed = OTChartsFeed(api_key="test", session=session)
        data = feed.get_candles(
            "iq", "EURUSD-OTC", 60, 40, now=self.now
        )
        self.assertEqual(list(data.columns), ["open", "high", "low", "close"])
        self.assertEqual(str(data.index.tz), "UTC")
        self.assertGreaterEqual(len(data), 30)

    def test_rejects_closed_symbol(self):
        session = FakeSession({"open": False, "candles": make_candles(self.now)})
        feed = OTChartsFeed(api_key="test", session=session)
        with self.assertRaises(OTChartsError):
            feed.get_candles("iq", "EURUSD-OTC", now=self.now)

    def test_rejects_gaps(self):
        session = FakeSession({
            "open": True,
            "gaps": {"missingBars": 2},
            "candles": make_candles(self.now),
        })
        feed = OTChartsFeed(api_key="test", session=session)
        with self.assertRaises(OTChartsError):
            feed.get_candles("iq", "EURUSD-OTC", now=self.now)

    def test_rejects_insufficient_history(self):
        session = FakeSession({
            "open": True,
            "gaps": {"missingBars": 0},
            "candles": make_candles(self.now, count=10),
        })
        feed = OTChartsFeed(api_key="test", session=session)
        with self.assertRaises(OTChartsError):
            feed.get_candles("iq", "EURUSD-OTC", now=self.now)

    def test_rejects_stale_candles(self):
        old_now = self.now - pd.Timedelta(hours=2)
        session = FakeSession({
            "open": True,
            "gaps": {"missingBars": 0},
            "candles": make_candles(old_now),
        })
        feed = OTChartsFeed(api_key="test", session=session)
        with self.assertRaises(OTChartsError):
            feed.get_candles("iq", "EURUSD-OTC", now=self.now)

    def test_requires_explicit_timezone_for_reference_time(self):
        session = FakeSession({
            "open": True,
            "gaps": {"missingBars": 0},
            "candles": make_candles(self.now),
        })
        feed = OTChartsFeed(api_key="test", session=session)
        with self.assertRaises(ValueError):
            feed.get_candles(
                "iq", "EURUSD-OTC", now="2026-11-28T12:00:00"
            )

    def test_rejects_invalid_timeframe(self):
        session = FakeSession({"symbols": []})
        feed = OTChartsFeed(api_key="test", session=session)
        with self.assertRaises(ValueError):
            feed.get_candles("iq", "EURUSD-OTC", 120, 40, now=self.now)


if __name__ == "__main__":
    unittest.main()
