import unittest
from datetime import datetime, timezone

from market_guard import forex_market_status


class ForexMarketGuardTests(unittest.TestCase):
    def test_saturday_is_closed(self):
        result = forex_market_status(datetime(2026, 11, 28, 15, 0, tzinfo=timezone.utc))
        self.assertFalse(result["open"])

    def test_monday_is_open(self):
        result = forex_market_status(datetime(2026, 11, 30, 15, 0, tzinfo=timezone.utc))
        self.assertTrue(result["open"])

    def test_friday_after_new_york_close_is_closed(self):
        result = forex_market_status(datetime(2026, 11, 27, 23, 0, tzinfo=timezone.utc))
        self.assertFalse(result["open"])

    def test_sunday_after_new_york_open_is_open(self):
        result = forex_market_status(datetime(2026, 11, 29, 23, 0, tzinfo=timezone.utc))
        self.assertTrue(result["open"])

    def test_rejects_naive_datetime(self):
        with self.assertRaises(ValueError):
            forex_market_status(datetime(2026, 11, 30, 12, 0))


if __name__ == "__main__":
    unittest.main()
