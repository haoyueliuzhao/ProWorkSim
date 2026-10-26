"""Exact task routing for new v062 graders; no actor network access."""
from __future__ import annotations

import json

from . import software_benchmark_dispatch_v062 as policy
from . import software_benchmark_requests_offline_v062 as offline
from . import software_benchmark_requests_tls_v062 as tls
from .software_benchmark_candidates_v054 import reference, checked
from .software_benchmark_ref_plan_v062 import retain

OFFLINE_TASKS = frozenset(("psf__requests-2931", "psf__requests-5414"))
TLS_TASKS = frozenset(tls.PROFILES)
TASKS = OFFLINE_TASKS | TLS_TASKS


def provider(task):
    return tls if task in TLS_TASKS else offline if task in OFFLINE_TASKS else None


def capabilities(task):
    return ["NET_ADMIN", "NET_BIND_SERVICE"] if task in TLS_TASKS else ["NET_ADMIN"] if task in OFFLINE_TASKS else []


def prepare():
    """Freeze local provider inputs. Reuse the tested numeric TLS endpoint; no DNS."""
    folder = policy.BATCH_ROOT / "grading-environments"
    values = {"offline": retain(folder / "offline.json", offline.environment_manifest()),
              "tls": retain(folder / "tls.json", tls.environment_manifest())}
    historical = policy.ROOT / "runs/software-benchmark-v060/original-ca-rescore-r1-20261025/environment-admission/task-qualifications"
    resolutions = {}
    for task in sorted(TLS_TASKS):
        qualification = json.loads((historical / task / "qualification.json").read_bytes())
        identity = json.loads(checked(qualification["controls"][0]["identity"]).read_bytes())
        ref = identity["network_resolution"]
        value = json.loads(checked(ref).read_bytes())
        addresses = policy.validate_ipv4_targets(value["ipv4"])
        if (value.get("selected_ip") != addresses[0] or value.get("hostname") != "httpbin.org"
                or value.get("ports") != [80, 443] or value.get("automatic_retry") is not False):
            raise ValueError("Historical frozen httpbin endpoint identity is not bounded")
        resolutions[task] = ref
    values["network_resolutions"] = resolutions
    return retain(folder / "bindings.json", values)


def request_fields(task):
    bindings = json.loads(checked(reference(policy.BATCH_ROOT / "grading-environments/bindings.json")).read_bytes())
    if task in TLS_TASKS:
        return {"environment_revision": bindings["tls"], "network_resolution": bindings["network_resolutions"][task]}
    if task in OFFLINE_TASKS:
        return {"environment_revision": bindings["offline"], "network_resolution": None}
    return {"environment_revision": None, "network_resolution": None}


def validate_request(request, task):
    expected = request_fields(task)
    if any(request.get(key) != value for key, value in expected.items()):
        raise ValueError("Task-specific provider or frozen network identity changed")
    adapter = provider(task)
    if adapter is not None:
        adapter.validate_environment(expected["environment_revision"])
    return adapter
