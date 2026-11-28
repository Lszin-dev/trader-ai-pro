import unittest

import pandas as pd

from twelvedata_feed import TwelveDataError, TwelveDataFeed


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

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


def make_values(now, count=80):
    end = pd.Timestamp(now).floor("min")
    start = end - pd.Timedelta(minutes=count - 1)
    rows = []
    for i in range(count):
        stamp = start + pd.Timedelta(minutes=i)
        price = 1.08 + i * 0.0001
        rows.append({
            "datetime": stamp.strftime("%Y-%m-%d %H:%M:%S"),
            "open": str(price),
            "high": str(price + 0.0002),
            "low": str(price - 0.0001),
            "close": str(price + 0.0001),
        })
    return rows


class TwelveDataFeedTests(unittest.TestCase):
    def setUp(self):
        self.now = pd.Timestamp("2026-11-30T12:00:30Z")

    def test_converts_candles_to_utc_and_uses_auth_header(self):
        session = FakeSession({"meta": {}, "values": make_values(self.now)})
        feed = TwelveDataFeed(api_key="secret-test", session=session)
        data = feed.get_candles(now=self.now)
        self.assertEqual(str(data.index.tz), "UTC")
        self.assertEqual(list(data.columns), ["open", "high", "low", "close"])
        self.assertEqual(session.headers["Authorization"], "apikey secret-test")
        self.assertNotIn("apikey", str(session.last_params))

    def test_excludes_current_unclosed_candle(self):
        session = FakeSession({"values": make_values(self.now)})
        feed = TwelveDataFeed(api_key="test", session=session)
        data = feed.get_candles(now=self.now)
        self.assertLessEqual(data.index[-1] + pd.Timedelta(minutes=1), self.now)

    def test_rejects_stale_market_data(self):
        old = self.now - pd.Timedelta(minutes=10)
        session = FakeSession({"values": make_values(old)})
        feed = TwelveDataFeed(api_key="test", session=session)
        with self.assertRaises(TwelveDataError):
            feed.get_candles(now=self.now)

    def test_rejects_insufficient_history(self):
        session = FakeSession({"values": make_values(self.now, count=10)})
        feed = TwelveDataFeed(api_key="test", session=session)
        with self.assertRaises(TwelveDataError):
            feed.get_candles(now=self.now)

    def test_rejects_provider_error(self):
        session = FakeSession({"code": 429, "message": "API credits exhausted", "status": "error"})
        feed = TwelveDataFeed(api_key="test", session=session)
        with self.assertRaises(TwelveDataError):
            feed.get_candles(now=self.now)

    def test_rejects_invalid_timeframe(self):
        session = FakeSession({"values": make_values(self.now)})
        feed = TwelveDataFeed(api_key="test", session=session)
        with self.assertRaises(ValueError):
            feed.get_candles(interval="5min", now=self.now)

    def test_never_places_api_key_in_query_parameters(self):
        session = FakeSession({"values": make_values(self.now)})
        feed = TwelveDataFeed(api_key="do-not-leak", session=session)
        feed.get_candles(now=self.now)
        self.assertNotIn("apikey", session.last_params)
        self.assertNotIn("do-not-leak", str(session.last_params))

    def test_exchange_rate_returns_recent_timestamped_quote(self):
        stamp = int((self.now - pd.Timedelta(seconds=3)).timestamp())
        session = FakeSession({"symbol": "EUR/USD", "rate": 1.08525, "timestamp": stamp})
        feed = TwelveDataFeed(api_key="test", session=session)
        result = feed.get_exchange_rate(now=self.now)
        self.assertEqual(result["price"], 1.08525)
        self.assertLessEqual(result["age_seconds"], 3.1)
        self.assertIn("exchange_rate", session.last_url)
        self.assertNotIn("apikey", session.last_params)

    def test_exchange_rate_rejects_stale_quote(self):
        stamp = int((self.now - pd.Timedelta(seconds=30)).timestamp())
        session = FakeSession({"symbol": "EUR/USD", "rate": 1.08525, "timestamp": stamp})
        feed = TwelveDataFeed(api_key="test", session=session)
        with self.assertRaises(TwelveDataError):
            feed.get_exchange_rate(now=self.now, max_age_seconds=15)

    def test_usage_accepts_paid_plan_without_daily_fields(self):
        session = FakeSession({
            "timestamp": "2026-11-30 12:00:00",
            "current_usage": 2,
            "plan_limit": 55,
            "plan_category": "grow",
        })
        feed = TwelveDataFeed(api_key="test", session=session)
        usage = feed.get_usage()
        self.assertEqual(usage["plan_limit"], 55)
        self.assertIsNone(usage["daily_usage"])


if __name__ == "__main__":
    unittest.main()
