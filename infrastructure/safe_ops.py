#!/usr/bin/env python3
"""Run a component with logged, non-raising fallback on failure.

The documented fan-out isolation boundary: per-site/per-component work whose
failure must not abort its siblings (state-task adapters, monitors, RTMC
site-details collation) goes through `safe_component`, so every swallowed
exception is logged at WARNING with its error text and the caller gets a
typed fallback instead.
"""


def safe_component(
    fn,
    *,
    logger,
    component: str,
    fallback,
    include_error: bool = False,
    log_extra: dict | None = None,
    **kwargs,
):
    """Return fn(**kwargs), or `fallback` (logged at WARNING) if it raises.

    Args:
        fn: the callable to run.
        logger: logger to record the failure on.
        component: name of the component; also the log message, so give it
            a stable, greppable value.
        fallback: value returned on failure.
        include_error: if True, return `fallback | {"error": str(exc)}` on
            failure (`fallback` must be a dict), for null-result contracts
            that carry the reason a check failed.
        log_extra: extra fields (e.g. `{"site": ...}`) added to the log record.
        **kwargs: passed through to fn.
    """
    try:
        return fn(**kwargs)

    except Exception as e:
        logger.warning(
            component,
            extra={
                "component": component,
                "status": "failure",
                "error_type": type(e).__name__,
                "error": str(e),
                **(log_extra or {}),
            },
        )
        if include_error:
            return fallback | {"error": str(e)}
        return fallback
