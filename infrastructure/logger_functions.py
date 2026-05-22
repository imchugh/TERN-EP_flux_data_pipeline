# -*- coding: utf-8 -*-
"""
Campbell Scientific datalogger HTTP API client.

Provides functions and a thin ``LoggerClient`` wrapper for querying data,
inspecting tables, listing files, and checking logger status via the
Campbell Scientific HTTP API (JSON format).
"""

import datetime as dt
import json
import logging
import pandas as pd
from dataclasses import dataclass
from typing import Any

from domain.constants import DATA_TIME_FORMAT as TIME_FORMAT
from infrastructure.external_io import get

###############################################################################
### BEGIN GLOBALS / CONSTANTS ###
###############################################################################

logger = logging.getLogger(__name__)

SECONDARY_TIME_FORMAT = TIME_FORMAT + '.%f'
ALLOWED_QUERY_MODES = [
    'most-recent', 'date-range', 'since-time', 'since-record', 'backfill'
    ]
VALID_FILE_SOURCES = ['CPU', 'CRD', 'USR']
VALID_FORMATS = ['html', 'json', 'toa5', 'tob1', 'xml']

###############################################################################
### END GLOBALS / CONSTANTS ###
###############################################################################


###############################################################################
### BEGIN CLASSES ###
###############################################################################

@dataclass(slots=True)
class LoggerClient():
    """
    Thin convenience wrapper around the Campbell logger HTTP API functions.

    Binds an IP address so callers only specify query parameters, not the
    address, on each call.
    """

    ip_addr: str


    # -------------------------------------------------------------------------
    def get_table_list(self) -> pd.DataFrame:

        return get_table_list(ip_addr=self.ip_addr)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    def get_table_variable_list(self, table: str) -> pd.DataFrame:

        return get_table_variable_list(ip_addr=self.ip_addr, table=table)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    def get_data_by_date_range(
            self,
            start_date: str | dt.datetime,
            end_date: str | dt.datetime,
            table: str,
            variable: str | None = None,
            ) -> pd.DataFrame:

        return get_data_by_date_range(
            ip_addr=self.ip_addr,
            start_date=start_date,
            end_date=end_date,
            table=table,
            variable=variable,
            )
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    def get_data_since_date(
            self,
            start_date: str | dt.datetime,
            table: str,
            variable: str | None = None,
            ) -> pd.DataFrame:

        return get_data_since_date(
            ip_addr=self.ip_addr,
            start_date=start_date,
            table=table,
            variable=variable,
            )
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    def get_data_n_records_back(
            self,
            table: str,
            recs_back: int = 1,
            variable: str | None = None,
            ) -> pd.DataFrame:

        return get_data_n_records_back(
            ip_addr=self.ip_addr,
            table=table,
            recs_back=recs_back,
            variable=variable,
            )
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    def get_logger_status(self) -> tuple[dict, dict]:

        return get_logger_status(ip_addr=self.ip_addr)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    def list_files(self, source: str) -> pd.DataFrame:

        return list_files(ip_addr=self.ip_addr, source=source)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    def get_used_space(self, source: str) -> dict:

        return get_used_space(ip_addr=self.ip_addr, source=source)
    # -------------------------------------------------------------------------

# -----------------------------------------------------------------------------

###############################################################################
### END CLASSES ###
###############################################################################


###############################################################################
### BEGIN DATA QUERY SECTION ###
###############################################################################

#------------------------------------------------------------------------------
def get_data_by_date_range(
        ip_addr: str,
        start_date: str | dt.datetime,
        end_date: str | dt.datetime,
        table: str,
        variable: str | None = None,
        ) -> pd.DataFrame:
    """Get all data between specified start and end dates.

    Args:
        ip_addr: IP address of the device.
        start_date: Start date.
        end_date: End date.
        table: Table from which to collect data.
        variable: Variable for which to collect data. Defaults to None (all).

    Returns:
        Time-indexed DataFrame of the requested data.
    """

    cmd_substr = build_query_str(
        mode='date-range',
        config_str=(
            f'&p1={_convert_time_to_logger_format(time=start_date)}'
            f'&p2={_convert_time_to_logger_format(time=end_date)}'
            ),
        table=table,
        variable=variable,
        )

    return _format_data(ip_addr=ip_addr, cmd_substr=cmd_substr)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_data_since_date(
        ip_addr: str,
        start_date: str | dt.datetime,
        table: str,
        variable: str | None = None,
        ) -> pd.DataFrame:
    """Get all data after a specified date.

    Args:
        ip_addr: IP address of the device.
        start_date: Start date.
        table: Table from which to collect data.
        variable: Variable for which to collect data. Defaults to None (all).

    Returns:
        Time-indexed DataFrame of the requested data.
    """

    cmd_substr = build_query_str(
        mode='since-time',
        config_str=f'&p1={_convert_time_to_logger_format(time=start_date)}',
        table=table,
        variable=variable,
        )

    return _format_data(ip_addr=ip_addr, cmd_substr=cmd_substr)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_data_n_records_back(
        ip_addr: str,
        table: str,
        recs_back: int = 1,
        variable: str | None = None,
        ) -> pd.DataFrame:
    """Get data starting n records back from the present.

    Args:
        ip_addr: IP address of the device.
        table: Table from which to collect data.
        recs_back: Number of records to step back from present. Defaults to 1.
        variable: Variable for which to collect data. Defaults to None (all).

    Returns:
        Time-indexed DataFrame of the requested data.
    """

    cmd_substr = build_query_str(
        mode='most-recent',
        config_str=f'&p1={recs_back}',
        table=table,
        variable=variable,
        )

    return _format_data(ip_addr=ip_addr, cmd_substr=cmd_substr)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def _format_data(ip_addr: str, cmd_substr: str) -> pd.DataFrame:
    """Execute a data query and shape the result into a DataFrame.

    Args:
        ip_addr: IP address of the device.
        cmd_substr: Query substring to embed in the complete URL.

    Returns:
        Time-indexed DataFrame with a RECORD column and one column per
        variable.
    """

    cmd_str = resolve_url(ip_addr=ip_addr, cmd_substr=cmd_substr)
    content = submit_request(cmd_str=cmd_str)
    init_df = (
        pd.DataFrame(content['head']['fields'])
        .drop(['type', 'settable'], axis=1)
        .set_index(keys='name')
        .fillna('')
        )
    var_list = ['TIMESTAMP', 'RECORD'] + init_df.index.tolist()
    data_list = []
    for record in content['data']:
        time = _convert_time_from_logger_format(time_str=record['time'])
        record_n = int(record['no'])
        data_list.append([time, record_n] + record['vals'])

    logger.debug(
        'data_query_complete',
        extra={'ip_addr': ip_addr, 'n_records': len(data_list)},
        )

    return (
        pd.DataFrame(data=data_list, columns=var_list)
        .set_index(keys='TIMESTAMP')
        )
#------------------------------------------------------------------------------

###############################################################################
### END DATA QUERY SECTION ###
###############################################################################


###############################################################################
### BEGIN STATUS SECTION ###
###############################################################################

#------------------------------------------------------------------------------
def clock_check(ip_addr: str) -> dict:
    """Check the logger clock.

    Args:
        ip_addr: IP address of the logger.

    Returns:
        Dict containing the logger time as reported by the ClockCheck command.
    """

    cmd_str = resolve_url(ip_addr=ip_addr, cmd_substr='ClockCheck')
    return submit_request(cmd_str=cmd_str)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_logger_status(ip_addr: str) -> tuple[dict, dict]:
    """Fetch the logger environment summary and status table.

    Args:
        ip_addr: IP address of the logger.

    Returns:
        A two-tuple of ``(summary_table, status_table)`` where both elements
        are plain dicts. ``summary_table`` is the head environment block;
        ``status_table`` maps field names to their most-recent values.
    """

    cmd_substr = build_query_str(
        mode='most-recent',
        config_str='&p1=1',
        table='status',
        )

    cmd_str = resolve_url(ip_addr=ip_addr, cmd_substr=cmd_substr)
    content = submit_request(cmd_str=cmd_str)
    summary_table = content['head']['environment']
    fields = [field['name'] for field in content['head']['fields']]
    data = content['data'][0]['vals']
    status_table = dict(zip(fields, data))
    return summary_table, status_table
#------------------------------------------------------------------------------

###############################################################################
### END STATUS SECTION ###
###############################################################################


###############################################################################
### BEGIN TABLE QUERY SECTION ###
###############################################################################

#------------------------------------------------------------------------------
def get_table_list(ip_addr: str) -> pd.DataFrame:
    """Get the list of tables available on the logger.

    Args:
        ip_addr: IP address of the device.

    Returns:
        DataFrame indexed by table name containing available metadata columns.
    """

    return _browse_symbols(ip_addr=ip_addr, cmd_substr='browsesymbols&uri=dl:')
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_table_variable_list(ip_addr: str, table: str) -> pd.DataFrame:
    """Get the list of variables available in a given table.

    Args:
        ip_addr: IP address of the device.
        table: Table for which to return the variables.

    Returns:
        DataFrame indexed by variable name containing available metadata
        columns (units, process, etc.).
    """

    return _browse_symbols(
        ip_addr=ip_addr,
        cmd_substr=f'browsesymbols&uri=dl:{table}',
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def build_lookup_table(ip_addr: str) -> pd.DataFrame:
    """Build a cross-table variable lookup for all tables on the logger.

    Iterates every table returned by ``get_table_list`` and concatenates the
    per-table variable metadata into a single DataFrame with a ``table``
    column added.

    Args:
        ip_addr: IP address of the device.

    Returns:
        DataFrame indexed by variable name with columns ``units``, ``process``,
        and ``table``.
    """

    df_list = []
    for table in get_table_list(ip_addr=ip_addr).index:
        df = get_table_variable_list(ip_addr=ip_addr, table=table)
        df['table'] = table
        df_list.append(df)
    return (
        pd.concat(df_list)
        [['units', 'process', 'table']]
        .fillna('')
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def _browse_symbols(ip_addr: str, cmd_substr: str) -> pd.DataFrame:
    """Submit a browsesymbols request and return results as a DataFrame.

    Args:
        ip_addr: IP address of the device.
        cmd_substr: Pre-built browsesymbols command substring.

    Returns:
        DataFrame indexed by symbol name.
    """

    cmd_str = resolve_url(ip_addr=ip_addr, cmd_substr=cmd_substr)
    rslt = submit_request(cmd_str=cmd_str)
    return (
        pd.DataFrame(rslt['symbols'])
        .drop(columns='type', errors='ignore')
        .set_index(keys='name')
        )
#------------------------------------------------------------------------------

###############################################################################
### END TABLE QUERY SECTION ###
###############################################################################


###############################################################################
### BEGIN FILE QUERY SECTION ###
###############################################################################

#------------------------------------------------------------------------------
def list_files(ip_addr: str, source: str) -> pd.DataFrame:
    """List the files available on a logger storage device.

    Args:
        ip_addr: IP address of the device.
        source: Storage source to check. One of ``'CPU'``, ``'CRD'``,
            ``'USR'``.

    Returns:
        DataFrame indexed by filename with columns for file size and
        ``last_write`` timestamp. Returns an empty DataFrame if the source
        contains no files.

    Raises:
        ValueError: If ``source`` is not one of the valid source identifiers.
    """

    drop_list = [
        'is_dir', 'run_now', 'run_on_power_up', 'read_only', 'paused'
        ]
    _check_source(source=source)
    cmd_str = resolve_url(ip_addr=ip_addr, cmd_substr='ListFiles', source=source)
    rslt = submit_request(cmd_str=cmd_str)
    df = pd.DataFrame(rslt['files'])
    if df.empty:
        return df
    df['path'] = df['path'].str.replace(f'{source}/', '', regex=False)
    df['last_write'] = df['last_write'].apply(_convert_time_from_logger_format)
    return (
        df[~df['is_dir']]
        .drop(drop_list, axis=1)
        .rename({'path': 'file'}, axis=1)
        .set_index(keys='file')
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_used_space(ip_addr: str, source: str) -> dict:
    """Get the total used space on a logger storage device.

    Args:
        ip_addr: IP address of the device.
        source: Storage source to check. One of ``'CPU'``, ``'CRD'``,
            ``'USR'``.

    Returns:
        Dict with a single key ``'used space on <source> (GB)'`` mapping to
        the total used space in GB, or ``nan`` if the source is empty.

    Raises:
        ValueError: If ``source`` is not one of the valid source identifiers.
    """

    _check_source(source=source)
    df = list_files(ip_addr=ip_addr, source=source)
    used_in_gb = round(df['size'].sum() / 10**9, 2) if not df.empty else float('nan')
    return {f'used space on {source} (GB)': used_in_gb}
#------------------------------------------------------------------------------

###############################################################################
### END FILE QUERY SECTION ###
###############################################################################


###############################################################################
### BEGIN HELPER FUNCTION SECTION ###
###############################################################################

#------------------------------------------------------------------------------
def submit_request(cmd_str: str, timeout: int = 2) -> dict | list:
    """Submit an HTTP request to the logger and return the parsed JSON response.

    Args:
        cmd_str: Full URL to request.
        timeout: Request timeout in seconds. Defaults to 2.

    Returns:
        Parsed JSON response body (typically a dict).
    """

    logger.debug('logger_request', extra={'url': cmd_str})
    response = get(url=cmd_str, timeout=timeout, stream=True)
    return json.loads(response.content)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def resolve_url(
        ip_addr: str,
        cmd_substr: str,
        out_format: str | None = 'json',
        source: str | None = None,
        ) -> str:
    """Assemble the full HTTP URL for a logger API command.

    Args:
        ip_addr: IP address of the device.
        cmd_substr: Command substring to embed after ``?command=``.
        out_format: Response format. One of ``VALID_FORMATS`` or ``None`` to
            omit the format parameter. Defaults to ``'json'``.
        source: Storage source prefix to insert before the command path.
            Defaults to None (omitted).

    Returns:
        Fully assembled URL string.

    Raises:
        ValueError: If ``out_format`` or ``source`` is not a recognised value.
    """

    addr_syntax = f'http://{ip_addr}/'
    command_syntax = f'?command={cmd_substr}'

    source_syntax = ''
    if source is not None:
        _check_source(source=source)
        source_syntax = f'{source}/'

    format_syntax = ''
    if out_format is not None:
        if out_format not in VALID_FORMATS:
            raise ValueError(
                f'out_format must be one of {", ".join(VALID_FORMATS)}'
                )
        format_syntax = f'&format={out_format}'

    return ''.join([addr_syntax, source_syntax, command_syntax, format_syntax])
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def build_query_str(
        table: str,
        mode: str,
        config_str: str,
        variable: str | None = None,
        ) -> str:
    """Build a dataquery command substring for the logger API.

    Args:
        table: Logger table to query.
        mode: Query mode. One of ``ALLOWED_QUERY_MODES``.
        config_str: Mode-specific parameter string (e.g. ``'&p1=1'``).
        variable: Optional variable name to append to the table URI.
            Defaults to None (all variables).

    Returns:
        Command substring suitable for passing to ``resolve_url``.
    """

    variable_syntax = '' if variable is None else f'.{variable}'
    return f'dataquery&uri=dl:{table}{variable_syntax}&mode={mode}{config_str}'
#------------------------------------------------------------------------------

###############################################################################
### END HELPER FUNCTION SECTION ###
###############################################################################


###############################################################################
### BEGIN PRIVATE FUNCTION SECTION ###
###############################################################################

#------------------------------------------------------------------------------
def _convert_time_to_logger_format(time: str | dt.datetime) -> str:
    """Convert a datetime to the logger's ISO-like timestamp format.

    Args:
        time: Datetime as a string (``TIME_FORMAT``) or ``datetime`` object.

    Returns:
        Timestamp string with the date/time separator replaced by ``'T'``.
    """

    if isinstance(time, str):
        time = dt.datetime.strptime(time, TIME_FORMAT)
    format_str = TIME_FORMAT.replace(' ', 'T')
    return dt.datetime.strftime(time, format_str)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
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

    eval_str = time_str.replace('T', ' ')
    try:
        return dt.datetime.strptime(eval_str, TIME_FORMAT)
    except ValueError as e:
        try:
            return dt.datetime.strptime(eval_str, SECONDARY_TIME_FORMAT)
        except ValueError:
            raise e
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def _check_source(source: str) -> None:
    """Validate a storage source identifier.

    Args:
        source: Source string to validate.

    Raises:
        ValueError: If ``source`` is not one of ``VALID_FILE_SOURCES``.
    """

    if source not in VALID_FILE_SOURCES:
        raise ValueError(
            f'source must be one of {", ".join(VALID_FILE_SOURCES)}'
            )
#------------------------------------------------------------------------------

###############################################################################
### END PRIVATE FUNCTION SECTION ###
###############################################################################
