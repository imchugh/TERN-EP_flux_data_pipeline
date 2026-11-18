"""Tests for the LoggerClient transport (URL/params, auth, timeout, session)."""

import unittest
from unittest import mock

from infrastructure import logger_functions
from infrastructure.logger_functions import LoggerClient


class TestLoggerClientRequests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(logger_functions, "get")
        self.get = patcher.start()
        self.addCleanup(patcher.stop)

    def test_data_query_params_and_session(self):
        self.get.return_value.json.return_value = {
            "head": {"fields": [{"name": "Batt", "type": "f", "settable": False}]},
            "data": [{"time": "2026-11-18T00:30:00", "no": 7, "vals": [13.1]}],
        }
        client = LoggerClient("10.0.0.1", auth=("admin", "1234"), timeout=5)
        df = client.get_data_since_date(
            "2026-11-18 00:00:00", table="Flux", variable="Batt"
        )

        kwargs = self.get.call_args.kwargs
        self.assertEqual(kwargs["url"], "http://10.0.0.1/")
        self.assertEqual(
            kwargs["params"],
            {
                "command": "dataquery",
                "uri": "dl:Flux.Batt",
                "mode": "since-time",
                "p1": "2026-11-18T00:00:00",
                "format": "json",
            },
        )
        self.assertEqual(kwargs["timeout"], 5)
        self.assertEqual(kwargs["session"].auth, ("admin", "1234"))
        self.assertEqual(df.loc[df.index[0], "RECORD"], 7)
        self.assertEqual(df.loc[df.index[0], "Batt"], 13.1)

    def test_source_becomes_url_path(self):
        self.get.return_value.json.return_value = {"files": []}
        LoggerClient("10.0.0.1").list_files("CRD")
        kwargs = self.get.call_args.kwargs
        self.assertEqual(kwargs["url"], "http://10.0.0.1/CRD/")
        self.assertEqual(kwargs["params"]["command"], "ListFiles")
        self.assertIsNone(kwargs["session"].auth)
        self.assertEqual(kwargs["timeout"], logger_functions.DEFAULT_TIMEOUT)

    def test_invalid_source_and_mode_rejected_before_request(self):
        client = LoggerClient("10.0.0.1")
        with self.assertRaises(ValueError):
            client.list_files("SD")
        with self.assertRaises(ValueError):
            client._data_query(table="Flux", mode="bogus")
        self.get.assert_not_called()

    def test_session_reused_across_calls(self):
        self.get.return_value.json.return_value = {"symbols": [{"name": "Flux"}]}
        client = LoggerClient("10.0.0.1")
        client.get_table_list()
        client.get_table_list()
        sessions = {id(c.kwargs["session"]) for c in self.get.call_args_list}
        self.assertEqual(len(sessions), 1)


if __name__ == "__main__":
    unittest.main()
