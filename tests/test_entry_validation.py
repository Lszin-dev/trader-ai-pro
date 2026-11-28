import unittest
from datetime import datetime, timedelta, timezone

from entry_validation import validate_entry_quote


class EntryQuoteValidationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 28, 12, 0, 0, tzinfo=timezone.utc)

    def test_accepts_recent_quote_with_timezone(self):
        result = validate_entry_quote(
            1.08525,
            self.now - timedelta(seconds=3),
            now=self.now,
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["price"], 1.08525)

    def test_rejects_zero_or_negative_price(self):
        for price in (0, -1):
            with self.subTest(price=price):
                result = validate_entry_quote(
                    price, self.now, now=self.now
                )
                self.assertFalse(result["valid"])

    def test_rejects_non_numeric_price(self):
        result = validate_entry_quote("indisponivel", self.now, now=self.now)
        self.assertFalse(result["valid"])

    def test_rejects_nan_and_infinity(self):
        for price in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(price=price):
                result = validate_entry_quote(
                    price, self.now, now=self.now
                )
                self.assertFalse(result["valid"])

    def test_rejects_stale_quote(self):
        result = validate_entry_quote(
            1.08525,
            self.now - timedelta(seconds=11),
            now=self.now,
        )
        self.assertFalse(result["valid"])
        self.assertIn("desatualizada", result["reason"])

    def test_rejects_timestamp_too_far_in_future(self):
        result = validate_entry_quote(
            1.08525,
            self.now + timedelta(seconds=3),
            now=self.now,
        )
        self.assertFalse(result["valid"])
        self.assertIn("futuro", result["reason"])

    def test_rejects_timestamp_without_timezone(self):
        result = validate_entry_quote(
            1.08525,
            "2026-11-28T12:00:00",
            now=self.now,
        )
        self.assertFalse(result["valid"])

    def test_rejects_invalid_timestamp(self):
        result = validate_entry_quote(
            1.08525, "horario-invalido", now=self.now
        )
        self.assertFalse(result["valid"])

    def test_accepts_iso_timestamp_and_normalizes_to_utc(self):
        result = validate_entry_quote(
            1.08525,
            "2026-11-28T09:00:00-03:00",
            now=self.now,
        )
        self.assertTrue(result["valid"])
        self.assertEqual(
            result["entry_timestamp"],
            "2026-11-28T12:00:00+00:00",
        )


if __name__ == "__main__":
    unittest.main()
