"""Tests for orchestration/legacy_rtmc_export.py's _apply_default_range_limits."""

import unittest
from datetime import datetime, timedelta
from unittest import mock

import numpy as np
import xarray as xr

from orchestration.legacy_rtmc_export import _apply_default_range_limits
from services.metadata.qc_config_schema import (
    RangeCheckSpec,
    SiteQCConfig,
    VariableQCSpec,
)


def _build_dataset():
    dates = [datetime(2026, 1, 1) + timedelta(minutes=30 * i) for i in range(5)]

    # Ta_2m: explicit per-site override should apply, regardless of any
    # default (Ta isn't even present in the mocked defaults below).
    ta = [10.0, 10.0, 100.0, 10.0, 10.0]  # index 2 out of the -5..45 override

    # AH_IRGA_Av: no explicit override -> falls back to the default lookup,
    # which needs statistic_type to resolve the Av-keyed default.
    ah = [10.0, 10.0, 50.0, 10.0, 10.0]  # index 2 out of the 0..30 default

    ds = xr.Dataset(
        {
            "Ta_2m": ("time", np.array(ta)),
            "AH_IRGA_Av": ("time", np.array(ah), {"statistic_type": "average"}),
            "crs": ((), 0),
        },
        coords={"time": dates},
    )
    return ds


class ApplyDefaultRangeLimitsTestCase(unittest.TestCase):
    def setUp(self):
        self.qc_config = SiteQCConfig(
            site_name="TestSite",
            variables={
                "Ta_2m": VariableQCSpec(
                    range_check=RangeCheckSpec(lower=-5, upper=45)
                ),
            },
        )
        self.range_defaults = {"AH": {"Av": [0, 30]}}

        patcher_qc = mock.patch(
            "orchestration.legacy_rtmc_export.qc_config_schema.load_qc_config",
            return_value=self.qc_config,
        )
        patcher_defaults = mock.patch(
            "orchestration.legacy_rtmc_export.qc_config_schema.load_range_defaults",
            return_value=self.range_defaults,
        )
        patcher_qc.start()
        patcher_defaults.start()
        self.addCleanup(patcher_qc.stop)
        self.addCleanup(patcher_defaults.stop)

    def test_explicit_site_override_takes_precedence(self):
        ds = _build_dataset()
        out = _apply_default_range_limits(ds, site_name="TestSite")

        ta = out["Ta_2m"].values
        self.assertTrue(np.isnan(ta[2]))
        self.assertFalse(np.isnan(ta[0]))

    def test_falls_back_to_default_for_unconfigured_variable(self):
        ds = _build_dataset()
        out = _apply_default_range_limits(ds, site_name="TestSite")

        ah = out["AH_IRGA_Av"].values
        self.assertTrue(np.isnan(ah[2]))
        self.assertFalse(np.isnan(ah[0]))

    def test_crs_is_left_untouched(self):
        ds = _build_dataset()
        out = _apply_default_range_limits(ds, site_name="TestSite")
        self.assertEqual(int(out["crs"].values), 0)


if __name__ == "__main__":
    unittest.main()
