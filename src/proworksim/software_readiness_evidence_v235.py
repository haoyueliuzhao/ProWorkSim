"""Project the observer's predecision readiness receipt into an A4 controller input."""

from copy import deepcopy
import json

from .software_context_builder_v230 import compact
from .software_project_relations_v217 import identity


def detailed_input(wire, observations, observer, boundary):
    revised = deepcopy(wire)
    view = json.loads(revised["messages"][-1]["content"])
    if view["anomaly"] != "A4" or view["subject"] != "independent_current_review":
        raise ValueError("Expected a current-review obligation")
    for label, ref in view["evidence"].items():
        if ref["tool"] != "delivery_readiness":
            continue
        matches = [
            item["outcome"]
            for item in observations
            if item["ordinal"] == ref["opportunity"] <= boundary
            and item["outcome"]["worker_id"] == observer
            and (item["outcome"].get("response") or {}).get("command_id") == ref["command_id"]
        ]
        if len(matches) != 1:
            raise ValueError("Missing unique predecision receipt for " + label)
        observation = matches[0]
        response = observation["response"]
        if (
            observation["decision"]["action"] != "delivery_readiness"
            or not response["ok"]
            or identity(response) != ref["sha256"]
        ):
            raise ValueError("Mismatched readiness receipt")
        ready = response["result"]
        test = ready.get("final_test") or {}
        final = ready.get("final_identity") or {}
        view.setdefault("readiness_by_evidence", {})[label] = {
            "ready_to_submit": ready["ready_to_submit"],
            "final_source_reference": final.get("source_reference"),
            "last_public_test": {
                key: test.get(key) for key in ("source_reference", "executed", "passed")
            },
            "current_fixed_patch_ids": ready["current_fixed_patch_ids"],
            "packages": [
                {k: package[k] for k in ("task_id", "owner", "reviewer", "missing")}
                for package in ready["package_chain"]["packages"]
                if package["task_id"] in view["graph"]["work"]
            ],
            "remaining_delivery_checks": [gap["kind"] for gap in ready["gaps"] if "kind" in gap],
        }
    if not view.get("readiness_by_evidence"):
        raise ValueError("No linked readiness evidence")
    revised["messages"][-1]["content"] = compact(view)
    return revised
