"""Tests for the plausible-range helper in orchestration/legacy_network_status.py."""

import unittest

from orchestration.legacy_network_status import _plausible_range


class PlausibleRangeTestCase(unittest.TestCase):
    def test_flat_default_is_returned_as_a_pair(self):
        self.assertEqual(_plausible_range("Fco2", {"Fco2": [-50, 30]}), (-50, 30))

    def test_no_default_gives_open_bounds(self):
        self.assertEqual(_plausible_range("Fco2", {}), (None, None))

    def test_statistic_keyed_entry_without_a_statistic_gives_open_bounds(self):
        # The monitor's SUBSET names carry no statistic; a nested entry can't
        # be resolved and must degrade to no filtering, not an error.
        self.assertEqual(_plausible_range("Ta", {"Ta": {"Av": [-10, 50]}}), (None, None))


if __name__ == "__main__":
    unittest.main()
