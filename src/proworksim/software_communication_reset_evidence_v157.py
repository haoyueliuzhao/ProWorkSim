"""Read-only exact reuse of the two historical selective-reset control pairs."""
from __future__ import annotations

import json

from .software_benchmark_candidates_v054 import checked, reference
from .software_benchmark_grading_v105 import environment_identity


def read(ref):
    return json.loads(checked(ref).read_bytes())


def verified_reset_controls(task, new_config):
    if task == "astropy__astropy-7336":
        from . import software_benchmark_rescore_v099 as prior
        from . import software_benchmark_test_reset_v099 as mechanism
        plan_ref = reference(prior.RUN_ROOT/"plan.json")
        plan = read(plan_ref)
        context = prior.Context(plan_ref)
        scorer = prior.build_scorer(context)
        qualification_ref = reference(prior.RUN_ROOT/"qualifications"/(task+".json"))
        binding_ref = reference(prior.mechanisms.__file__)
    elif task == "pylint-dev__pylint-6528":
        from . import software_benchmark_grading_recovery_v114 as prior
        from . import software_benchmark_test_reset_v114 as mechanism
        plan_ref = reference(prior.scope.PLAN_FILE)
        plan = read(plan_ref)
        scorer = prior.scorer(prior.scope.dispatch_view(prior.scope.require_grading_allowed))
        qualification_ref = reference(prior.scope.COORDINATOR_ROOT/"qualifications"/(task+".json"))
        binding_ref = reference(prior.reset_binding.__file__)
    else:
        raise ValueError("No selective-reset control is registered for this task")
    old_config_ref = plan["environments"][task]["configuration"]
    old_config = read(old_config_ref)
    if environment_identity(old_config) != environment_identity(new_config):
        raise ValueError("Selective-reset image, official baseline, dataset or scorer inputs changed")
    qualified = scorer.validate_qualification(qualification_ref, old_config, plan_ref)
    details = []
    for control in qualified["controls"]:
        receipt = read(control["receipt"])
        diagnostic = read(receipt["diagnostic_repair"])
        reset = diagnostic.get("test_reset_plans", {}).get(task, {})
        if (diagnostic.get("test_reset_revision") != mechanism.VERSION
                or reset.get("instance_id") != task or reset.get("replaced_reset_commands") != 2
                or any(reset.get(key) is not False for key in (
                    "official_test_patch_changed", "test_commands_changed",
                    "candidate_patch_changed", "grading_rules_changed"))):
            raise ValueError("Successful historical controls lack the exact reset evidence")
        details.append({"patch_kind": control["patch_kind"], "receipt": control["receipt"],
                        "cleanup": control["quiescence"], "diagnostic": receipt["diagnostic_repair"],
                        "repaired_eval_sha256": reset["repaired_eval_sha256"],
                        "official_test_patch_sha256": reset["official_test_patch_sha256"],
                        "upstream_sha256": diagnostic["upstream_sha256"]})
    if (len(details) != 2 or {r["patch_kind"] for r in details} != {"gold", "empty"}
            or len({r["repaired_eval_sha256"] for r in details}) != 1
            or len({r["official_test_patch_sha256"] for r in details}) != 1):
        raise ValueError("Both gold and empty must use the same exact reset/test patch")
    return {"version": "v157-verified-historical-selective-reset-pair-r1", "passed": True,
            "instance_id": task, "original_plan": plan_ref,
            "original_configuration": old_config_ref, "original_qualification": qualification_ref,
            "environment_identity": environment_identity(new_config), "controls": details,
            "reset_source": reference(mechanism.__file__), "original_binding_source": binding_ref,
            "new_binding_must_match_these_test_and_eval_hashes": True,
            "model_calls": 0, "Docker_operations": 0, "old_artifacts_changed": False}
