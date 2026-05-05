# -*- coding: utf-8 -*-
"""
Created on Mon Sep 12 12:34:58 2022

@author: jcutern-imchugh

This script fetches flux station details from TERN's SPARQL endpoint
"""

###############################################################################
### BEGIN IMPORTS ###
###############################################################################

from datetime import datetime

# -----------------------------------------------------------------------------

from infrastructure import paths, external_io, file_io
from infrastructure.geospatial import get_timezone, get_UTC_offset
from services.metadata import dereference
from services import config_loader

###############################################################################
### END IMPORTS ###
###############################################################################


###############################################################################
### BEGIN INITS ###
###############################################################################

ALIAS_DICT = {
    'Aqueduct Snow Gum': 'SnowGum',
    'ArcturusEmerald': 'Emerald',
    'Calperum Chowilla': 'Calperum',
    'Dargo High Plains': 'Dargo',
    'Longreach Mitchell Grass Rangeland': 'Longreach',
    'Nimmo High Plains': 'Nimmo',
    'Samford Ecological Research Facility': 'Samford',
    'Silver Plain': 'SilverPlains',
    'Tumbarumba2': 'Tumbarumba',
    'Wellington Research Station Flux Tower': 'Wellington',
    'Wombat Forest 2':'WombatForest'
}

_SPARQL_CACHE = None
_CREDS_CACHE = None
_METADATA_CACHE = None

###############################################################################
### END INITS ###
###############################################################################


###############################################################################
### BEGIN CLASSES ###
###############################################################################

# -----------------------------------------------------------------------------
class SiteMetadata(dict):
    """
    Lightweight metadata container.

    Provides:
    - automatic type formatting
    - attribute-style access
    - dictionary behaviour
    """

    DATA_DTYPES = {
        'id': str,
        'fluxnet_id': str,
        'date_commissioned': datetime,
        'date_decommissioned': datetime,
        'latitude': float,
        'longitude': float,
        'elevation': float,
        'time_step': int,
        'freq_hz': int,
        'soil': str,
        'tower_height': float,
        'vegetation': str,
        'canopy_height': float,
        'time_zone': str,
        'UTC_offset': float,
    }

    # -------------------------------------------------------------------------

    def __init__(self, data: dict):

        formatted = {}

        for key, value in data.items():

            if value in (None, "", "nan"):
                formatted[key] = None
                continue

            dtype = self.DATA_DTYPES.get(key)

            try:

                if dtype is float:
                    formatted[key] = float(value)

                elif dtype is int:
                    formatted[key] = int(float(value))

                elif dtype is str:
                    formatted[key] = str(value)

                elif dtype is datetime:
                    formatted[key] = datetime.fromisoformat(value)

                else:
                    formatted[key] = value

            except Exception:
                formatted[key] = value

        super().__init__(formatted)
    # -------------------------------------------------------------------------
    
    # -------------------------------------------------------------------------    
    
    def __getattr__(self, key):
        
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)
    # -------------------------------------------------------------------------
    
    # -------------------------------------------------------------------------
    
    def __setattr__(self, key, value):
        
        raise AttributeError("SiteMetadata is immutable")
    # -------------------------------------------------------------------------        

    # -------------------------------------------------------------------------
    def __dir__(self):
        
        return sorted(set(super().__dir__()) | set(self.keys()))
    # -------------------------------------------------------------------------    

    # -------------------------------------------------------------------------
    def __repr__(self):
        
        label = self.get("site_name", None)
        if label:
            return f"<SiteMetadata {label}>"
        return f"<SiteMetadata {self.get('site_name','unknown')}>"
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    
    def to_yaml_dict(self):

        return {
            k: (v.isoformat() if isinstance(v, datetime) else v)
            for k, v in self.items()
            }
    # -------------------------------------------------------------------------    

# -----------------------------------------------------------------------------

###############################################################################
### END CLASSES ###
###############################################################################


###############################################################################
### BEGIN FUNCTIONS ###
###############################################################################
   
# -----------------------------------------------------------------------------
# QUERY LOAD / EXECUTION UTILITIES
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def _get_CREDS_CACHE() -> dict:
    """
    Get credentials (or return cached).

    Returns:
        credentials.

    """
    
    global _CREDS_CACHE

    if _CREDS_CACHE is None:
        cred_path = paths.get_local_stream_path(
            resource='configs', 
            stream='secrets'
            )
        _CREDS_CACHE = (
            config_loader.load_config_file(file=cred_path)
            ['SITE_DETAILS']
            )

    return _CREDS_CACHE
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def load_sparql_configs() -> dict:
    """
    Load the SPARQL queries from YAML if not already loaded.
    Returns a dictionary with keys for each query.
    """
    
    global _SPARQL_CACHE
    if _SPARQL_CACHE is None:
        _SPARQL_CACHE = (
            config_loader.load_config_file_from_name(
                name='sparql_query_configs'
                )
            )
    return _SPARQL_CACHE
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def available_sparql_queries() -> list[str]:
    """Return a list of available SPARQL query keywords."""
    
    return list(load_sparql_configs()['queries'].keys())
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_sparql_query(query_key: str) -> str:
    """
    Return the query string for a given keyword.
    """
    
    queries = load_sparql_configs()['queries']

    try:
        return queries[query_key]
    except KeyError:
        raise ValueError(
            f"Query '{query_key}' not found. "
            f"Available queries: {list(queries)}"
        )
# -----------------------------------------------------------------------------        

# -----------------------------------------------------------------------------
        
def run_query(query_key: str) -> dict:
    """
    

    Args:
        query_key: query label in yml file (see available_sparqle_queries for a list).

    Returns:
        json bindings.

    """

    # Get creds
    creds = _get_CREDS_CACHE()

    # Load the query config strings
    configs = load_sparql_configs()
        
    # Do the query
    rslt = external_io.post(
        configs['sparql_endpoint'],
        data=configs['queries'][query_key],
        headers=configs['query_headers'],
        auth=(creds['USERNAME'], creds['PASSWORD']),
        ).json()  
    
    return rslt.get("results", {}).get("bindings", [])
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def parse_sparql_bindings(bindings: list[dict]) -> list[dict]:
    """
    Convert SPARQL JSON bindings into a list of simple dictionaries.
    """
    
    return [
        {key: val['value'] for key, val in row.items()}
        for row in bindings
    ]
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
# DOMAIN QUERIES
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_flux_tower_predicates_from_rdf() -> dict:
    """
    Get the UIDs of the RDF graph predicates for flux towers.

    Returns:
        dictionary mapping common names (keys) to UIDs (values).

    """

    rows = parse_sparql_bindings(
        run_query("list_predicates")
        )

    return {
        row["predicate"].split("/")[-1]: row["predicate"]
        for row in rows
    }
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_flux_tower_attrs_from_rdf() -> dict:
    """
    Get the UIDs of the RDF graph nested attrs for flux towers.

    Args:
        do_format (optional): return the data as a type-formatted and
        validated site-indexed metadata dataframe. Defaults to False.

    Returns:
        dictionary mapping common names (keys) to UIDs (values).

    """

    bindings = run_query(query_key='get_attributes')
    uuid_list = [b["attr_uuid"]["value"] for b in bindings]
    return {
        value: key for key, value in
        dereference.dereference_labels(uris=uuid_list).items()
        }
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_flux_tower_geometry_from_rdf(
        format_site_names: bool=True
        ) -> dict[str, dict]:
    """
    Get lat / long / elevation nested attributes.

    Args:
        format_site_names (optional): return the data as a type-formatted and
        validated site-indexed metadata dataframe. Defaults to True.

    Returns:
        dict with site name keys and geo info dict as value.

    """

    rows = parse_sparql_bindings(run_query("get_geometry"))

    rslt = {}

    for row in rows:

        site = row["label"]

        if format_site_names:
            site = convert_site_label(site)

        rslt[site] = {
            "latitude": 
                float(row.get("latitude")) if row.get("latitude") else None,
            "longitude": 
                float(row.get("longitude")) if row.get("longitude") else None,
            "elevation": 
                float(row.get("elevation")) if row.get("elevation") else None,
                }

    return rslt
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_flux_tower_fields_from_rdf(
    query: str = 'operational', 
    format_site_names: bool=True, 
    current_only: bool=True,
    add_tz_vars=True,
    ) -> dict:
    """
    Get the values for the operationally-required global metadata fields from
    the RDF graph.

    Args:
        fields (TYPE, optional): DESCRIPTION. Defaults to 'operational'.

    Returns:
        data: type-formatted and validated site-indexed metadata dataframe.

    """
    
    # Set query
    mode = 'get_operational'
    if query == 'extended':
        mode = 'get_extended'

    # Query and extract the data
    rows = parse_sparql_bindings(run_query(query_key=mode))
       
    rslt = {}
    
    # Iterate over results
    for attrs in rows:
        
        # Skip decommissioned sites if current_only = True
        if current_only and attrs.get("date_decommissioned"):
            continue
        
        # Rewrite labels to EP and DSA vocabs
        site = attrs['label']
        if format_site_names:
            site = convert_site_label(label=site)
        attrs['site_name'] = site
        attrs['dsa_label'] = attrs.pop('label')
        
        # Generate time-based variables
        if add_tz_vars:
            tz = {'time_zone': None, 'UTC_offset': None}
            try:
                tz['time_zone'] = get_timezone(
                    lat=float(attrs['latitude']),
                    lon=float(attrs['longitude'])
                    )
                tz['UTC_offset'] = get_UTC_offset(tz_name=tz['time_zone'])
            except KeyError:
                pass
            attrs.update(tz)
        rslt[site] = attrs
        
    return {site: rslt[site] for site in sorted(rslt)}
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def get_flux_tower_fields_from_source(source: str='yml') -> dict:
    """
    Convenience wrapper for user-selection of metadata source (yml or rdf).

    Args:
        source (str, optional): source identifier. Defaults to 'yml'.

    Raises:
        TypeError: raised if source is not recognised.

    Returns:
        dict containing all site info.

    """
    
    if source == 'yml':
        return config_loader.load_config_file_from_name('global_metadata')
    if source == 'rdf':
        return get_flux_tower_fields_from_rdf()
    raise TypeError(f'Source {source} not recognised!')
# -----------------------------------------------------------------------------    

# -----------------------------------------------------------------------------
    
def write_flux_tower_fields_config(overwrite: bool=False) -> None:
    """
    Write data from rdf graph to local yml file.

    Args:
        overwrite (bool, optional): overwrite existing file if True. 
        Defaults to False.

    Raises:
        FileExistsError: raised if file exists and overwrite=False.

    Returns:
        None.

    """
    
    rslt = get_flux_tower_fields_from_rdf(query='operational')
    file_path = config_loader.CONFIG_PATH / 'global_metadata.yml'
    if not overwrite:
        if file_path.exists():
            raise FileExistsError('File already exists!')
    file_io.write_yml_file(file_path=file_path, data=rslt)
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
   
def get_network_metadata() -> dict[str, SiteMetadata]:
    """
    Load the metadata from the yml file (or return cached).

    Returns:
        the metadata for all sites.

    """

    global _METADATA_CACHE

    if _METADATA_CACHE is None:
        fields = get_flux_tower_fields_from_source()
        _METADATA_CACHE = {
            key: SiteMetadata(value)
            for key, value in fields.items()
        }

    return _METADATA_CACHE
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------
def get_site_metadata(site: str) -> SiteMetadata:
    """
    Load the site metadata from the yml file (or return cached).

    Args:
        site: name of site.

    Returns:
        the metadata for the site.

    """

    metadata = get_network_metadata()
    return metadata[site]
# -----------------------------------------------------------------------------

# -------------------------------------------------------------------------------
# UTILITY FUNCTIONS
# -------------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def convert_site_label(label: str) -> str:
    """
    Drop ' Flux Station' and convert name alias.

    Args:
        label: original site label.

    Returns:
        converted site label.

    """
    
    label_clean = label.replace(' Flux Station', '')
    return ALIAS_DICT.get(label_clean, label_clean).replace(' ', '')
# -----------------------------------------------------------------------------

# -----------------------------------------------------------------------------

def format_canopy_height(meta: dict) -> dict:
    """
    Unused at present - if it is formatted to float, it will need to have a single 
    value.

    Args:
        meta: metadata?

    Returns:
        mutated dict.

    """
    
    try:
        meta['canopy_height'] = float(meta['canopy_height'])
    except (KeyError, TypeError, ValueError):
        pass
    return meta
# -----------------------------------------------------------------------------

###############################################################################
### END FUNCTIONS ###
###############################################################################
