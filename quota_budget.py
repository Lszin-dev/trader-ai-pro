"""Conservative per-process credit estimate; provider snapshot is authoritative
only at the instant of retrieval. This is not a guarantee of account-wide usage.
"""
from datetime import datetime, timezone

class DailyBudget:
    def __init__(self, cap=750):
        self.cap=int(cap)
        if self.cap < 1:
            raise ValueError("Daily budget must be positive.")
        self.day=None
        self.used=0
        self.limit=self.cap

    def _roll(self, now=None):
        day=(now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
        changed=day!=self.day
        if changed:
            self.day=day
            self.used=0
            self.limit=self.cap
        return changed

    def sync(self, usage, now=None):
        self._roll(now)
        try:
            reported=int(usage["daily_usage"])
            limit=int(usage["plan_daily_limit"])
            if reported < 0 or limit <= 0:
                return
        except (KeyError, TypeError, ValueError, OverflowError):
            return
        self.used=max(self.used,reported+1)
        self.limit=min(self.cap,max(1,int(limit*0.95)))

    def reserve(self, cost=1, now=None):
        self._roll(now)
        if cost < 1 or self.used+cost>self.limit:
            return False
        self.used+=cost
        return True

    def snapshot(self, now=None):
        self._roll(now)
        return {"estimated_credits":self.used,"budget_limit":self.limit,"utc_day":self.day.isoformat()}
