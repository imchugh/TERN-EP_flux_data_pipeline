"""Tests for infrastructure.credentials (secrets-file login lookup)."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from infrastructure import credentials

SECRETS_YML = """\
SITE_DETAILS: {USERNAME: sparql_user, PASSWORD: sparql_pw}
LOGGERS:
  Calperum: {USERNAME: admin, PASSWORD: "1234"}
"""


class TestGetLogin(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "logins.yml"
        path.write_text(SECRETS_YML, encoding="utf-8")
        patcher = mock.patch.object(credentials, "secrets_path", return_value=path)
        patcher.start()
        self.addCleanup(patcher.stop)
        credentials.load_secrets.cache_clear()
        self.addCleanup(credentials.load_secrets.cache_clear)

    def test_single_login_section(self):
        self.assertEqual(
            credentials.get_login("SITE_DETAILS"), ("sparql_user", "sparql_pw")
        )

    def test_named_entry_in_section(self):
        # A numeric-looking UID must come back as given (quoted in YAML).
        self.assertEqual(
            credentials.get_login("LOGGERS", "Calperum"), ("admin", "1234")
        )

    def test_missing_entry_optional_returns_none(self):
        self.assertIsNone(credentials.get_login("LOGGERS", "Yanco", required=False))
        self.assertIsNone(credentials.get_login("NOPE", "Yanco", required=False))

    def test_missing_required_raises(self):
        with self.assertRaises(KeyError):
            credentials.get_login("LOGGERS", "Yanco")
        with self.assertRaises(KeyError):
            credentials.get_login("NOPE")


if __name__ == "__main__":
    unittest.main()
