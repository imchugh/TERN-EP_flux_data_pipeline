"""Monitor tasks: network status and dashboard outputs."""

from tasks.registry import register


@register
def construct_status_geojson() -> None:
    """Construct the network status geojson."""
    from services.network.state_task_orchestrator import aggregate

    aggregate(run_tasks=True, output="geojson")


# -----------------------------------------------------------------------------


@register
def construct_legacy_status_geojson() -> dict:
    """Construct the legacy-format network status geojson (network_status.json).

    Temporary bridge for a downstream visualisation that still expects the
    old flat per-site {Fco2, Fh, Fe, Fsd} schema. See
    orchestration/legacy_network_status.py for removal notes.
    """
    from orchestration.legacy_network_status import build
    from tasks.tasks import mngr

    return build(site_list=mngr.get_site_list())
