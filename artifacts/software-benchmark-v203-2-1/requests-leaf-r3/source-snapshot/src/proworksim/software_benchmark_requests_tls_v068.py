"""TLS shutdown hook for the actual private official-evaluator namespace.

The existing v066 fixture, CA checks and byte relay remain unchanged. This
module changes only which cleanup binding receives their existing finish hook.
"""
from __future__ import annotations

import threading

VERSION = "v068-private-evaluator-tls-lifecycle-r1"
_BINDING_LOCK = threading.RLock()


def run_official(run_instance, *args, tracking, **kwargs):
    namespace = getattr(run_instance, "__globals__", None)
    if not isinstance(namespace, dict) or not callable(namespace.get("cleanup_container")):
        raise ValueError("A concrete evaluator with its actual cleanup binding is required")
    with _BINDING_LOCK:
        original = namespace["cleanup_container"]
        lifecycle = {"version": VERSION, "binding": "passed_function.__globals__.cleanup_container",
            "cleanup_calls": 0, "finish_attempts_before_cleanup": 0, "binding_restored": False}
        tracking["tls_lifecycle"] = lifecycle
        finish_requested = set()

        def cleanup(client, container, logger):
            if container is not None:
                wrapper = tracking.get("environment_container")
                if (wrapper is None or container.id not in tracking.get("owned_container_ids", [])
                        or getattr(getattr(wrapper, "delegate", None), "id", None) != container.id):
                    raise ValueError("Cleanup received a container outside this TLS wrapper's ownership")
                if container.id not in finish_requested:
                    finish_requested.add(container.id)
                    lifecycle["finish_attempts_before_cleanup"] += 1
                    try:
                        wrapper.finish_transport()
                    except Exception as error:
                        # Resource teardown must still run. The independent scoring
                        # evidence remains incomplete and is never upgraded to pass.
                        tracking.setdefault("transport_cleanup_errors", []).append(str(error))
            lifecycle["cleanup_calls"] += 1
            return original(client, container, logger)

        namespace["cleanup_container"] = cleanup
        try:
            return run_instance(*args, **kwargs)
        finally:
            namespace["cleanup_container"] = original
            lifecycle["binding_restored"] = True
