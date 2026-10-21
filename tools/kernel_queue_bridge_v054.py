"""Isolated kernel-revision factory/health bridge; never imports the old package."""
import argparse
import json
from pathlib import Path

from proworksim import software_benchmark_queue_v054 as queue
from proworksim.software_benchmark_candidates_v054 import reference

COMMON = ("version", "execution_authorized", "authorization", "plan", "slots", "registry",
          "scorer_manifest", "capacities", "capacity_admission", "prewarm_policy",
          "residency_protocol", "model_loads", "slot_claims", "automatic_start")


def validate(request):
    bindings = queue.load_ref(request["bindings"])
    queue.validate_frozen(bindings, initial=request.get("initial", False))
    if "original_bindings" in request:
        original = queue.load_ref(request["original_bindings"])
        queue.validate_frozen(original)
        if any(bindings.get(key) != original.get(key) for key in COMMON):
            raise ValueError("Kernel revision changed a common experiment identity")
        for arm in ("REF", "MATCH", "PROJECT"):
            before = queue.load_ref(original["conditions"][arm])
            after = queue.load_ref(bindings["conditions"][arm])
            for value in (before, after):
                value.pop("source_manifest", None)
                value.pop("kernel_optimization_revision", None)
            if before != after:
                raise ValueError("Kernel revision changed the frozen numerical/interface condition")
    from proworksim.software_benchmark_resident_pool_v054 import validate_pool_policy
    policy = validate_pool_policy(bindings["resident_pool_policy"])
    if policy["source_manifest"] != bindings["source_manifest"]:
        raise ValueError("Kernel pool has another source revision")
    source = queue.load_ref(bindings["source_manifest"])
    if reference(__file__) not in source["files"]:
        raise ValueError("Bridge is absent from immutable kernel source manifest")
    return bindings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "healthy", "prepare"))
    parser.add_argument("--request", required=True, type=Path)
    args = parser.parse_args(argv)
    request = json.loads(args.request.read_text())
    bindings = validate(request)
    if args.command == "validate":
        result = {"bindings": request["bindings"], "source_manifest": bindings["source_manifest"],
                  "pool_policy": bindings["resident_pool_policy"], "common_identities_unchanged": True}
    elif args.command == "healthy":
        from proworksim.software_benchmark_deferred_pool_v054 import healthy_residents
        result = healthy_residents(bindings["resident_pool_policy"])
    else:
        from proworksim.software_benchmark_service_factory_v054 import build_service
        from proworksim.software_benchmark_slot_factory_v054 import build_slot_config
        slot, observed, root = request["slot"], request["observed"], Path(request["root"])
        declaration = observed["declaration"]
        if slot["arm"] not in {"MATCH", "PROJECT"} or declaration["gpu_index"] != 6:
            raise ValueError("Only GPU6 MATCH/PROJECT migration is authorized")
        service = build_service(arm=slot["arm"], capacity_reference=bindings["capacities"]["MATCH"],
            card={"index": 6, "uuid": declaration["gpu_uuid"],
                  "admission": "immutable_pool_registration_and_live_resident"},
            directory=root / "service", resident_reference=observed["declaration_reference"],
            registration_reference=observed["registration"],
            pool_policy_reference=bindings["resident_pool_policy"])
        config = build_slot_config(slot_id=slot["slot_id"], condition_reference=bindings["conditions"][slot["arm"]],
            model_service=queue.load_ref(service), registry_reference=bindings["registry"],
            scorer_manifest_reference=bindings["scorer_manifest"], output=root / "config.json",
            authorization=bindings["authorization"], prewarm_policy_reference=bindings["prewarm_policy"])
        result = {"service": service, "config": config}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
