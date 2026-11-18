"""Tests for the API-based logger status check (sidelined, kept for future use)."""

import unittest
from unittest import mock

from services.network import logger_monitor

SUMMARY = {"model": "CR1000X"}
STATUS = {key: f"{key}_val" for key in logger_monitor.STATUS_SUBSET}


class TestCheckLoggerStatus(unittest.TestCase):
    def setUp(self):
        for target, kwargs in [
            ("SITE_IP", {"new": {"Calperum": {"host": "10.0.0.7"}}}),
            ("resolve_endpoint", {"return_value": "192.168.7.10"}),
        ]:
            patcher = mock.patch.object(logger_monitor, target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(
            logger_monitor.logger_functions,
            "get_logger_status",
            return_value=(SUMMARY, STATUS),
        )
        self.api = patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, login):
        with mock.patch.object(
            logger_monitor.credentials, "get_login", return_value=login
        ) as get_login:
            result = logger_monitor.check_logger_status("Calperum")
        get_login.assert_called_once_with("LOGGERS", "Calperum", required=False)
        return result

    def test_login_from_secrets_is_sent(self):
        result = self._run(("admin", "1234"))
        self.api.assert_called_once_with(ip_addr="192.168.7.10", auth=("admin", "1234"))
        self.assertIsNone(result["error"])
        self.assertEqual(result["model"], "CR1000X")

    def test_unlisted_site_sends_no_login(self):
        self._run(None)
        self.api.assert_called_once_with(ip_addr="192.168.7.10", auth=None)

    def test_api_failure_returns_null_result_with_error(self):
        self.api.side_effect = RuntimeError("401 Unauthorized")
        result = self._run(("admin", "wrong"))
        self.assertEqual(result["error"], "401 Unauthorized")
        self.assertIsNone(result["model"])

    def test_unknown_site_raises(self):
        with self.assertRaises(KeyError):
            logger_monitor.check_logger_status("Nowhere")


if __name__ == "__main__":
    unittest.main()
