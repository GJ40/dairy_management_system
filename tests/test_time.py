from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.utils.time import get_business_date, utc_now_naive


class TimeUtilityTests(unittest.TestCase):
    def test_business_date_across_utc_day_boundary(self) -> None:
        at = datetime(2026, 1, 1, 18, 30, tzinfo=timezone.utc)
        self.assertEqual(get_business_date(at), "2026-01-02")

    def test_utc_now_naive_has_no_timezone(self) -> None:
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        value = utc_now_naive()
        after = datetime.now(timezone.utc).replace(tzinfo=None)
        self.assertIsNone(value.tzinfo)
        self.assertGreaterEqual(value, before)
        self.assertLessEqual(value, after)


if __name__ == "__main__":
    unittest.main()
