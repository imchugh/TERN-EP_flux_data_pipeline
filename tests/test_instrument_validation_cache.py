"""Tests for the content-hash-addressed instrument validation cache."""

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from services.metadata.tern import instrument_validation_cache as cache_mod


class CacheTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        cache_path = Path(self._tmp_dir.name) / "instrument_validation_cache.json"
        lock_path = cache_path.with_name(cache_path.name + ".lock")
        self._patches = [
            patch.object(cache_mod, "CACHE_PATH", cache_path),
            patch.object(cache_mod, "LOCK_PATH", lock_path),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(self._tmp_dir.cleanup)
        for p in self._patches:
            self.addCleanup(p.stop)


class TestHashing(unittest.TestCase):
    def test_hash_bytes_is_sha256(self):
        import hashlib

        content = b"hello"
        self.assertEqual(
            cache_mod.hash_bytes(content), hashlib.sha256(content).hexdigest()
        )

    def test_hash_file_matches_hash_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yml"
            path.write_bytes(b"site: Foo\n")
            self.assertEqual(
                cache_mod.hash_file(path), cache_mod.hash_bytes(b"site: Foo\n")
            )


class TestLookupAndRecord(CacheTestCase):
    def test_lookup_miss_when_no_cache_file(self):
        self.assertIsNone(cache_mod.lookup("deadbeef"))

    def test_record_then_lookup_hit(self):
        cache_mod.record(
            "hash1", instrument_uris={"CSAT3B": "urn:csat3b"}, label="SiteA"
        )
        entry = cache_mod.lookup("hash1")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["label"], "SiteA")
        self.assertEqual(entry["instrument_uris"], {"CSAT3B": "urn:csat3b"})
        self.assertIn("validated_at", entry)

    def test_lookup_miss_for_different_hash(self):
        cache_mod.record("hash1", instrument_uris={}, label="SiteA")
        self.assertIsNone(cache_mod.lookup("hash2"))

    def test_record_atomic_write_leaves_no_tmp_file(self):
        cache_mod.record("hash1", instrument_uris={}, label="SiteA")
        tmp_files = list(cache_mod.CACHE_PATH.parent.glob("*.tmp"))
        self.assertEqual(tmp_files, [])

    def test_corrupt_cache_file_handled_gracefully(self):
        cache_mod.CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cache_mod.CACHE_PATH.write_text("not valid json{{{")
        self.assertIsNone(cache_mod.lookup("hash1"))
        # Self-heals: a subsequent record() succeeds and is retrievable.
        cache_mod.record("hash1", instrument_uris={}, label="SiteA")
        self.assertIsNotNone(cache_mod.lookup("hash1"))

    def test_concurrent_record_calls_do_not_lose_updates(self):
        n = 20
        with ThreadPoolExecutor(max_workers=n) as pool:
            list(
                pool.map(
                    lambda i: cache_mod.record(
                        f"hash-{i}", instrument_uris={}, label=f"Site{i}"
                    ),
                    range(n),
                )
            )
        data = json.loads(cache_mod.CACHE_PATH.read_text())
        self.assertEqual(len(data), n)
        for i in range(n):
            self.assertIn(f"hash-{i}", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
