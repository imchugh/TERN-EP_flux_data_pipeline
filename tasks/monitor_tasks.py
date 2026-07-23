# -*- coding: utf-8 -*-
"""Monitor tasks: network status and dashboard outputs."""

from tasks.registry import register


@register
def construct_status_geojson() -> None:
    """Construct the network status geojson."""

    from services.network.state_task_orchestrator import aggregate
    aggregate(run_tasks=True, output='geojson')
