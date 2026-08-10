#!/usr/bin/env python3
"""Created on Wed Mar 18 11:41:02 2026

@author: imchugh
"""


def safe_component(
    fn,
    *,
    logger,
    component: str,
    fallback,
    **kwargs,
):
    """Execute a component safely.

    - On success: return function result
    - On failure: log and return fallback
    """
    try:
        return fn(**kwargs)

    except Exception as e:
        logger.debug(
            "",
            extra={
                "event": "component_failed",
                "component": component,
                "status": "failure",
                "error_type": type(e).__name__,
            },
        )
        return fallback
