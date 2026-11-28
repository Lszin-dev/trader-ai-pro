import unittest
from datetime import datetime, timezone, timedelta
from quota_budget import DailyBudget

class BudgetTests(unittest.TestCase):
    def test_daily_budget_and_rollover(self):
        now=datetime(2026,11,30,23,59,tzinfo=timezone.utc)
        b=DailyBudget(3)
        self.assertTrue(b.reserve(3,now))
        self.assertFalse(b.reserve(1,now))
        self.assertTrue(b.reserve(1,now+timedelta(minutes=1)))

    def test_provider_sync_never_reduces_local_count(self):
        b=DailyBudget(750)
        b.reserve(5)
        b.sync({"daily_usage":2,"plan_daily_limit":800})
        self.assertEqual(b.snapshot()["estimated_credits"],5)
        b.sync({"daily_usage":748,"plan_daily_limit":800})
        self.assertTrue(b.reserve())
        self.assertFalse(b.reserve())

    def test_lower_provider_limit(self):
        b=DailyBudget()
        b.sync({"daily_usage":0,"plan_daily_limit":100})
        self.assertEqual(b.snapshot()["budget_limit"],95)
