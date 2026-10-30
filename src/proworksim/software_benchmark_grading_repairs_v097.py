"""Opt-in private scorer binding; no runtime launch and no frozen source edits."""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import FunctionType, ModuleType, SimpleNamespace

from . import software_benchmark_grader_probe_v097 as probe
from . import software_benchmark_requests_tls_v068 as tls_lifecycle
from .software_benchmark_candidates_v054 import reference

VERSION = "v097-private-grader-probe-and-tls-cleanup-r1"


def _bind(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


def bind_scorer(scorer):
    """Retain the caller's exact identity/permission/candidate validators.

    The returned module must receive its own frozen manifest and control runs.
    It does not authorize containers or qualify any prior failed environment.
    """
    old_namespace = scorer.score_request.__globals__
    namespace = {**old_namespace, **vars(scorer)}
    tls = SimpleNamespace(**{**vars(scorer.environment.tls),
                            "run_official": tls_lifecycle.run_official})
    environment = SimpleNamespace(**{**vars(scorer.environment), "tls": tls})
    namespace["environment"] = environment
    for name, value in list(namespace.items()):
        if isinstance(value, FunctionType) and value.__globals__ is old_namespace:
            namespace[name] = _bind(value, namespace)

    class ObservedContainer(scorer.ObservedContainer):
        def start(self, *args, **kwargs):
            namespace["policy"].require_v066_allowed(
                "v066.grader.start", instance_id=self.preparation["mapping"]["instance_id"])
            self.delegate.reload()
            namespace["validate_attrs"](self.delegate.attrs, self.preparation)
            result = namespace["base"].PreparationObservedContainer.start(self, *args, **kwargs)
            namespace["validate_attrs"](self.delegate.attrs, self.preparation)
            path = Path(self.preparation["path"])
            observed = json.loads(path.read_bytes())
            if (observed["head_git_tree"] != self.preparation["mapping"]["official_tree"]
                    or observed["working_tree_clean"] is not True):
                raise ValueError("Official initial baseline is not the pinned clean tree")
            inside, evidence = probe.observe(self.delegate,
                self.preparation["mapping"]["public_python"],
                path.with_name("private-boundary-probe-v097.json"))
            archive = namespace["archive"]
            host = {key: os.stat("/proc/self/ns/" + key).st_ino for key in archive.NAMESPACES}
            if inside["cpus"] != namespace["cpus"](self.preparation["cpuset_cpus"]):
                raise ValueError("Actual grader CPU affinity differs")
            observed.update(
                namespace_evidence=archive.namespace_evidence(inside["namespaces"], host),
                boundary_probe=evidence, source_image_id=self.preparation["image_id"],
                candidate_or_official_tests_changed=False, actual_cap_add=[],
                actual_cap_drop=["ALL"], effective_network_mode="none",
                resource_key=self.preparation["resource_key"])
            path.write_bytes(namespace["base"].canonical(observed))
            return result

    class Containers(scorer.Containers):
        create = _bind(scorer.Containers.create,
                       {**scorer.Containers.create.__globals__, **namespace,
                        "ObservedContainer": ObservedContainer})

    inherited_manifest = scorer.installation_manifest

    def installation_manifest():
        return {**inherited_manifest(), "environment_mechanism_revision": VERSION,
            "boundary_probe_adapter": reference(probe.__file__),
            "scorer_mechanism_adapter": reference(__file__),
            "tls_cleanup_binding_adapter": reference(tls_lifecycle.__file__),
            "official_tests_and_scoring_rules_changed": False,
            "runtime_qualified_by_CPU_controls": False}

    namespace.update(ObservedContainer=ObservedContainer, Containers=Containers,
                     installation_manifest=installation_manifest)
    result = ModuleType("proworksim.private_scorer_v097")
    result.__dict__.update(namespace)
    return result
