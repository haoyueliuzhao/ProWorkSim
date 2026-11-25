"""Clarify the distinction between a cross-package blocker and a within-package review debt."""

from .software_event_orders_v243 import wire as original_wire


def wire(row, choices):
    request = original_wire(row, choices)
    request["messages"][0]["content"] += (
        " For anomaly, distinguish the affected package from a separate upstream package. "
        "Classify a dependency blocker (A2) when a receipt links a downstream package to an upstream "
        "artifact it cannot currently use. The order of steps within one package alone does not establish "
        "that relation. A formed candidate lacking required independent verification of its current version "
        "is a verification gap (A4). Cite the direct receipt and choose the work route separately."
    )
    return request
