from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.utils.time import get_business_date


class TimeUtilityTests(unittest.TestCase):
    def test_business_date_across_utc_day_boundary(self) -> None:
        at = datetime(2026, 1, 1, 18, 30, tzinfo=timezone.utc)
        self.assertEqual(get_business_date(at), "2026-01-02")


if __name__ == "__main__":
    unittest.main()
