"""Tests for the persistent instrument-validation cache wired into
load_runtime_config."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services.metadata.tern import instrument_validation_cache as cache_mod
from services.metadata.tern.runtime_config_loader import load_runtime_config

VALID_YAML = """\
site: TestSite
file_formats:
  flux: CSI
flux_system: TERNFLUX
flux_file: flux
variables:
  Ta_Av:
    height: 2.0
    statistic_type: average
    input_variables:
      Ta_1_1_1:
        instrument: Campbell Scientific HMP155A
        file: flux
        units: degC
"""

EDITED_YAML = VALID_YAML.replace("height: 2.0", "height: 2.5")


class RuntimeConfigLoaderCacheTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)

        cache_path = Path(self._tmp_dir.name) / "instrument_validation_cache.json"
        lock_path = cache_path.with_name(cache_path.name + ".lock")
        for p in (
            patch.object(cache_mod, "CACHE_PATH", cache_path),
            patch.object(cache_mod, "LOCK_PATH", lock_path),
        ):
            p.start()
            self.addCleanup(p.stop)

        self.config_path = Path(self._tmp_dir.name) / "TestSite.yml"
        self.config_path.write_text(VALID_YAML)

        is_valid_patch = patch(
            "services.metadata.tern.instrument_registry.is_valid_instrument",
            Mock(return_value=True),
        )
        get_uri_patch = patch(
            "services.metadata.tern.instrument_registry.get_instrument_uri",
            Mock(return_value="urn:example:hmp155a"),
        )
        self.mock_is_valid = is_valid_patch.start()
        self.mock_get_uri = get_uri_patch.start()
        self.addCleanup(is_valid_patch.stop)
        self.addCleanup(get_uri_patch.stop)

    def test_uncached_config_calls_is_valid_instrument(self):
        load_runtime_config(self.config_path)
        self.mock_is_valid.assert_called_once_with("Campbell Scientific HMP155A")

    def test_cached_config_skips_is_valid_instrument_on_second_load(self):
        load_runtime_config(self.config_path)
        self.mock_is_valid.reset_mock()

        cfg = load_runtime_config(self.config_path)

        self.mock_is_valid.assert_not_called()
        self.assertEqual(cfg.site_name, "TestSite")

    def test_editing_config_invalidates_cache(self):
        load_runtime_config(self.config_path)
        self.mock_is_valid.reset_mock()

        self.config_path.write_text(EDITED_YAML)
        load_runtime_config(self.config_path)

        self.mock_is_valid.assert_called_once()

    def test_failed_validation_does_not_poison_cache(self):
        self.mock_is_valid.return_value = False

        with self.assertRaises(ValueError):
            load_runtime_config(self.config_path)

        content_hash = cache_mod.hash_file(self.config_path)
        self.assertIsNone(cache_mod.lookup(content_hash))

        self.mock_is_valid.reset_mock()
        with self.assertRaises(ValueError):
            load_runtime_config(self.config_path)
        self.mock_is_valid.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
