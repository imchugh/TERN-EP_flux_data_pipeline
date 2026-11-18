"""Campbell Scientific datalogger HTTP API client.

``LoggerClient`` queries data, inspects tables, lists files and checks status
through a logger's web-server API (JSON format). One client per logger: it
holds the address, the optional login and the timeout, and sends every
request through one ``requests.Session`` so consecutive calls (e.g.
``build_lookup_table``) reuse the connection. A session is not thread-safe;
give each worker thread its own client.
"""

import datetime as dt
import json
import logging
from dataclasses import dataclass, field

import pandas as pd
import requests
from fluxcore import DATA_TIME_FORMAT as TIME_FORMAT

from infrastructure.external_io import HTTPRequestError, get

logger = logging.getLogger(__name__)

SECONDARY_TIME_FORMAT = TIME_FORMAT + ".%f"
ALLOWED_QUERY_MODES = [
    "most-recent",
    "date-range",
    "since-time",
    "since-record",
    "backfill",
]
VALID_FILE_SOURCES = ["CPU", "CRD", "USR"]

# Seconds to wait for a logger to respond. Generous because many loggers sit
# behind cellular modems; override per client.
DEFAULT_TIMEOUT = 10

# Upper bound on requests for one paged data query (see
# LoggerClient._query_records), so a misbehaving logger can't loop forever.
MAX_PAGES = 10_000

# Extra attempts for a request that timed out or lost its connection (slow
# cellular links stall now and then). Every API call is a read-only GET, so
# repeating one is safe. HTTP errors such as 401 are not retried.
RETRIES = 1

# HTTP Basic credentials for a password-protected logger web server, as
# ``(user, password)``. With the default .csipasswd that is ``("admin", <UID>)``.
Auth = tuple[str, str] | None


@dataclass
class LoggerClient:
    """Client for one Campbell logger's HTTP API.

    Args:
        ip_addr: IP address of the logger.
        auth: HTTP Basic ``(user, password)`` for a password-protected logger;
            None (default) for one without a password.
        timeout: Seconds to wait for each response.

    Usable as a context manager to close the session's connection on exit.
    """

    ip_addr: str
    auth: Auth = None
    timeout: float = DEFAULT_TIMEOUT
    _session: requests.Session = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Open the session, carrying the login for every request."""
        self._session = requests.Session()
        self._session.auth = self.auth

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def __enter__(self) -> "LoggerClient":
        """Return the client for use in a ``with`` block."""
        return self

    def __exit__(self, *exc_info) -> None:
        """Close the session on leaving the ``with`` block."""
        self.close()

    # Transport

    def request(self, command: str, source: str | None = None, **params) -> dict:
        """Send one API command and return the parsed JSON response.

        Args:
            command: API command (e.g. ``'dataquery'``, ``'ClockCheck'``).
            source: Storage source the command applies to (``'CPU'``,
                ``'CRD'``, ``'USR'``), which becomes the URL path. None
                (default) for commands on the logger itself.
            **params: Further query parameters; ``requests`` URL-encodes them.

        Returns:
            Parsed JSON response body.

        Raises:
            ValueError: If ``source`` is not a recognised source.
            HTTPRequestError: On HTTP error status (e.g. 401 for a missing or
                wrong login), or on connection failure or timeout once
                ``RETRIES`` further attempts have also failed.
        """
        path = ""
        if source is not None:
            _check_source(source=source)
            path = f"{source}/"
        url = f"http://{self.ip_addr}/{path}"
        query = {"command": command, **params, "format": "json"}
        for attempt in range(RETRIES + 1):
            logger.debug(
                "logger_request",
                extra={"url": url, "params": query, "attempt": attempt},
            )
            try:
                response = get(
                    url=url, params=query, timeout=self.timeout, session=self._session
                )
                break
            except HTTPRequestError as exc:
                transient = isinstance(
                    exc.__cause__, (requests.Timeout, requests.ConnectionError)
                )
                if not transient or attempt == RETRIES:
                    raise
                logger.warning(
                    "logger_request_retry",
                    extra={"url": url, "params": query, "error": str(exc)},
                )
        # strict=False: string fields (e.g. Status CompileResults) can hold raw
        # control characters such as \r\n, which strict JSON rejects.
        return json.loads(response.text, strict=False)

    def _data_query(
        self, table: str, mode: str, variable: str | None = None, **params
    ) -> dict:
        """Send one ``dataquery`` command for a table (or one variable in it).

        Returns the raw response, which may be truncated: see
        ``_query_records``.
        """
        if mode not in ALLOWED_QUERY_MODES:
            raise ValueError(f"mode must be one of {', '.join(ALLOWED_QUERY_MODES)}")
        uri = f"dl:{table}" if variable is None else f"dl:{table}.{variable}"
        return self.request("dataquery", uri=uri, mode=mode, **params)

    def _query_records(
        self,
        table: str,
        mode: str,
        variable: str | None = None,
        *,
        limit: int | None = None,
        end: dt.datetime | None = None,
        **params,
    ) -> tuple[dict, list[dict]]:
        """Run a ``dataquery`` to completion, paging past truncated responses.

        A logger silently caps how much one response holds (by size, so the
        record count depends on model, OS and table width; a CR6 with a
        63-column table returns 17), and returns the *oldest* records of the
        requested span. So after the first response this keeps asking for
        ``since-record <last received>`` (inclusive) until no newer record
        comes back. It never asks past the newest record: the logger answers
        that with the oldest records in the table (ring-buffer wraparound),
        so any record not numbered above the last one ends the paging.

        Args:
            table: Logger table.
            mode: First request's query mode.
            variable: Optional single variable.
            limit: Stop once this many records are held (``most-recent``).
            end: Stop at, and drop, records at or after this time
                (``date-range``, whose end the logger treats as exclusive).
            **params: First request's mode parameters (``p1``, ``p2``).

        Returns:
            ``(head, records)``: the first response's head block and the
            records in ascending record-number order.
        """
        content = self._data_query(table=table, mode=mode, variable=variable, **params)
        head, records = content["head"], list(content["data"])
        n_requests = 1

        def done() -> bool:
            if not records:
                return True
            if limit is not None and len(records) >= limit:
                return True
            last_time = _convert_time_from_logger_format(records[-1]["time"])
            return end is not None and last_time >= end

        while not done():
            if n_requests >= MAX_PAGES:
                raise RuntimeError(
                    f"{table} query on {self.ip_addr} not complete after "
                    f"{MAX_PAGES} requests"
                )
            last_no = int(records[-1]["no"])
            page = self._data_query(
                table=table, mode="since-record", variable=variable, p1=last_no
            )["data"]
            n_requests += 1
            new = []
            for record in page:
                no = int(record["no"])
                if no <= last_no:
                    if new:  # numbering went backwards: wrapped round
                        break
                    continue  # the inclusive overlap record
                new.append(record)
                last_no = no
            if not new:
                break
            records.extend(new)

        if end is not None:
            records = [
                r for r in records if _convert_time_from_logger_format(r["time"]) < end
            ]
        if limit is not None:
            records = records[:limit]
        logger.debug(
            "data_query_complete",
            extra={
                "ip_addr": self.ip_addr,
                "table": table,
                "n_records": len(records),
                "n_requests": n_requests,
            },
        )
        return head, records

    # Data

    def get_data_by_date_range(
        self,
        start_date: str | dt.datetime,
        end_date: str | dt.datetime,
        table: str,
        variable: str | None = None,
    ) -> pd.DataFrame:
        """Get all data from the start date up to (not including) the end date.

        Args:
            start_date: Start date (``TIME_FORMAT`` string or datetime),
                inclusive.
            end_date: End date (``TIME_FORMAT`` string or datetime), exclusive.
            table: Table from which to collect data.
            variable: Variable for which to collect data. Defaults to None (all).

        Returns:
            Time-indexed DataFrame of the requested data.
        """
        end_date = _to_datetime(end_date)
        return self._format_data(
            *self._query_records(
                table=table,
                mode="date-range",
                variable=variable,
                end=end_date,
                p1=_convert_time_to_logger_format(time=start_date),
                p2=_convert_time_to_logger_format(time=end_date),
            )
        )

    def get_data_since_date(
        self,
        start_date: str | dt.datetime,
        table: str,
        variable: str | None = None,
    ) -> pd.DataFrame:
        """Get all data from a specified date (inclusive) to the newest record.

        Args:
            start_date: Start date (``TIME_FORMAT`` string or datetime).
            table: Table from which to collect data.
            variable: Variable for which to collect data. Defaults to None (all).

        Returns:
            Time-indexed DataFrame of the requested data.
        """
        return self._format_data(
            *self._query_records(
                table=table,
                mode="since-time",
                variable=variable,
                p1=_convert_time_to_logger_format(time=start_date),
            )
        )

    def get_data_n_records_back(
        self,
        table: str,
        recs_back: int = 1,
        variable: str | None = None,
    ) -> pd.DataFrame:
        """Get the most recent ``recs_back`` records.

        Args:
            table: Table from which to collect data.
            recs_back: Number of records to step back from present. Defaults
                to 1.
            variable: Variable for which to collect data. Defaults to None (all).

        Returns:
            Time-indexed DataFrame of the requested data.
        """
        return self._format_data(
            *self._query_records(
                table=table,
                mode="most-recent",
                variable=variable,
                limit=recs_back,
                p1=recs_back,
            )
        )

    @staticmethod
    def _format_data(head: dict, records: list[dict]) -> pd.DataFrame:
        """Shape ``dataquery`` records into a DataFrame.

        Returns:
            Time-indexed DataFrame with a RECORD column and one column per
            variable.
        """
        var_list = ["TIMESTAMP", "RECORD"] + [f["name"] for f in head["fields"]]
        data_list = [
            [
                _convert_time_from_logger_format(time_str=record["time"]),
                int(record["no"]),
                *record["vals"],
            ]
            for record in records
        ]
        return pd.DataFrame(data=data_list, columns=var_list).set_index(
            keys="TIMESTAMP"
        )

    # Status

    def clock_check(self) -> dict:
        """Return the logger clock as reported by the ClockCheck command."""
        return self.request("ClockCheck")

    def get_logger_status(self) -> tuple[dict, dict]:
        """Fetch the logger environment summary and status table.

        Returns:
            A two-tuple of ``(summary_table, status_table)`` where both
            elements are plain dicts. ``summary_table`` is the head
            environment block; ``status_table`` maps field names to their
            most-recent values.
        """
        content = self._data_query(table="status", mode="most-recent", p1=1)
        summary_table = content["head"]["environment"]
        fields = [field["name"] for field in content["head"]["fields"]]
        data = content["data"][0]["vals"]
        status_table = dict(zip(fields, data))
        return summary_table, status_table

    # Tables

    def get_table_list(self) -> pd.DataFrame:
        """Get the list of tables available on the logger.

        Returns:
            DataFrame indexed by table name containing available metadata
            columns.
        """
        return self._browse_symbols(uri="dl:")

    def get_table_variable_list(self, table: str) -> pd.DataFrame:
        """Get the list of variables available in a given table.

        Args:
            table: Table for which to return the variables.

        Returns:
            DataFrame indexed by variable name containing available metadata
            columns (units, process, etc.).
        """
        return self._browse_symbols(uri=f"dl:{table}")

    def build_lookup_table(self) -> pd.DataFrame:
        """Build a cross-table variable lookup for all tables on the logger.

        Returns:
            DataFrame indexed by variable name with columns ``units``,
            ``process``, and ``table``.
        """
        df_list = []
        for table in self.get_table_list().index:
            df = self.get_table_variable_list(table=table)
            df["table"] = table
            df_list.append(df)
        return pd.concat(df_list)[["units", "process", "table"]].fillna("")

    def _browse_symbols(self, uri: str) -> pd.DataFrame:
        """Send a ``browsesymbols`` command and return a DataFrame by name."""
        rslt = self.request("browsesymbols", uri=uri)
        return (
            pd.DataFrame(rslt["symbols"])
            .drop(columns="type", errors="ignore")
            .set_index(keys="name")
        )

    # Files

    def list_files(self, source: str) -> pd.DataFrame:
        """List the files available on a logger storage device.

        Args:
            source: Storage source to check. One of ``'CPU'``, ``'CRD'``,
                ``'USR'``.

        Returns:
            DataFrame indexed by filename with columns for file size and
            ``last_write`` timestamp. Returns an empty DataFrame if the source
            contains no files.

        Raises:
            ValueError: If ``source`` is not one of the valid source identifiers.
        """
        drop_list = ["is_dir", "run_now", "run_on_power_up", "read_only", "paused"]
        rslt = self.request("ListFiles", source=source)
        df = pd.DataFrame(rslt["files"])
        if df.empty:
            return df
        df["path"] = df["path"].str.replace(f"{source}/", "", regex=False)
        df["last_write"] = df["last_write"].apply(_convert_time_from_logger_format)
        return (
            df[~df["is_dir"]]
            .drop(drop_list, axis=1)
            .rename({"path": "file"}, axis=1)
            .set_index(keys="file")
        )

    def get_used_space(self, source: str) -> dict:
        """Get the total used space on a logger storage device.

        Args:
            source: Storage source to check. One of ``'CPU'``, ``'CRD'``,
                ``'USR'``.

        Returns:
            Dict with a single key ``'used space on <source> (GB)'`` mapping
            to the total used space in GB, or ``nan`` if the source is empty.

        Raises:
            ValueError: If ``source`` is not one of the valid source identifiers.
        """
        df = self.list_files(source=source)
        used_in_gb = (
            round(df["size"].sum() / 10**9, 2) if not df.empty else float("nan")
        )
        return {f"used space on {source} (GB)": used_in_gb}


def _to_datetime(time: str | dt.datetime) -> dt.datetime:
    """Parse a ``TIME_FORMAT`` string (or pass a datetime through)."""
    if isinstance(time, str):
        return dt.datetime.strptime(time, TIME_FORMAT)
    return time


def _convert_time_to_logger_format(time: str | dt.datetime) -> str:
    """Convert a datetime to the logger's ISO-like timestamp format.

    Args:
        time: Datetime as a string (``TIME_FORMAT``) or ``datetime`` object.

    Returns:
        Timestamp string with the date/time separator replaced by ``'T'``.
    """
    format_str = TIME_FORMAT.replace(" ", "T")
    return dt.datetime.strftime(_to_datetime(time), format_str)


def _convert_time_from_logger_format(time_str: str) -> dt.datetime:
    """Parse a logger timestamp string into a Python datetime.

    Handles both the standard and sub-second (``SECONDARY_TIME_FORMAT``)
    variants.

    Args:
        time_str: Timestamp string as returned by the logger API.

    Returns:
        Parsed ``datetime`` object.

    Raises:
        ValueError: If the string matches neither known format.
    """
    eval_str = time_str.replace("T", " ")
    try:
        return dt.datetime.strptime(eval_str, TIME_FORMAT)
    except ValueError as e:
        try:
            return dt.datetime.strptime(eval_str, SECONDARY_TIME_FORMAT)
        except ValueError:
            raise e from None


def _check_source(source: str) -> None:
    """Validate a storage source identifier.

    Args:
        source: Source string to validate.

    Raises:
        ValueError: If ``source`` is not one of ``VALID_FILE_SOURCES``.
    """
    if source not in VALID_FILE_SOURCES:
        raise ValueError(f"source must be one of {', '.join(VALID_FILE_SOURCES)}")
