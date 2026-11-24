"""The v231 execution contract with an additional reversible worker-input projection."""

from .software_context_builder_v230 import identity
from .software_context_fields_v231_1 import transform
from .software_graph_execution_v230 import Execution
from .storage import atomic_write, digest, json_bytes


class FieldExecution(Execution):
    def __init__(self, backend, folder, episode, branch, condition):
        if condition != "T2":
            raise ValueError("This endpoint is for the registered nested-field condition only")

        def projected(route, payload):
            wire = payload["wire"]
            final, edits = transform(wire, payload["member_id"])
            if route != "/chat/completions":
                counted = backend(route, {**payload, "wire": final})
                if counted["request_sha256"] != digest(json_bytes(final)):
                    raise ValueError("Count and final wire differ")
                return {
                    **counted,
                    "final_sha256": counted["request_sha256"],
                    "request_sha256": digest(json_bytes(wire)),
                }
            rid = payload["request_id"]
            attempt = folder / "worker" / identity([branch, payload["member_id"], rid])
            # The existing endpoint already claimed the single-use request and saved original/T1.
            manifest = {
                "condition": condition,
                "actor": payload["member_id"],
                "branch": branch,
                "request_id": rid,
                "intermediate_t1": identity(wire),
                "physical_t2": identity(final),
                "edits": edits,
            }
            atomic_write(attempt / "final-manifest.json", json_bytes(manifest))
            atomic_write(attempt / "final.json", json_bytes(final))
            return backend(route, {**payload, "wire": final})

        super().__init__(projected, folder, episode, branch, "T1")
