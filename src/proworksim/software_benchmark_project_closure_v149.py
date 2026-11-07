"""Run-identity binding separate from the unchanged v141 managed role contract.

The caller supplies a host-validated row; this core treats the run slot as an
opaque identity, so a new run namespace does not require another prefix patch.
Host scope/membership attestation remains mandatory at the export boundary.
"""

from __future__ import annotations

from types import FunctionType

from . import software_benchmark_project_closure_v141 as original

VERSION = "v149-explicit-run-identity-same-managed-closure-r1"
IDENTITY_KEYS = (
    "slot_id",
    "instance_id",
    "condition_id",
    "seed",
    "organization_id",
    "group_id",
    "arm",
    "execution_arm",
    "fixed_members",
    "member_count",
)


def normalized_identity(identity):
    if not isinstance(identity, dict) or any(k not in identity for k in IDENTITY_KEYS):
        raise ValueError("An explicitly validated run/task/role identity is required")
    result = {k: identity[k] for k in IDENTITY_KEYS}
    if (
        not isinstance(result["slot_id"], str)
        or not result["slot_id"]
        or type(result["seed"]) is not int
    ):
        raise ValueError("Run identity and canonical seed must be explicit")
    # Validate the model/role contract using its own original namespace without
    # imposing that namespace on the new execution slot or emitted evidence.
    canonical = f"v142:{result['instance_id']}:{result['condition_id']}:{result['seed']}"
    checked = original.validate_slot_identity(canonical, result["instance_id"])
    if any(result[k] != checked[k] for k in IDENTITY_KEYS if k != "slot_id"):
        raise ValueError("Execution task, condition, seed or role roster changed")
    return result


def validate_slot_identity(slot_id, instance_id, *, identity):
    result = normalized_identity(identity)
    if result["slot_id"] != slot_id or result["instance_id"] != instance_id:
        raise ValueError("Closure identity differs from the host-bound execution row")
    return result


def _bind(function, namespace):
    value = FunctionType(
        function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__
    )
    value.__kwdefaults__ = dict(function.__kwdefaults__ or {})
    return value


def _namespace(identity):
    def validate(slot_id, instance_id):
        return validate_slot_identity(slot_id, instance_id, identity=identity)

    namespace = {**original.__dict__, "VERSION": VERSION, "validate_slot_identity": validate}
    base_namespace = {
        **original._base_validate.__globals__,
        "VERSION": VERSION,
        "validate_slot_identity": validate,
    }
    namespace["_base_validate"] = _bind(original._base_validate, base_namespace)
    namespace["validate_delivery_evidence"] = _bind(original.validate_delivery_evidence, namespace)
    return namespace


def validate_delivery_evidence(evidence, snapshot, baseline_bundle, *, validated_identity=None):
    identity = normalized_identity(validated_identity or evidence.get("execution_identity"))
    if (
        evidence.get("execution_identity") != identity
        or snapshot.get("execution_identity") != identity
    ):
        raise ValueError("Closure evidence lost its explicit execution identity")
    namespace = _namespace(identity)
    return namespace["validate_delivery_evidence"](evidence, snapshot, baseline_bundle)


def export_managed_closure(prepared, folder, *, slot_id, sdk_closed, validated_identity):
    identity = validate_slot_identity(
        slot_id, prepared.case["case_id"], identity=validated_identity
    )
    namespace = _namespace(identity)

    def write(path, value):
        if (
            isinstance(value, dict)
            and value.get("version") == VERSION
            and value.get("slot_id") == slot_id
        ):
            value = {**value, "execution_identity": identity}
        return original.write_new(path, value)

    namespace["write_new"] = write
    result = _bind(original.export_managed_closure, namespace)(
        prepared, folder, slot_id=slot_id, sdk_closed=sdk_closed
    )
    return {**result, "execution_identity": identity}
