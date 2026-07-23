# -*- coding: utf-8 -*-
"""Monitor tasks: network status and dashboard outputs."""

from tasks.registry import register


@register
def construct_status_geojson() -> None:
    """Construct the network status geojson."""

    from services.network.state_task_orchestrator import aggregate
    aggregate(run_tasks=True, output='geojson')

# -----------------------------------------------------------------------------

@register
def construct_site_details(site: str) -> None:
    """Construct the site details TOA5 file for RTMC plotting."""

    from orchestration.site_details_construction import build_site_details_toa5
    build_site_details_toa5(site=site)

# -----------------------------------------------------------------------------

@register
def construct_site_details_json() -> None:
    """Generate site_info.json for all sites (RTMC data source)."""

    from orchestration.site_details_construction import build_site_details_json
    from tasks.tasks import mngr
    build_site_details_json(site_list=mngr.get_site_list())
