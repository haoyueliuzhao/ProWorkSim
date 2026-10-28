"""Separate physical cleanup from unrecoverable CA/scoring evidence.

All mutations require the v068 scope guard. Docker access is limited to an
injected or fixed read-only exact-ID inspection. Existing results are retained.
The old scorer executes in a private function namespace with the new TLS hook;
no old module globals are changed.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import re
import time
from types import FunctionType, SimpleNamespace

from . import software_benchmark_dispatch_v066 as primary
from . import software_benchmark_scorer_v066 as original_scorer
from . import software_benchmark_requests_tls_v068 as lifecycle
from .software_benchmark_candidates_v054 import checked, reference, write_new

ROOT = primary.ROOT
VERSION = "v068-grading-physical-evidence-recovery-r1"
PROOF_ROOT = ROOT / "artifacts/software-benchmark-v068/physical-cleanup-reconciliation-r2"
ORIGINAL_RECONCILIATIONS = ROOT / "artifacts/software-benchmark-v068/physical-cleanup-reconciliation-r1"
CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")


def load(ref):
    return json.loads(checked(ref).read_bytes())


def _default_guard(operation="v068.run", **identity):
    from .software_benchmark_recovery_scope_v068 import require_allowed
    return require_allowed(operation, **identity)


@lru_cache(maxsize=1)
def original_grading():
    spec = importlib.util.spec_from_file_location("v068_original_grading_delegate",
        ROOT / "tools/run_capability_grading_v066.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def private_function(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    value.__annotations__ = dict(function.__annotations__)
    return value


def scorer_with_tls_lifecycle():
    """Keep old tests/limits/validation, replacing only the host finish binding."""
    tls = SimpleNamespace(**{**vars(original_scorer.environment.tls), "run_official": lifecycle.run_official})
    environment = SimpleNamespace(**{**vars(original_scorer.environment), "tls": tls})
    namespace = {**vars(original_scorer), "environment": environment}
    namespace["_score"] = private_function(original_scorer._score, namespace)
    return private_function(original_scorer.score_request, namespace)


def score_request(request, *, guard=None):
    guard = guard or _default_guard
    guard("v068.run", instance_id=request["instance_id"])
    folder = Path(request["directory"]).resolve()
    if folder != primary.GRADING_ROOT / request["resource_key"]:
        raise ValueError("Recovery scorer must use the originally owned grading directory")
    if (folder / "quiescence.json").exists():
        raise ValueError("A consumed scoring attempt cannot be replayed")
    write_new(folder / "lifecycle-runtime-v068.json", {"version": VERSION,
        "request": reference(folder / "request.json"), "adapter": reference(__file__),
        "tls_lifecycle": reference(lifecycle.__file__), "original_scorer": reference(original_scorer.__file__),
        "original_official_manifest": request["scorer_manifest"],
        "original_manifest_scope": "unchanged official installation, tests, limits and fixture; host lifecycle override recorded separately",
        "old_module_globals_modified": False, "scoring_or_model_rules_changed": False})
    return scorer_with_tls_lifecycle()(request)


def physical_inputs(request_ref):
    request = load(request_ref)
    folder = Path(request["directory"]).resolve()
    key = request["resource_key"]
    if (folder != primary.GRADING_ROOT / key or Path(request_ref["path"]).resolve() != folder / "request.json"
            or request["plan"] != reference(primary.PLAN_FILE)):
        raise ValueError("Only this exact owned grading request can be reconciled")
    _, resource, config = original_scorer._planned(request)
    quiet_ref, completion_ref = reference(folder / "quiescence.json"), reference(folder / "completion.json")
    quiet, completion = load(quiet_ref), load(completion_ref)
    admission = load(reference(folder / "capacity-claim.json"))
    claim_ref = admission["claim"]
    claim = load(claim_ref)
    initial_ref = reference(folder / "official-output/initial-container.json")
    initial = load(initial_ref)
    identities = quiet.get("owned_container_ids")
    if (quiet.get("resource_key") != key or quiet.get("create_result_unknown") is not False
            or quiet.get("other_containers_affected") is not False
            or not isinstance(identities, list) or len(identities) != 1
            or not isinstance(identities[0], str) or not CONTAINER_ID.fullmatch(identities[0])
            or initial.get("container_id") != identities[0]
            or completion.get("request") != request_ref or completion.get("resource_key") != key
            or type(completion.get("returncode")) is not int
            or completion.get("status") not in {"process_exited", "technical_unknown"}
            or not isinstance(completion.get("finished_unix"), (int, float))
            or not isinstance(completion.get("started_unix"), (int, float))
            or completion["finished_unix"] < completion["started_unix"]
            or admission.get("prepared_request") != request_ref
            or completion.get("capacity_claim") != claim_ref
            or Path(claim_ref["path"]).resolve() != primary.BATCH_ROOT / "resource-claims" / (key + ".json")
            or claim.get("version") != primary.VERSION
            or claim.get("key") != key or claim.get("plan") != request["plan"]
            or claim.get("spec", {}).get("role") not in {"control", "score", "delivery_score"}
            or claim.get("spec", {}).get("instance_id") != request["instance_id"]):
        raise ValueError("Owned IDs, process exit or exact capacity provenance is incomplete")
    transport_ref = quiet.get("transport_result")
    if request["instance_id"] not in original_scorer.environment.TLS_TASKS or not isinstance(transport_ref, dict):
        raise ValueError("This recovery only reconciles the independently bounded TLS measurement path")
    transport = load(transport_ref)
    if (Path(transport_ref["path"]).resolve() != folder / "official-output/transport.json"
            or transport.get("thread_finished") is not True):
        raise ValueError("A live or unproven host relay cannot release capacity")
    receipt_path = folder / "receipt.json"
    receipt_ref = reference(receipt_path) if receipt_path.exists() else None
    receipt_status = load(receipt_ref).get("status") if receipt_ref else "missing"
    if not isinstance(receipt_status, str) or not receipt_status:
        raise ValueError("The existing scoring receipt has no explicit status")
    return {"request": request, "configuration": config, "resource": resource,
        "folder": folder, "quiet": quiet, "quiet_ref": quiet_ref,
        "completion": completion, "completion_ref": completion_ref,
        "claim": claim, "claim_ref": claim_ref, "initial_ref": initial_ref,
        "transport": transport, "transport_ref": transport_ref, "container_ids": identities,
        "receipt_ref": receipt_ref, "receipt_status": receipt_status}


def read_only_inspect(container_id, *, configuration):
    """Called only behind the injected scope guard; never stops/deletes objects."""
    import docker
    socket = Path(configuration["scorer_request_base"]["docker_socket"]).resolve()
    client = docker.DockerClient(base_url="unix://" + str(socket), timeout=30)
    try:
        try:
            container = client.containers.get(container_id)
        except docker.errors.NotFound:
            return {"container_id": container_id, "exists": False, "status": 404, "inspected_unix": time.time()}
        return {"container_id": container_id, "exists": True, "status": 200,
                "returned_id": container.id, "inspected_unix": time.time()}
    finally:
        client.close()


def validate_absent(observations, inputs, started_unix):
    if not isinstance(observations, list) or len(observations) != len(inputs["container_ids"]):
        raise ValueError("Every original owned ID needs its own fresh absence receipt")
    for observation, expected in zip(observations, inputs["container_ids"], strict=True):
        when = observation.get("inspected_unix")
        if (observation.get("container_id") != expected or observation.get("exists") is not False
                or observation.get("status") != 404 or not isinstance(when, (int, float))
                or not started_unix <= when <= time.time() + 1):
            raise ValueError("Only fresh exact-ID 404 observations prove absence")


def released_claim(inputs):
    claim = inputs["claim"]
    marker = primary.BATCH_ROOT / "resource-claims" / (claim["key"] + ".released.json")
    if not marker.exists():
        return False
    value = load(reference(marker))
    if value.get("claim") != inputs["claim_ref"] or value.get("quiescent") is not True:
        raise ValueError("Resource release belongs to another claim")
    lease = Path(claim["lease"])
    if lease.parent.resolve() != marker.parent or not lease.name.startswith("active-grader-"):
        raise ValueError("This proof cannot release another resource class")
    return not lease.exists() or lease.read_bytes() != checked(inputs["claim_ref"]).read_bytes()


def validate_reconciliation(ref, inputs):
    proof = load(ref)
    if (proof.get("version") not in {VERSION, "v068-physical-cleanup-reconciliation-r1"}
            or proof.get("resource_key") != inputs["request"]["resource_key"]
            or proof.get("original_quiescence") != inputs["quiet_ref"]
            or proof.get("completion") != inputs["completion_ref"]
            or proof.get("transport") != inputs["transport_ref"]
            or proof.get("physical_quiescence") is not True
            or proof.get("CA_final_identity_recovered") is not False
            or proof.get("original_scoring_status_unchanged") != inputs["receipt_status"]
            or proof.get("original_records_overwritten") is not False):
        raise ValueError("Physical reconciliation does not bind the untouched scoring evidence")
    if proof["version"] == "v068-physical-cleanup-reconciliation-r1":
        observation = proof.get("fresh_read_only_Docker_inspection", {})
        if (inputs["container_ids"] != [proof.get("container_id")]
                or observation.get("exists") is not False or observation.get("status") != 404):
            raise ValueError("The historical exact owned object was not proven absent")
    else:
        observations = proof.get("inspections", [])
        if (proof.get("original_receipt") != inputs["receipt_ref"]
                or [item.get("container_id") for item in observations] != inputs["container_ids"]
                or any(item.get("exists") is not False or item.get("status") != 404 for item in observations)):
            raise ValueError("A reconciliation omitted original owned objects")
    return proof


class RecoveryGrading:
    def __init__(self, *, guard=None, inspector=None, releaser=None, proof_root=PROOF_ROOT,
                 original_reconciliations=None, base=None):
        self.guard = guard or _default_guard
        self.inspector = inspector or read_only_inspect
        self.releaser = releaser or primary.release_resource
        self.proof_root = Path(proof_root)
        self.base = base or original_grading()
        self.reconciliations = dict(original_reconciliations if original_reconciliations is not None else {
            "control-psf__requests-1921-" + kind: reference(ORIGINAL_RECONCILIATIONS / (kind + ".json"))
            for kind in ("gold", "empty") if (ORIGINAL_RECONCILIATIONS / (kind + ".json")).exists()})
        self.last_cleanup_failure = None

    def __getattr__(self, name):
        return getattr(self.base, name)

    def run_request(self, request_ref, stop_event=None):
        request = load(request_ref)
        self.guard("v068.run", instance_id=request["instance_id"])
        namespace = dict(vars(self.base))
        def fixed_python(arguments):
            if arguments[:2] != ["-m", "proworksim.software_benchmark_scorer_v066"]:
                raise ValueError("Only the declared bounded scorer command may be redirected")
            return self.base.fixed_python(["-m", "proworksim.software_benchmark_grading_recovery_v068", *arguments[2:]])
        namespace["fixed_python"] = fixed_python
        return private_function(self.base.run_request, namespace)(request_ref, stop_event=stop_event)

    def trustworthy_cleanup(self, request_ref):
        if self.base.trustworthy_cleanup(request_ref):
            return True
        try:
            inputs = physical_inputs(request_ref)
            key = inputs["request"]["resource_key"]
            path = self.proof_root / (key + ".json")
            existing = self.reconciliations.get(key) or (reference(path) if path.exists() else None)
            if existing:
                validate_reconciliation(existing, inputs)
                if released_claim(inputs):
                    return True
            self.guard("v068.run", instance_id=inputs["request"]["instance_id"])
            if existing is None:
                started = time.time()
                observations = [self.inspector(identity, configuration=inputs["configuration"])
                                for identity in inputs["container_ids"]]
                validate_absent(observations, inputs, started)
                value = {"version": VERSION, "resource_key": key, "recorded_unix": time.time(),
                    "original_quiescence": inputs["quiet_ref"], "completion": inputs["completion_ref"],
                    "transport": inputs["transport_ref"], "claim": inputs["claim_ref"],
                    "initial_container": inputs["initial_ref"], "inspections": observations,
                    "physical_quiescence": True, "CA_final_identity_recovered": False,
                    "original_scoring_status_unchanged": inputs["receipt_status"],
                    "original_receipt": inputs["receipt_ref"], "scoring_evidence_recovered": False,
                    "original_records_overwritten": False, "other_objects_changed": False,
                    "delete_or_stop_calls": 0}
                self.proof_root.mkdir(parents=True, exist_ok=True)
                existing = write_new(path, value)
            self.releaser(inputs["claim_ref"], quiescent=True)
            if not released_claim(inputs):
                raise ValueError("The owned reservation did not finish releasing")
            release_path = self.proof_root / (key + "-reservation-release.json")
            if not release_path.exists():
                write_new(release_path, {"version": VERSION, "proof": existing,
                    "claim": inputs["claim_ref"], "released": True, "no_container_delete_or_stop_performed": True})
            return True
        except Exception as error:
            self.last_cleanup_failure = {"type": type(error).__name__, "message": str(error)}
            return False


@lru_cache(maxsize=1)
def default_grading():
    return RecoveryGrading()


def run_request(request_ref, stop_event=None):
    return default_grading().run_request(request_ref, stop_event=stop_event)


def trustworthy_cleanup(request_ref):
    return default_grading().trustworthy_cleanup(request_ref)


def prepare_score(result_ref, *, endpoint="code"):
    return default_grading().prepare_score(result_ref, endpoint=endpoint)


def delivery_disposition(result_ref, code_request_ref=None):
    return default_grading().delivery_disposition(result_ref, code_request_ref)


def qualify(task):
    return default_grading().qualify(task)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    result = score_request(json.loads(parser.parse_args().request.read_bytes()))
    print(json.dumps({key: result[key] for key in ("resource_key", "status", "resolved")}))
