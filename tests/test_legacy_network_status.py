"""Tests for the default-range masking used by the network status monitors."""

import unittest
from unittest import mock

import pandas as pd

from services.network.data_monitor import mask_to_default_range

PATCH = "services.network.data_monitor._range_defaults"


class MaskToDefaultRangeTestCase(unittest.TestCase):
    def setUp(self):
        self.series = pd.Series([1.0, 500.0, -80.0, -5.0])

    def test_flat_default_masks_values_outside_the_bounds(self):
        with mock.patch(PATCH, return_value={"Fco2": [-50, 30]}):
            out = mask_to_default_range(self.series, "Fco2")
        self.assertEqual(out.dropna().tolist(), [1.0, -5.0])

    def test_no_default_leaves_the_series_unchanged(self):
        with mock.patch(PATCH, return_value={}):
            out = mask_to_default_range(self.series, "Fco2")
        self.assertEqual(out.tolist(), self.series.tolist())

    def test_statistic_keyed_entry_without_a_statistic_is_unfiltered(self):
        # The legacy monitor's SUBSET names carry no statistic; a nested entry
        # can't be resolved and must degrade to no filtering, not an error.
        with mock.patch(PATCH, return_value={"Ta": {"Av": [-10, 50]}}):
            out = mask_to_default_range(self.series, "Ta")
        self.assertEqual(out.tolist(), self.series.tolist())


if __name__ == "__main__":
    unittest.main()
