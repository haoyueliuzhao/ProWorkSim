"""Explicit next-deployment inputs; never rebind frozen v203.2.1 globals.

Future packaging must use this module, the public-test binding helper, its pinned
manifest and v175 managed entry together. These functions prepare configuration
bytes only. No historical actor/controller is changed or started by importing it.
"""
from __future__ import annotations

import json
from types import FunctionType

from . import software_benchmark_runtime_inputs_v203_2_1 as original
from . import software_benchmark_public_test_binding_v203_2_2 as binding
from .storage import json_bytes

VERSION = binding.VERSION
PUBLIC_FILES = binding.public_files()
RESULT_REVISION = binding.manifest()["result_revision"]


def rebound(function, **updates):
    namespace = {**function.__globals__, "PUBLIC_FILES": PUBLIC_FILES,
                 "RESULT_REVISION": RESULT_REVISION, **updates}
    bound = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = function.__kwdefaults__
    return bound


def actor_inputs(*args, **kwargs):
    binding.manifest()
    result = rebound(original.actor_inputs)(*args, **kwargs)
    result["config"].update(public_test_bundle_manifest_sha256=binding.MANIFEST_SHA256,
                            public_test_deployment_revision=binding.manifest()["deployment_revision"])
    result["files"]["public-test-bundle-manifest.json"] = binding.MANIFEST.read_bytes()
    return result


def validate_actor_selection(ready, expected):
    binding.manifest()
    if (expected.get("public_test_bundle_manifest_sha256") != binding.MANIFEST_SHA256
            or expected.get("public_test_deployment_revision") != binding.manifest()["deployment_revision"]):
        raise ValueError("Actor configuration lacks the v203.2.2 public-test deployment admission")
    proof = binding.admit_loaded_hashes(ready.get("public_test_files_sha256"))
    result = rebound(original.validate_actor_selection)(ready, expected)
    return {**result, "public_test_bundle_admission": proof}


def controller_inputs(*args, **kwargs):
    result = rebound(original.controller_inputs, validate_actor_selection=validate_actor_selection)(*args, **kwargs)
    config = json.loads(result["controller-config.json"])
    config.update(public_test_bundle_manifest_sha256=binding.MANIFEST_SHA256,
                  public_test_deployment_revision=binding.manifest()["deployment_revision"])
    result["controller-config.json"] = json_bytes(config)
    return result


public_test_guidance = original.public_test_guidance
public_dependency_descriptor = original.public_dependency_descriptor
