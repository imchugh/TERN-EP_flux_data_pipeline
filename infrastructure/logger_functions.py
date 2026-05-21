# -*- coding: utf-8 -*-
"""
Created on Fri Mar  1 16:09:49 2024

Todo:
    - Add the substring to raised exceptions so we can see if the request is mangled



"""

import datetime as dt
import json
import numpy as np
import pandas as pd
from dataclasses import dataclass

from domain.constants import DATA_TIME_FORMAT as TIME_FORMAT
from infrastructure.external_io import get

###############################################################################
### BEGIN GLOBALS / CONSTANTS ###
###############################################################################

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
    Thin convenience wrapper around Campbell infrastructure functions.
    """
    
    ip_addr: str
    

    # -------------------------------------------------------------------------
    def get_table_list(
            self,
            list_only: bool = True,
            ) -> list[str] | pd.DataFrame:

        return get_table_list(
            ip_addr=self.ip_addr,
            list_only=list_only,
        )
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    def get_table_variable_list(
            self,
            table: str,
            list_only: bool = True,
            ) -> list[str] | pd.DataFrame:

        return get_table_variable_list(
            ip_addr=self.ip_addr,
            table=table,
            list_only=list_only,
            )
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
    def get_logger_status(self) -> dict:

        return get_logger_status(
            ip_addr=self.ip_addr,
            )
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    def list_files(
            self,
            source: str,
            ) -> pd.DataFrame:

        return list_files(
            ip_addr=self.ip_addr,
            source=source,
           )
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    def get_used_space(
            self,
            source: str,
            ) -> dict:

        return get_used_space(
            ip_addr=self.ip_addr,
            source=source,
            )
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
        ip_addr: str, start_date: str | dt.datetime,
        end_date: str | dt.datetime, table: str, variable: str=None
        ) -> pd.DataFrame:
    """Get all of the data between specified start and end dates.

    Args:
        ip_addr: IP address of the device.
        start_date: start date.
        end_date: end date.
        table: table from which to collect data.
        variable (optional): the variable for which to collect data. Defaults to None.

    Returns:
        The data.

    """

    # Build the query substring
    cmd_substr = build_query_str(
        mode='date-range',
        config_str=(
            f'&p1={_convert_time_to_logger_format(time=start_date)}'
            f'&p2={_convert_time_to_logger_format(time=end_date)}'
            ),
        table=table,
        variable=variable
        )

    # Return data
    return _format_data(
        ip_addr=ip_addr,
        cmd_substr=cmd_substr
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_data_since_date(
        ip_addr: str, start_date: str | dt.datetime, table: str,
        variable: str=None
        ) -> pd.DataFrame:
    """Get all of the data after specified date.

    Args:
        ip_addr: IP address of the device.
        start_date: start date.
        table: table from which to collect data.
        variable (optional): the variable for which to collect data. Defaults to None.

    Returns:
        The data.

    """

    # Build the query substring
    cmd_substr = build_query_str(
        mode='since-time',
        config_str = (
            f'&p1={_convert_time_to_logger_format(time=start_date)}'
            ),
        table=table,
        variable=variable
        )

    # Return data
    return _format_data(
        ip_addr=ip_addr,
        cmd_substr=cmd_substr
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_data_n_records_back(
        ip_addr: str, table: str, recs_back: int=1, variable: str=None
        ) -> pd.DataFrame:
    """Get data starting n records back from present.

    Args:
        ip_addr: IP address of the device.
        table: table from which to collect data.
        recs_back: number of records to step back from present. Defaults to 1.
        variable (optional): the variable for which to collect data. Defaults to None.

    Returns:
        The data.

    """

    # Build the query substring
    cmd_substr = build_query_str(
        mode='most-recent',
        config_str=f'&p1={recs_back}',
        table=table,
        variable=variable
        )

    # Return data
    return _format_data(
        ip_addr=ip_addr,
        cmd_substr=cmd_substr
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def _format_data(ip_addr: str, cmd_substr: str) -> pd.DataFrame:
    """Execute the command and shape the resulting data.

    Args:
        ip_addr: IP address of the device.
        cmd_substr: the substring to be embedded in the complete command string.

    Returns:
        The data.

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
    return (
        pd.DataFrame(
            data=data_list, columns=var_list
            )
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
        Logger time.

    """

    cmd_str = resolve_url(ip_addr=ip_addr, cmd_substr='ClockCheck')
    return submit_request(cmd_str=cmd_str)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_logger_status(ip_addr: str) -> tuple[dict, dict]:

    # Build the query substring
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
        list_only (optional): whether to return just a list of names, or all info. Default is True.
    Returns:
        The tables.

    """
    
    return _browse_symbols(
        ip_addr=ip_addr, 
        cmd_substr='browsesymbols&uri=dl:', 
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_table_variable_list(ip_addr: str, table: str) -> pd.DataFrame:
    """Get the list of variables available in a given table.

    Args:
        ip_addr: IP address of the device.
        table: the table for which to return the variables.
        list_only (optional): whether to return just a list of variables, or all info.
    Returns:
        The variables.

    """
    
    return _browse_symbols(
        ip_addr=ip_addr, 
        cmd_substr=f'browsesymbols&uri=dl:{table}', 
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def _browse_symbols(ip_addr: str, cmd_substr: str) -> pd.DataFrame:
    
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
    """List the available files.

    Args:
        ip_addr: IP address of the device.
        source: the source to check (CPU, CRD or USR).

    Raises:
        FileNotFoundError: raised if the source is invalid.

    Returns:
        Files, including size and last write date and time.

    """

    drop_list = [
        'is_dir', 'run_now', 'run_on_power_up', 'read_only', 'paused'
        ]
    _check_source(source=source)
    cmd_str = resolve_url(
        ip_addr=ip_addr,
        cmd_substr='ListFiles',
        source=source
        )
    rslt = submit_request(cmd_str=cmd_str)
    df = pd.DataFrame(rslt['files'])
    if len(df) == 0:
        return df
    df.path = df.path.str.replace(f'{source}/', '')
    df.last_write = df.last_write.apply(_convert_time_from_logger_format)
    return (
        df[~df.is_dir]
        .drop(drop_list, axis=1)
        .rename({'path': 'file'}, axis=1)
        .set_index(keys='file')
        )
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_used_space(ip_addr: str, source: str) -> str:
    """
    Get the total used space in GB.

    Args:
        ip_addr: IP address of the device.
        source: the source to check (CPU, CRD or USR).

    Returns:
        Space used in GB.

    """

    _check_source(source=source)
    df = list_files(ip_addr=ip_addr, source=source)
    if len(df) != 0:
        used_in_gb = round(df["size"].sum()/10**9, 2)
    else:
        used_in_gb = np.nan
    return {f'used space on {source} (GB)': used_in_gb}
#------------------------------------------------------------------------------

# def get_newest_file(ip_addr: str, source: str, file_ext: str=None) -> str:

#     cmd_str = resolve_url(
#         ip_addr=ip_addr,
#         cmd_substr='NewestFile',
#         source=source
#         )

#     cmd_str = f'http://{ip_addr}/?command=NewestFile&expr={source}:*.{file_ext}'
#     rslt = submit_request(cmd_str=cmd_str)
#     breakpoint()


###############################################################################
### END FILE QUERY SECTION ###
###############################################################################



###############################################################################
### BEGIN HELPER FUNCTION SECTION ###
###############################################################################

#------------------------------------------------------------------------------
def submit_request(cmd_str: str, timeout: int=2) -> bytes:

    response = get(
        url=cmd_str,
        timeout=timeout,
        stream=True,
        )

    return json.loads(response.content)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def resolve_url(ip_addr, cmd_substr, out_format='json', source=None):

    addr_syntax = f'http://{ip_addr}/'
    command_syntax = f'?command={cmd_substr}'

    source_syntax = ''
    if not source is None:
        _check_source(source=source)
        source_syntax = f'{source}/'

    format_syntax = ''
    if not out_format is None:
        if not out_format in VALID_FORMATS:
            raise KeyError(
                f'out_format must be one of {", ".join(VALID_FORMATS)}'
                )
        format_syntax = f'&format={out_format}'

    return ''.join([addr_syntax, source_syntax, command_syntax, format_syntax])
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def build_query_str(
        table: str, mode: str, config_str: str, variable=None
        ) -> str:

    variable_syntax = ''
    if not variable is None:
        variable_syntax = f'.{variable}'

    return f'dataquery&uri=dl:{table}{variable_syntax}&mode={mode}{config_str}'
#------------------------------------------------------------------------------

###############################################################################
### END HELPER FUNCTION SECTION ###
###############################################################################

def build_lookup_table(ip_addr):

    df_list = []
    for table in get_table_list(ip_addr=ip_addr):
        df = get_table_variable_list(ip_addr=ip_addr, table=table)
        df['table'] = table
        df_list.append(df)
    return (
        pd.concat(df_list)
        [['units', 'process', 'table']]
        .fillna('')
        )

###############################################################################
### BEGIN PRIVATE FUNCTION SECTION ###
###############################################################################

def _convert_time_to_logger_format(time):

    if isinstance(time, str):
        time = dt.datetime.strptime(time, TIME_FORMAT)
    format_str = TIME_FORMAT.replace(' ', 'T')
    return dt.datetime.strftime(time, format_str)

def _convert_time_from_logger_format(time_str):

    eval_str = time_str.replace('T', ' ')
    try:
        return dt.datetime.strptime(eval_str, TIME_FORMAT)
    except ValueError as e:
        try:
            return dt.datetime.strptime(eval_str, SECONDARY_TIME_FORMAT)
        except ValueError:
            raise e

def _check_source(source):

    if not source in VALID_FILE_SOURCES:
        raise KeyError(
            f'source must be one of {", ".join(VALID_FILE_SOURCES)}'
            )

###############################################################################
### END PRIVATE FUNCTION SECTION ###
###############################################################################
