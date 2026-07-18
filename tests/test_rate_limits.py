"""Distributed/local provider capacity guards."""

from __future__ import annotations

import dataclasses
import unittest
from unittest.mock import patch

from services import rate_limits
from services.config import settings


class ConcurrencyLimitTest(unittest.TestCase):
    def setUp(self):
        rate_limits._active.clear()

    def tearDown(self):
        rate_limits._active.clear()

    def test_local_capacity_is_released_after_use(self):
        local_settings = dataclasses.replace(settings, redis_url="")
        with patch.object(rate_limits, "settings", local_settings):
            with rate_limits.concurrency("test", limit=1, lease_seconds=30):
                with self.assertRaises(rate_limits.ConcurrencyLimitExceeded):
                    with rate_limits.concurrency(
                        "test",
                        limit=1,
                        lease_seconds=30,
                    ):
                        pass
            with rate_limits.concurrency("test", limit=1, lease_seconds=30):
                pass


if __name__ == "__main__":
    unittest.main()
