"""Cold grading providers whose frozen identity matches the executing scope.

This factory creates only private Python objects and local immutable manifests.
It never launches a container, probes DNS, connects a socket or grants authority.
Each new scope needs its own manifest and newly qualified gold/empty controls.
"""
from __future__ import annotations

import copy
import ipaddress
import json
from pathlib import Path
from types import FunctionType, ModuleType

from . import software_benchmark_grading_environment_v066 as original_environment
from . import software_benchmark_requests_offline_v066 as original_offline
from . import software_benchmark_requests_tls_v066 as original_tls
from . import software_benchmark_requests_tls_v068 as lifecycle
from . import software_benchmark_grading_ca_v116 as ca
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_function, clone_namespace

VERSION = "v141-cold-scope-bound-grading-environment-r1"


def _module(namespace, name):
    result = ModuleType(name)
    result.__dict__.update(namespace)
    return result


def _class(cls, namespace):
    methods = {name: clone_function(value, namespace) for name, value in vars(cls).items()
               if isinstance(value, FunctionType)}
    return type(cls.__name__, (cls,), methods)


def _load(ref):
    return json.loads(checked(ref).read_bytes())


def _retain(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        ref = reference(path)
        if _load(ref) != value:
            raise ValueError("Refuse to overwrite a previously frozen grading environment")
        return ref
    return write_new(path, value)


def validate_resolution(resolution_ref, *, scope_ref, expected_source):
    """Validate supplied new-scope probe evidence without doing a network probe."""
    checked(scope_ref)
    value = _load(resolution_ref)
    addresses = value.get("ipv4")
    if (not isinstance(addresses, list) or not addresses or len(set(addresses)) != len(addresses)
            or value.get("scope") != scope_ref or value.get("source") != expected_source
            or value.get("hostname") != "httpbin.org" or value.get("ports") != [80, 443]
            or value.get("selected_ip") != addresses[0] or value.get("automatic_retry") is not False):
        raise ValueError("A new-scope frozen public endpoint and explicit probe source are required")
    for address in addresses:
        ip = ipaddress.IPv4Address(address)
        if str(ip) != address or not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise ValueError("Only literal public IPv4 endpoints may enter scoring")
    proof = _load(value["diagnostic"])
    if (proof.get("scope") != scope_ref or addresses[0] not in proof.get("current_DNS_ipv4", [])
            or not all(any(row.get("ip") == addresses[0] and row.get("port") == port
                           and row.get("get_contract_valid") is True
                           for row in proof.get("probes", [])) for port in (80, 443))):
        raise ValueError("Frozen endpoint lacks this scope's successful bounded HTTP/HTTPS probe")
    return value


def assert_runtime_binding(provider):
    """Check the validator used by actual start, not just module attributes."""
    validator = provider.validate_environment
    if validator.__globals__.get("environment_manifest") is not provider.environment_manifest:
        raise ValueError("Actual environment validator is bound to another manifest function")
    for cls in provider.EnvironmentContainer.__mro__:
        start = vars(cls).get("start")
        if isinstance(start, FunctionType) and "validate_environment" in start.__globals__:
            if start.__globals__["validate_environment"] is not validator:
                raise ValueError("Actual container start is bound to another environment validator")
            return True
    raise ValueError("No executing start-to-environment-validator binding was found")


def cold_environment(policy, *, scope_ref, directory, resolution_ref=None,
                     resolution_source="v142_current_DNS_and_bounded_endpoint_probe"):
    """Build unqualified providers from original mechanisms, never old bindings.

    ``policy`` must be the caller's new authorization-aware dispatch view. The
    caller separately freezes plan/resources and obtains actual environment
    qualification; this factory contains no grant or historical-score reuse.
    """
    from .software_benchmark_grading_repairs_v141 import transport_adapter
    checked(scope_ref)
    if not callable(getattr(policy, "require_v066_allowed", None)):
        raise ValueError("A concrete new-scope dispatch guard is required")
    directory = Path(directory).resolve()
    tcp = transport_adapter(policy)
    offline_ns = clone_namespace(original_offline, require_v066_allowed=policy.require_v066_allowed)
    original_manifest = offline_ns["environment_manifest"]

    def offline_manifest():
        return {**original_manifest(), "version": VERSION, "dispatch_guard": scope_ref,
                "environment_factory": reference(__file__), "binding_directory": str(directory),
                "authorization_bound_by": "Explicit caller scope and per-object request; no historical authority",
                "fresh_scope_manifest": True, "runtime_qualified": False}

    offline_ns["environment_manifest"] = offline_manifest
    offline_ns["EnvironmentContainer"] = _class(original_offline.EnvironmentContainer, offline_ns)
    offline = _module(offline_ns, __name__+".offline")
    tls_ns = clone_namespace(original_tls, prior=offline, transport=tcp, policy=policy)
    tls_ns["EnvironmentContainer"] = _class(original_tls.EnvironmentContainer, tls_ns)
    tls = _module(tls_ns, __name__+".tls")
    ca.bind_tls(tls)  # Private module only; immutable approved CA bytes remain separate.
    approved_manifest = tls.environment_manifest

    def tls_manifest():
        return {**approved_manifest(), "environment_factory_revision": VERSION,
                "environment_factory": reference(__file__), "dispatch_guard": scope_ref,
                "binding_directory": str(directory), "fresh_scope_manifest": True,
                "runtime_qualified": False}

    tls.environment_manifest = tls_manifest
    tls.validate_environment.__globals__["environment_manifest"] = tls_manifest
    tls.run_official = lifecycle.run_official
    ns = clone_namespace(original_environment, policy=policy, offline=offline, tls=tls)

    def prepare():
        checked(scope_ref)
        if resolution_ref is not None:
            validate_resolution(resolution_ref, scope_ref=scope_ref, expected_source=resolution_source)
        for provider in (offline, tls):
            assert_runtime_binding(provider)
        values = {"offline": _retain(directory/"offline.json", offline.environment_manifest()),
                  "tls": _retain(directory/"tls.json", tls.environment_manifest()),
                  "scope": scope_ref, "factory": reference(__file__),
                  "current_scope_resolution_required_for": sorted(ns["TLS_TASKS"])}
        result = _retain(directory/"bindings.json", values)
        offline.validate_environment(values["offline"])
        tls.validate_environment(values["tls"])
        return result

    def request_fields(task):
        values = _load(reference(directory/"bindings.json"))
        if values.get("scope") != scope_ref or values.get("factory") != reference(__file__):
            raise ValueError("Frozen bindings belong to another scope or environment factory")
        if task in ns["TLS_TASKS"]:
            if resolution_ref is None:
                raise ValueError("Live Requests tasks require a separately authorized fresh endpoint probe")
            validate_resolution(resolution_ref, scope_ref=scope_ref, expected_source=resolution_source)
            return {"environment_revision": values["tls"], "network_resolution": resolution_ref}
        if task in ns["OFFLINE_TASKS"]:
            return {"environment_revision": values["offline"], "network_resolution": None}
        return {"environment_revision": None, "network_resolution": None}

    def validate_request(request, task):
        expected = request_fields(task)
        if any(request.get(key) != value for key, value in expected.items()):
            raise ValueError("Task's new-scope environment or endpoint identity changed")
        provider = ns["provider"](task)
        if provider is not None:
            assert_runtime_binding(provider)
            provider.validate_environment(expected["environment_revision"])
        return provider

    ns.update(prepare=prepare, request_fields=request_fields, validate_request=validate_request)
    return _module(ns, __name__+".environment")


def validate_cold_identity(environment, task, request):
    """Necessary CPU preflight before creation; does not qualify a task."""
    provider = environment.validate_request(copy.deepcopy(request), task)
    return {"version": VERSION, "instance_id": task, "actual_provider_bound": provider is not None,
            "environment_revision": request.get("environment_revision"),
            "network_resolution": request.get("network_resolution"),
            "frozen_manifest_equals_executing_manifest": True,
            "gold_empty_runtime_qualification": False, "container_operations": 0}


def validate_transport_evidence(receipt, quiet, observed, identity, folder, **kwargs):
    """Retain CA/limits/cleanup checks and bind the new scope's exact endpoint."""
    from . import software_benchmark_environment_v116 as historical
    from . import software_benchmark_scope_v142 as scope
    validator = clone_function(historical.validate_transport_evidence,
                               {**historical.validate_transport_evidence.__globals__, "scope": scope})
    result = validator(receipt, quiet, observed, identity, folder, **kwargs)
    for row in result.get("connections", []):
        if row.get("outcome") == "tcp_eof" and not all(row.get(key) is True for key in
                ("client_eof_observed", "remote_eof_observed", "tcp_completion_evidence")):
            raise ValueError("A new clean TCP closure needs actual two-sided EOF evidence")
    return result
