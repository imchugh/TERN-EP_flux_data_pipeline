# -*- coding: utf-8 -*-
"""Monitor tasks: network status and dashboard outputs."""

from tasks.registry import register


@register
def construct_status_geojson() -> None:
    """Construct the network status geojson."""

    import network_monitoring.network_status as ns
    from tasks.tasks import mngr
    ns.network_status_to_geojson(
        site_list=mngr.get_site_list_for_task(task='construct_status_geojson')
        )

# -----------------------------------------------------------------------------

@register
def construct_site_details(site: str) -> None:
    """Construct the site details file for RTMC plotting."""

    import data_constructors.details_constructor as deetcon
    deetcon.write_site_info(site=site)

# -----------------------------------------------------------------------------

@register
def construct_site_details_json() -> None:

    import data_constructors.details_constructor as deetcon
    from tasks.tasks import mngr
    deetcon.site_info_2_json(site_list=mngr.get_site_list())
