"""Tests for LoggerClient: transport (URL/params, auth, timeout, session) and
paging past the logger's silent per-response record cap."""

import datetime as dt
import json
import unittest
from unittest import mock

import requests

from infrastructure import logger_functions
from infrastructure.logger_functions import LoggerClient

T0 = dt.datetime(2026, 11, 10)


def _response(payload) -> mock.Mock:
    return mock.Mock(text=json.dumps(payload))


class FakeLogger:
    """A 30-min table on a logger that caps each response at ``cap`` records.

    Mimics observed behaviour (CR6, 2026-11-18): every mode returns the oldest
    ``cap`` records of its span; ``since-record`` is inclusive, and asking past
    the newest record returns the oldest records in the table (wraparound).
    """

    def __init__(self, first_no=1000, n=100, cap=17):
        self.cap = cap
        self.table = [
            {
                "time": (T0 + dt.timedelta(minutes=30 * i)).isoformat(),
                "no": first_no + i,
                "vals": [float(i)],
            }
            for i in range(n)
        ]
        self.modes = []

    def __call__(self, url, params, timeout, session):
        mode, p1 = params["mode"], params.get("p1")
        self.modes.append(mode)
        if mode == "most-recent":
            span = self.table[-int(p1) :]
        elif mode == "since-record":
            span = [r for r in self.table if r["no"] >= int(p1)] or self.table
        elif mode == "since-time":
            span = [r for r in self.table if r["time"] >= p1]
        elif mode == "date-range":
            span = [r for r in self.table if p1 <= r["time"] < params["p2"]]
        return _response(
            {
                "head": {"fields": [{"name": "Fc", "type": "xsd:float"}]},
                "data": span[: self.cap],
            }
        )


class TestLoggerClientRequests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(logger_functions, "get")
        self.get = patcher.start()
        self.addCleanup(patcher.stop)

    def test_data_query_params_and_session(self):
        self.get.return_value = _response(
            {
                # No "settable"/"process" keys: older OSes (CR1000.Std.21) omit them.
                "head": {"fields": [{"name": "Batt", "type": "f"}]},
                "data": [{"time": "2026-11-18T00:30:00", "no": 7, "vals": [13.1]}],
            }
        )
        client = LoggerClient("10.0.0.1", auth=("admin", "1234"), timeout=5)
        df = client.get_data_since_date(
            "2026-11-18 00:00:00", table="Flux", variable="Batt"
        )

        kwargs = self.get.call_args_list[0].kwargs
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

    def test_control_characters_in_strings_are_accepted(self):
        self.get.return_value = mock.Mock(
            text='{"time": "x", "description": "Compiled.\r\n"}'
        )
        self.assertEqual(LoggerClient("10.0.0.1").clock_check()["time"], "x")

    def test_source_becomes_url_path(self):
        self.get.return_value = _response({"files": []})
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
        self.get.return_value = _response({"symbols": [{"name": "Flux"}]})
        client = LoggerClient("10.0.0.1")
        client.get_table_list()
        client.get_table_list()
        sessions = {id(c.kwargs["session"]) for c in self.get.call_args_list}
        self.assertEqual(len(sessions), 1)


class TestRetry(unittest.TestCase):
    def _fail(self, cause):
        exc = logger_functions.HTTPRequestError("GET request failed")
        exc.__cause__ = cause
        return exc

    def test_timeout_is_retried_once_then_succeeds(self):
        ok = _response({"time": "x"})
        with mock.patch.object(
            logger_functions,
            "get",
            side_effect=[self._fail(requests.ReadTimeout()), ok],
        ) as get:
            self.assertEqual(LoggerClient("10.0.0.1").clock_check()["time"], "x")
        self.assertEqual(get.call_count, 2)

    def test_repeated_timeouts_raise(self):
        fails = [self._fail(requests.ConnectTimeout()) for _ in range(5)]
        with mock.patch.object(logger_functions, "get", side_effect=fails) as get:
            with self.assertRaises(logger_functions.HTTPRequestError):
                LoggerClient("10.0.0.1").clock_check()
        self.assertEqual(get.call_count, logger_functions.RETRIES + 1)

    def test_http_error_is_not_retried(self):
        fail = self._fail(requests.HTTPError("401 Client Error"))
        with mock.patch.object(logger_functions, "get", side_effect=[fail]) as get:
            with self.assertRaises(logger_functions.HTTPRequestError):
                LoggerClient("10.0.0.1").clock_check()
        self.assertEqual(get.call_count, 1)


class TestPaging(unittest.TestCase):
    def setUp(self):
        self.fake = FakeLogger()
        patcher = mock.patch.object(logger_functions, "get", side_effect=self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = LoggerClient("10.0.0.1")

    def _assert_contiguous(self, df, first_no, n):
        self.assertEqual(df["RECORD"].tolist(), list(range(first_no, first_no + n)))

    def test_since_time_pages_to_newest_without_wrapping(self):
        df = self.client.get_data_since_date(T0 + dt.timedelta(days=1), table="Flux")
        self._assert_contiguous(df, 1048, 52)  # records 48..99 of the table
        self.assertEqual(self.fake.modes[0], "since-time")
        self.assertTrue(all(m == "since-record" for m in self.fake.modes[1:]))

    def test_most_recent_returns_the_newest_n(self):
        df = self.client.get_data_n_records_back(table="Flux", recs_back=48)
        self._assert_contiguous(df, 1052, 48)

    def test_date_range_is_end_exclusive_and_complete(self):
        df = self.client.get_data_by_date_range(
            T0, T0 + dt.timedelta(days=1), table="Flux"
        )
        self._assert_contiguous(df, 1000, 48)
        self.assertLess(df.index[-1], T0 + dt.timedelta(days=1))

    def test_uncapped_logger_needs_one_confirming_request(self):
        self.fake.cap = 10_000
        df = self.client.get_data_since_date(T0, table="Flux")
        self._assert_contiguous(df, 1000, 100)
        self.assertEqual(len(self.fake.modes), 2)


if __name__ == "__main__":
    unittest.main()
