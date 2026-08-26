"""Fetch flux station details from TERN's SPARQL endpoint."""

from infrastructure import external_io, file_io, paths
from infrastructure.datetime_utils import get_timezone, get_UTC_offset
from services import config_loader
from services.metadata.tern import rdf_label_resolver

ALIAS_DICT = {
    "Aqueduct Snow Gum": "SnowGum",
    "ArcturusEmerald": "Emerald",
    "Calperum Chowilla": "Calperum",
    "Dargo High Plains": "Dargo",
    "Longreach Mitchell Grass Rangeland": "Longreach",
    "Nimmo High Plains": "Nimmo",
    "Samford Ecological Research Facility": "Samford",
    "Silver Plain": "SilverPlains",
    "Tumbarumba 2": "Tumbarumba",
    "Wellington Research Station Flux Tower": "Wellington",
    "Wombat Forest 2": "WombatForest",
}

_SPARQL_CACHE = None
_CREDS_CACHE = None


# QUERY LOAD / EXECUTION UTILITIES


def _get_CREDS_CACHE() -> dict:
    """Get credentials (or return cached).

    Returns:
        credentials.

    """
    global _CREDS_CACHE

    if _CREDS_CACHE is None:
        cred_path = paths.get_local_stream_path(resource="configs", stream="secrets")
        _CREDS_CACHE = config_loader.load_config_file(file=cred_path)["SITE_DETAILS"]

    return _CREDS_CACHE


def load_sparql_configs() -> dict:
    """Load the SPARQL queries from YAML if not already loaded.

    Returns:
        Dict with keys for each query.
    """
    global _SPARQL_CACHE
    if _SPARQL_CACHE is None:
        _SPARQL_CACHE = config_loader.load_config_file_from_name(
            name="sparql_query_configs"
        )
    return _SPARQL_CACHE


def available_sparql_queries() -> list[str]:
    """Return a list of available SPARQL query keywords."""
    return list(load_sparql_configs()["queries"].keys())


def get_sparql_query(query_key: str) -> str:
    """Return the query string for a given keyword."""
    queries = load_sparql_configs()["queries"]

    try:
        return queries[query_key]
    except KeyError:
        raise ValueError(
            f"Query '{query_key}' not found. Available queries: {list(queries)}"
        ) from None


def run_query(query_key: str, end_point: str = "knowledge_graph_core") -> dict:
    """Execute a named SPARQL query against the given endpoint.

    Args:
        query_key: query label in yml file (see available_sparql_queries for a list).
        end_point: SPARQL endpoint key in the sparql_endpoints config section.

    Returns:
        JSON response bindings.
    """
    # Load the query config strings
    configs = load_sparql_configs()
    endpoint_cfg = configs["sparql_endpoints"][end_point]

    creds = _get_CREDS_CACHE() if endpoint_cfg["requires_auth"] else None
    auth = (creds["USERNAME"], creds["PASSWORD"]) if creds else None

    # Do the query
    rslt = external_io.post(
        url=endpoint_cfg["url"],
        data=configs["queries"][query_key],
        headers=configs["query_headers"],
        auth=auth,
    ).json()

    return rslt.get("results", {}).get("bindings", [])


def parse_sparql_bindings(bindings: list[dict]) -> list[dict]:
    """Convert SPARQL JSON bindings into a list of simple dictionaries."""
    return [{key: val["value"] for key, val in row.items()} for row in bindings]


# DOMAIN QUERIES


def get_flux_tower_predicates_from_rdf() -> dict:
    """Get the UIDs of the RDF graph predicates for flux towers.

    Returns:
        dictionary mapping common names (keys) to UIDs (values).

    """
    rows = parse_sparql_bindings(run_query("list_predicates"))

    return {row["predicate"].split("/")[-1]: row["predicate"] for row in rows}


def get_flux_tower_attrs_from_rdf() -> dict:
    """Get the UIDs of the RDF graph nested attrs for flux towers.

    Returns:
        Dictionary mapping common names (keys) to UIDs (values).
    """
    bindings = run_query(query_key="get_attributes")
    uuid_list = [b["attr_uuid"]["value"] for b in bindings]
    return {
        value: key
        for key, value in rdf_label_resolver.dereference_labels(uris=uuid_list).items()
    }


def get_flux_tower_geometry_from_rdf(format_site_names: bool = True) -> dict[str, dict]:
    """Get lat / long / elevation nested attributes.

    Args:
        format_site_names: if True (default), rewrite RDF labels to EP/DSA
            site names via `convert_site_label`.

    Returns:
        Dict with site name keys and geo info dict as value.
    """
    rows = parse_sparql_bindings(run_query("get_geometry"))

    rslt = {}

    for row in rows:
        site = row["label"]

        if format_site_names:
            site = convert_site_label(site)

        rslt[site] = {
            "latitude": float(row.get("latitude")) if row.get("latitude") else None,
            "longitude": float(row.get("longitude")) if row.get("longitude") else None,
            "elevation": float(row.get("elevation")) if row.get("elevation") else None,
        }

    return rslt


def get_flux_tower_fields_from_rdf(
    query: str = "operational",
    format_site_names: bool = True,
    current_only: bool = True,
    add_tz_vars=True,
) -> dict:
    """Get flux tower global metadata fields from the RDF graph, keyed by site name.

    Args:
        query: 'operational' (default) or 'extended' — selects which
            SPARQL query mode to run.
        format_site_names: if True, rewrite RDF labels to EP/DSA site names
            via `convert_site_label`.
        current_only: if True, skip sites with a date_decommissioned value.
        add_tz_vars: if True, add time_zone/UTC_offset fields derived from
            latitude/longitude (left as None if either is missing).

    Returns:
        Dict keyed by site name, sorted, each value a dict of raw RDF
        attributes for that site.
    """
    # Set query
    mode = "get_operational"
    if query == "extended":
        mode = "get_extended"

    # Query and extract the data
    rows = parse_sparql_bindings(run_query(query_key=mode))
    rslt = {}

    # Iterate over results
    for attrs in rows:
        # Skip decommissioned sites if current_only = True
        if current_only and attrs.get("date_decommissioned"):
            continue

        # Rewrite labels to EP and DSA vocabs
        site = attrs["label"]
        if format_site_names:
            site = convert_site_label(label=site)
        attrs["site_name"] = site
        attrs["dsa_label"] = attrs.pop("label")

        # Generate time-based variables
        if add_tz_vars:
            tz = {"time_zone": None, "UTC_offset": None}
            try:
                tz["time_zone"] = get_timezone(
                    lat=float(attrs["latitude"]), lon=float(attrs["longitude"])
                )
                tz["UTC_offset"] = get_UTC_offset(tz_name=tz["time_zone"])
            except KeyError:
                pass
            attrs.update(tz)
        rslt[site] = attrs

    return {site: rslt[site] for site in sorted(rslt)}


def write_flux_tower_fields_config(overwrite: bool = False) -> None:
    """Write data from rdf graph to local yml file.

    Args:
        overwrite (bool, optional): overwrite existing file if True.
        Defaults to False.

    Raises:
        FileExistsError: raised if file exists and overwrite=False.

    Returns:
        None.

    """
    rslt = get_flux_tower_fields_from_rdf(query="operational")
    file_path = config_loader.CONFIG_PATH / "site_metadata.yml"
    if not overwrite:
        if file_path.exists():
            raise FileExistsError("File already exists!")
    file_io.write_yml_file(file_path=file_path, data=rslt)


def get_instrument_vocab():
    """Return the raw SPARQL bindings for the TERN instrument controlled vocabulary."""
    return parse_sparql_bindings(
        run_query(query_key="get_instrument_vocabulary", end_point="tern_vocabs_core")
    )


# UTILITY FUNCTIONS


def convert_site_label(label: str) -> str:
    """Drop ' Flux Station' and convert name alias.

    Args:
        label: original site label.

    Returns:
        converted site label.

    """
    label_clean = label.replace(" Flux Station", "")
    return ALIAS_DICT.get(label_clean, label_clean).replace(" ", "")
