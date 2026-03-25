# -*- coding: utf-8 -*-
"""
Created on Tue Aug 27 15:46:11 2024

@author: jcutern-imchugh
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

import pathlib

from infrastructure import file_io

###############################################################################
### END IMPORTS ###
###############################################################################



###############################################################################
### BEGIN INITS ###
###############################################################################

CONFIG_PATH = pathlib.Path(__file__).parents[1] / 'configs'
CONFIG_FILE = 'paths.yml'
CONFIGS = file_io.read_yml(file_path=CONFIG_PATH / CONFIG_FILE)
LOCAL_PATHS = CONFIGS['local']
REMOTE_PATHS = CONFIGS['remote']
REMOTE_ALIAS_DICT = {
    'AliceSpringsMulga': 'AliceMulga', 'Longreach': 'MitchellGrassRangeland',
    }
PLACEHOLDER = '<site>'

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN CONFIGURATION FILE FUNCTIONS ###
###############################################################################

#------------------------------------------------------------------------------
def list_project_sites() -> list:
    """List the available sites in the raw data directory"""
    
    return sorted(
        (site_dir.name for site_dir in
            pathlib.Path(get_local_resource_path(
                resource='raw_data', as_str=True
                )
                .replace(PLACEHOLDER, '')
                )
            .glob('*')
            )
        )
#------------------------------------------------------------------------------

# #------------------------------------------------------------------------------
# def list_internal_config_files() -> list:
#     """List the available internal configuration files incl. absolute path."""

#     return [
#         file for file in
#         (pathlib.Path(__file__).resolve().parents[1] / 'configs').glob('*')
#         if file.suffix in ALLOWED_CONFIG_TYPES
#         ]
# #------------------------------------------------------------------------------

# #------------------------------------------------------------------------------
# def list_internal_config_names() -> list:
#     """List the available internal configurations"""

#     return [file.stem for file in list_internal_config_files()]
# #------------------------------------------------------------------------------

# #------------------------------------------------------------------------------
# def get_internal_config_path(config_name: str) -> pathlib.Path:
#     """Get the path to an internal configuration file"""
    
#     files_dict = {file.stem: file for file in list_internal_config_files()}
#     return files_dict[config_name]
# #------------------------------------------------------------------------------

# #------------------------------------------------------------------------------
# def get_internal_configs(config_name: str) -> dict:
#     """Get the content of an internal configuration file"""

#     path = get_internal_config_path(config_name=config_name)
#     with open(path) as f:
#         if path.suffix == '.txt':
#             return f.read()
#         if path.suffix == '.yml':
#             return yaml.safe_load(stream=f)
#         if path.suffix == '.csv':
#             return pd.read_csv(f).to_dict()
# #------------------------------------------------------------------------------

# #------------------------------------------------------------------------------
# def get_local_configs(config_stream: str) -> dict:
#     """Get the content of a local config file (external to code project"""

#     return read_yaml_file(
#         get_path(
#             location='local', resource='configs', stream=config_stream,
#             )
#         )
# #------------------------------------------------------------------------------

###############################################################################
### END CONFIGURATION FILE FUNCTIONS ###
###############################################################################



###############################################################################
### BEGIN LOCAL RESOURCE FUNCTIONS ###
###############################################################################

#------------------------------------------------------------------------------
def list_local_resources() -> list:
    """List the local resources defined in the .yml file."""

    return list(LOCAL_PATHS.keys())
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def list_local_streams(resource: str) -> list:
    """
    List the local streams defined in the .yml file.

    Args:
        resource: resource for which to return streams.

    Returns:
        List of local streams.

    """

    return list(LOCAL_PATHS[resource]['stream'].keys())
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_local_resource_path(
        resource: str, **kwargs: dict
        ) -> pathlib.Path | str:
    """
    Get the path to the local resource.

    Args:
        resource: the local resource for which to return the path.
        **kwargs: additional keyword args to pass to get_path function.

    Returns:
        Path to local resource.

    """

    return get_path(location='local', resource=resource, **kwargs)
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_local_stream_path(
        resource: str, stream: str, **kwargs: dict
        ) -> pathlib.Path | str:
    """
    Get the path to the local resource stream.

    Args:
        resource: the local resource for which to return the path.
        stream: resource stream for which to return the path.
        **kwargs: additional keyword args to pass to get_path method.

    Returns:
        Path to local resource stream.

    """

    return get_path(
        location='local', resource=resource, stream=stream, **kwargs
        )
#------------------------------------------------------------------------------

# #------------------------------------------------------------------------------
# def get_local_config_file(config_stream: str, **kwargs: dict) -> dict:

#     return read_yaml_file(
#         get_path(
#             location='local', resource='configs', stream=config_stream,
#             **kwargs
#             )
#         )
# #------------------------------------------------------------------------------

# #------------------------------------------------------------------------------
# def get_other_config_file(file_path):

#     return read_yaml_file(file=file_path)
# #------------------------------------------------------------------------------

###############################################################################
### END LOCAL RESOURCE FUNCTIONS ###
###############################################################################



###############################################################################
### BEGIN REMOTE DATA FUNCTIONS ###
###############################################################################

#------------------------------------------------------------------------------
def list_remote_resources() -> list:
    """
    List the available remote resources defined in the .yml file.

    Returns:
        List of remote resources.

    """

    return list(LOCAL_PATHS.keys())
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def list_remote_streams(resource: str) -> pathlib.Path | str:
    """
    List the available remote streams defined in the .yml file.

    Args:
        resource: the remote resource for which to return the streams.

    Returns:
        List of remote resource streams.

    """

    return list(LOCAL_PATHS[resource]['stream'].keys())
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def get_remote_resource_path(
        resource: str, **kwargs: dict
        ) -> pathlib.Path | str:
    """
    Get the path to the remote resource.

    Args:
        resource: the remote resource for which to return the path.
        **kwargs: additional keyword args to pass to get_path method.

    Returns:
        Path of remote resource.

    """

    return get_path(location='remote', resource=resource, **kwargs)
#------------------------------------------------------------------------------

#--------------------------------------------------------------------------
def get_remote_stream_path(
        resource: str, stream: str, **kwargs: dict
        ) -> pathlib.Path | str:
    """
    Get the path to the remote resource stream.

    Args:
        resource: the remote resource for which to return the path.
        stream: resource stream for which to return the path.
        **kwargs: additional keyword args to pass to get_path method.

    Returns:
        Path to remote resource stream.

    """

    return get_path(
        location='remote', resource=resource, stream=stream, **kwargs
        )
#--------------------------------------------------------------------------

###############################################################################
### END REMOTE DATA FUNCTIONS ###
###############################################################################



###############################################################################
### BEGIN GENERIC DATA FUNCTIONS ###
###############################################################################

#------------------------------------------------------------------------------
def get_path(
        location: str, resource: str, stream: str=None,
        site: str=None, subdirs: list=[], file_name: str=None,
        check_exists: bool=False, as_str: bool=False
        ):
    """
    Get the path to a resource or stream.

    Args:
        location: local or remote.
        resource: resource to select.
        stream (optional): stream path to extract. Defaults to None.
        site (optional): name of site. Defaults to None.
        subdirs (optional): list of subdirectories to append. Defaults to [].
        file_name (optional): file name to append. Defaults to None.
        check_exists (optional): whether to check if path exists. Defaults to False.
        as_str (optional): whether to return path as str. Defaults to False.

    Raises:
        KeyError: raised (and caught) if passed site doesn't have a remote alias.
        RuntimeError: raised if subdirectories or file names are passed but the path is to a file.
        FileNotFoundError: raised if check_exists=True and file does not exist.

    Returns:
        Path to resource / stream.

    """

    # Select local or remote configs
    if location == 'local':
        configs = LOCAL_PATHS
    elif location == 'remote':
        configs = REMOTE_PATHS
    else:
        raise KeyError('Allowed locations are "local" and "remote"!')

    # Create an empty path
    path = pathlib.Path()

    # get the configs for the specific resource
    resource_configs = configs[resource]
    if len(resource_configs['base_path']) > 0:
        path = path / resource_configs['base_path']

    # Add the resource stream to the path
    if not stream is None:
        path = path / resource_configs['stream'][stream]

    # Check if resolves to a file; if so, subdirs and file_name cannot be
    # sensibly appended -> raise
    if len(path.suffix) > 0:
        if len(subdirs) > 0:
            raise RuntimeError(
                f'Current path resolves to a file ({path.name}); no '
                'subdirectory append allowed!'
                )
        if not file_name is None:
            raise RuntimeError(
                f'Current path resolves to a file ({path.name}); no '
                'file name append allowed!'
                )

    # Add subdirectories
    subdirs = list(subdirs)
    if not file_name is None:
        subdirs.append(file_name)
    for element in subdirs:
        path = path / element

    # Fill site placeholder (and get remote alias if applicable)
    if not site is None:
        if location == 'remote':
            try:
                site = REMOTE_ALIAS_DICT[site]
            except KeyError:
                pass
        path = pathlib.Path(str(path).replace(PLACEHOLDER, site))

    # Check if the path exists
    if check_exists:
        if not path.exists():
            raise FileNotFoundError('No such path!')

    # Return
    if as_str:
        return str(path)
    return path
#------------------------------------------------------------------------------

###############################################################################
### END GENERIC DATA FUNCTIONS ###
###############################################################################
