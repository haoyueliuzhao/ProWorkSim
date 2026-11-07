"""Fresh role-pilot scoring with task-local qualification and exact candidates.

Unchanged non-Requests environments reuse checked control evidence. The four
Requests tasks and pytest10081 need new controls after their declared repairs.
Missing preparation leaves that issue pending, never cancels independent work.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import inspect
import json
from pathlib import Path
from types import FunctionType

from . import software_benchmark_grading_v105 as base
from . import software_benchmark_grading_v131 as prior
from . import software_benchmark_grading_v143 as qualified_prior
from . import software_benchmark_scope_v146 as scope
from . import software_benchmark_environment_v141 as current_environment
from . import software_benchmark_grading_repairs_v141 as repair
from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_expansion_episode_v069 import clone_namespace, clone_function

VERSION = "v146-role-pilot-official-scoring-r1"
REUSE_VERSION = "v146-unchanged-official-environment-control-reuse-r1"
MODULE = __name__
TLS_TASKS = frozenset({"psf__requests-1766", "psf__requests-1921"})
FRESH_CONTROL_TASKS = frozenset()
OFFLINE_BUILD_PLAN = scope.BATCH_ROOT/"pytest10081-offline-build-plan.json"
_namespace = clone_namespace(base, scope=scope, VERSION=VERSION, REUSE_VERSION=REUSE_VERSION,
                             MODULE=MODULE, __file__=__file__)
_parent_scorer = _namespace["scorer"]
_parent_host = _namespace["host"]


def control_key(task, kind):
    if kind not in {"gold", "empty"}:
        raise ValueError("Only an unused declared gold/empty control is permitted")
    return "control-v142-"+task+"-"+kind


def private_environment(policy):
    endpoint = reference(scope.NETWORK_RESOLUTION_FILE)
    def resolution_validator(resolution_ref, *, scope_ref, expected_source):
        if (resolution_ref != endpoint or scope_ref != reference(scope.__file__)
                or expected_source != 'v142_current_DNS_and_bounded_endpoint_probe'):
            raise ValueError('The recovery may only reuse the original exact public endpoint')
        scope.validate_original_probe_reuse()
        return current_environment.validate_resolution(resolution_ref,
            scope_ref=reference(qualified_prior.scope.previous.__file__), expected_source=expected_source)
    factory = clone_function(current_environment.cold_environment,
        {**current_environment.cold_environment.__globals__, 'validate_resolution':resolution_validator,
         '__file__':__file__})
    return factory(policy, scope_ref=reference(scope.__file__),
        directory=scope.COORDINATOR_ROOT/"provider-bindings/environments", resolution_ref=endpoint)


def validate_transport_evidence(receipt, quiet, observed, identity, folder, **kwargs):
    from . import software_benchmark_environment_v116 as historical
    scope.validate_original_probe_reuse()
    validator = clone_function(historical.validate_transport_evidence,
        {**historical.validate_transport_evidence.__globals__, 'scope':scope})
    result = validator(receipt, quiet, observed, identity, folder, **kwargs)
    for row in result.get('connections', []):
        if row.get('outcome') == 'tcp_eof' and not all(row.get(key) is True for key in
                ('client_eof_observed','remote_eof_observed','tcp_completion_evidence')):
            raise ValueError('Clean TCP closure lacks actual two-sided EOF evidence')
    return result


def _fresh_validator(namespace):
    source = inspect.getsource(base.original.validate_qualification)
    edits = {'"control-" + task + "-" + kind': '"control-v142-" + task + "-" + kind',
        'from .software_benchmark_grading_qualification_v060 import validate_transport_evidence':
        'from .software_benchmark_grading_v146 import validate_transport_evidence'}
    for old, new in edits.items():
        if source.count(old) != 1:
            raise ValueError("The concrete official control validator changed")
        source = source.replace(old, new)
    compiled = {}
    exec(compile(source, __file__+":actual-control-validator", "exec"), namespace, compiled)
    native = compiled["validate_qualification"]

    def validate(ref, config, plan_ref):
        value = scope.load(ref)
        if value.get("version") == REUSE_VERSION:
            if config["instance_id"] in FRESH_CONTROL_TASKS:
                raise ValueError("A revised environment cannot reuse an old control pair")
            expected = reuse_value(config["instance_id"], value["current_manifest"], scope.load(plan_ref))
            if value != expected or value["plan"] != plan_ref:
                raise ValueError("The original actual qualification or exact equivalence changed")
            return value
        if value.get("version") != VERSION:
            raise ValueError("Only this scope's actual controls or exact checked reuse may qualify")
        return native(ref, config, plan_ref)
    return validate


def scorer(policy, *, manifest_provider=None):
    from . import software_benchmark_project_closure_v141 as closure
    value = _parent_scorer(policy, manifest_provider=manifest_provider)
    namespace = value.validate_request.__globals__
    prior.bind_group_identity(namespace)
    namespace.update(validate_delivery_evidence=closure.validate_delivery_evidence, MAX_GRADERS=scope.MAX_GRADERS)
    namespace["validate_request"] = prior._lane_validator(namespace)
    namespace["validate_qualification"] = _fresh_validator(namespace)
    original_planned = namespace["_planned"]

    def planned(request):
        plan, resource, config = original_planned(request)
        if config["instance_id"] == repair.PYTEST_TASK:
            if not OFFLINE_BUILD_PLAN.is_file():
                raise ValueError("pytest10081 remains pending until its actual offline build closure is frozen")
            repair.validate_offline_plan(reference(OFFLINE_BUILD_PLAN))
        return plan, resource, config

    namespace["_planned"] = planned
    inherited_manifest = namespace["installation_manifest"]

    def installation_manifest():
        manifest = inherited_manifest()
        if manifest_provider is not None:
            return manifest
        return {**manifest, "managed_delivery_validator": reference(closure.__file__),
            "deployment_repair_adapter": reference(__file__), "new_resource_scope": reference(scope.__file__),
            "original_scoring_adapter": reference(base.original.__file__),
            "selective_reset_tasks": sorted(prior.reset_binding.reset.TASKS),
            "selective_reset_binding": reference(prior.reset_binding.__file__),
            "TLS_lifecycle_binding": reference(prior.lifecycle.__file__),
            "fresh_gold_empty_required_for": sorted(FRESH_CONTROL_TASKS),
            "unchanged_other_controls_require_explicit_evidence_equivalence": True,
            "grading_lane_count": scope.MAX_GRADERS, "aggregate_container_parent": None,
            "system_parent_slice_created": False, "official_scoring_rules_and_test_patch_changed": False,
            "scoring_environment_binding": reference(current_environment.__file__),
            "offline_build_dependency_adapter": reference(repair.__file__),
            "offline_build_plan": reference(OFFLINE_BUILD_PLAN) if OFFLINE_BUILD_PLAN.is_file() else None,
            "candidate_reselection": False, "actual_runtime_qualification_pending": True}

    writer_ns = {**prior.bind_receipt_writer.__globals__, "scope": scope, "VERSION": VERSION}
    writer_ns["classify_http_502"] = clone_function(prior.classify_http_502, writer_ns)
    namespace["write_new"] = clone_function(prior.bind_receipt_writer, writer_ns)(namespace)
    namespace["cleanup"] = clone_function(prior.bind_physical_cleanup,
        {**prior.bind_physical_cleanup.__globals__, "VERSION": VERSION})(namespace)
    namespace["installation_manifest"] = installation_manifest
    # Synchronize module fields before any adapter copies the live namespace.
    for key in ("_planned", "_generation_result", "validate_candidate_request", "validate_request",
                "validate_qualification", "validate_delivery_evidence", "installation_manifest", "write_new", "cleanup"):
        setattr(value, key, namespace[key])
    if OFFLINE_BUILD_PLAN.is_file():
        repair.bind_offline_build_scorer(value, reference(OFFLINE_BUILD_PLAN))
    dataset = json.loads(checked(reference(scope.ROOT/"artifacts/software-benchmark-v054/source/trusted-evaluation.json")).read_bytes())
    reset = prior.reset_binding.bind_scorer(value,
        [row for row in dataset if row["instance_id"] in prior.reset_binding.reset.TASKS], passthrough_tasks=())
    concrete = namespace["_score"]

    def selected_score(request, resource, config, tracking):
        if config["instance_id"] in prior.reset_binding.reset.TASKS:
            return reset._score(request, resource, config, tracking)
        return concrete(request, resource, config, tracking)

    namespace["_score"] = value._score = selected_score
    value._v146_concrete_score = concrete
    value._v146_reset_scorer = reset
    return value


@lru_cache(maxsize=1)
def original_qualified_scorer():
    return prior.scorer(prior.scope.dispatch_view(prior.scope.require_grading_allowed))


def reuse_value(task, manifest_ref, plan):
    old_plan_ref = reference(qualified_prior.scope.PLAN_FILE)
    old_plan = scope.load(old_plan_ref)
    if task not in plan['environments'] or task not in old_plan['environments']:
        raise ValueError('Recovery cannot add a new task environment')
    before = scope.load(old_plan['environments'][task]['configuration'])
    after = scope.load(plan['environments'][task]['configuration'])
    if base.environment_identity(before) != base.environment_identity(after):
        raise ValueError('Original task image/baseline/hidden scorer identity changed')
    old_ref = reference(qualified_prior.scope.COORDINATOR_ROOT/'qualifications'/(task+'.json'))
    old_scorer = qualified_prior.scorer(qualified_prior.scope.dispatch_view(qualified_prior.scope.require_grading_allowed))
    old_scorer.validate_qualification(old_ref, before, old_plan_ref)
    old_manifest_ref = reference(qualified_prior.scope.COORDINATOR_ROOT/'scorer-manifest.json')
    old_manifest, new_manifest = scope.load(old_manifest_ref), scope.load(manifest_ref)
    keys = ('parent','archive_adapter','limits','cap_add','cap_drop','no_new_privileges',
            'requests_capabilities_by_task','official_tests_and_scoring_rules_changed',
            'host_namespace_mount_or_daemon_operations','original_scoring_adapter',
            'selective_reset_binding','selective_reset_tasks','TLS_lifecycle_binding',
            'host_poll_adapter','managed_delivery_validator','scoring_environment_binding')
    if any(old_manifest.get(k) != new_manifest.get(k) for k in keys):
        raise ValueError('Official evaluator or resource settings changed')
    current = private_environment(scope.dispatch_view(scope.require_grading_allowed))
    old_fields, new_fields = old_scorer.environment.request_fields(task), current.request_fields(task)
    for fields, directory, factory in (
            (old_fields, qualified_prior.scope.COORDINATOR_ROOT/'provider-bindings/environments', reference(qualified_prior.__file__)),
            (new_fields, scope.COORDINATOR_ROOT/'provider-bindings/environments', reference(__file__))):
        if fields.get('environment_revision') is not None:
            value = scope.load(fields['environment_revision'])
            if value.get('binding_directory') != str(directory) or value.get('environment_factory') != factory:
                raise ValueError('Environment binding directory or factory differs from its own scope')
            ignored = {'adapter','policy','transport','legacy_fixture_adapter','dispatch_guard',
                       'authorization_bound_by','version','binding_directory','environment_factory'}
            fields['environment_revision'] = {k:v for k,v in value.items() if k not in ignored}
    if old_fields != new_fields:
        raise ValueError('Effective TLS/public fixture environment differs')
    return {'version':REUSE_VERSION,'instance_id':task,'passed':True,
        'plan':reference(scope.PLAN_FILE),'current_manifest':manifest_ref,
        'original_plan':old_plan_ref,'original_qualification':old_ref,
        'original_manifest':old_manifest_ref,'original_configuration':old_plan['environments'][task]['configuration'],
        'new_configuration':plan['environments'][task]['configuration'],
        'unchanged_manifest_fields':list(keys),'same_task_image_baseline_official_tests_and_scoring_rules':True,
        'model_calls':0,'Docker_operations':0,'new_controls':0}


def prepare_environment_qualifications_local():
    plan_ref = reference(scope.PLAN_FILE)
    plan = scope.validate_plan(scope.load(plan_ref))
    scoring = scorer(scope.dispatch_view(scope.require_grading_allowed))
    scoring.environment.prepare()
    manifest = scope.retain(scope.COORDINATOR_ROOT/"scorer-manifest.json", scoring.installation_manifest())
    qualifications, controls, pending = {}, [], {}
    for task in sorted(plan["environments"]):
        try:
            if task not in FRESH_CONTROL_TASKS:
                value = reuse_value(task, manifest, plan)
                ref = scope.retain(scope.COORDINATOR_ROOT/"qualifications"/(task+".json"), value)
                qualifications[task] = {"status": "qualified", "qualification": ref, "reused_controls": True}
                continue
            if task == repair.PYTEST_TASK:
                repair.validate_offline_plan(reference(OFFLINE_BUILD_PLAN))
            fields = scoring.environment.request_fields(task)
            for kind in ("gold", "empty"):
                key = control_key(task, kind)
                resource = plan["resources"].get(key, {})
                if (resource.get("role") != "control" or resource.get("instance_id") != task
                        or resource.get("patch_kind") != kind):
                    raise ValueError("No exact unused new control identity")
                request = {"version": VERSION, "resource_key": key, "instance_id": task, "slot_id": None,
                    "plan": plan_ref, "configuration": plan["environments"][task]["configuration"],
                    "patch_kind": kind, "limits": scoring.LIMITS, "scorer_manifest": manifest,
                    "cpuset_cpus": None, "directory": str(scope.GRADING_ROOT/key), "candidate_lock": None, **fields}
                controls.append(scope.retain(scope.GRADING_ROOT/key/"request.json", request))
        except (ValueError, KeyError, OSError) as error:
            pending[task] = {"status": "environment_preparation_pending", "error": type(error).__name__+": "+str(error),
                             "new_controls_automatically_created_for_missing_reuse_evidence": False}
    value = {"version": VERSION, "qualifications": qualifications, "controls": controls,
             "reuse_failures": pending, "pending_environments": pending, "model_calls": 0, "Docker_operations": 0,
             "unqualified_tasks_cannot_start_generation": True, "automatic_retry": False}
    initial = scope.COORDINATOR_ROOT/"qualification-preparation.json"
    # The current DNS probe can legitimately become available after the cold
    # offline preparation. Retain that first record; append an immutable new
    # preparation identity instead of overwriting or blocking unrelated work.
    if initial.exists() and scope.load(reference(initial)) != value:
        identity = base.hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        target = scope.COORDINATOR_ROOT/"qualification-preparations"/(identity+".json")
    else:
        target = initial
    ref = scope.retain(target, value)
    return {**value, "preparation_reference": ref}


def host(policy, scoring):
    # Reuse the exact group-bearing request builder, then replace its local
    # qualification body so all five revised tasks require this scope's pair.
    helper_ns = {**prior.host.__globals__, "scope": scope, "VERSION": VERSION,
                 "_parent_host": _parent_host, "control_key": control_key,
                 "FRESH_CONTROL_TASKS": FRESH_CONTROL_TASKS}
    value = clone_function(prior.host, helper_ns)(policy, scoring)
    # The retry has a new scorer/cache identity but the same exact candidate.
    source = inspect.getsource(value.delivery_disposition)
    old = 'request.get("resource_key") != "score-" + str(row["slot_index"])'
    new = ('request.get("resource_key") not in {"score-" + str(row["slot_index"]), '
           '"score-retry-" + str(row["slot_index"])}')
    if source.count(old) != 1:
        raise ValueError('The exact same-tree delivery reuse identity check changed')
    namespace = {**value.delivery_disposition.__globals__}
    compiled = {}
    exec(compile(source.replace(old, new), __file__+':same-candidate-score-retry', 'exec'), namespace, compiled)
    value.delivery_disposition = compiled['delivery_disposition']

    def prepare_score_retry(request_ref):
        request = scope.load(request_ref)
        key = request['resource_key']
        if '-retry-' in key or not (key.startswith('score-') or key.startswith('delivery-score-')):
            raise ValueError('Only one supplemental scoring attempt is permitted')
        folder = Path(request['directory'])
        quiet = scope.load(reference(folder/'quiescence.json'))
        if quiet.get('quiescent') is not True or quiet.get('cleanup_errors') != []:
            raise PermissionError('Old scoring writers must be removed before retry')
        if (folder/'receipt.json').exists():
            receipt = scope.load(reference(folder/'receipt.json'))
            if receipt.get('status') == 'official_report' and type(receipt.get('resolved')) is bool:
                raise ValueError('Normal test failure or success must never be rescored')
        prefix, index = key.rsplit('-', 1)
        retry_key = prefix+'-retry-'+index
        plan = scope.load(reference(scope.PLAN_FILE))
        spec = plan['resources'].get(retry_key, {})
        if (spec.get('retry_of_resource_key') != key or spec.get('slot_id') != request['slot_id']
                or spec.get('same_locked_candidate_required') is not True):
            raise PermissionError('No exact unused same-candidate scoring identity')
        revised = {**request, 'resource_key':retry_key, 'directory':str(scope.GRADING_ROOT/retry_key),
                   'retry_of_request':request_ref}
        prior_completion = (reference(folder/'receipt.json') if (folder/'receipt.json').exists()
                            else reference(folder/'completion.json'))
        scope.retain(scope.API_ROOT/'score-retry-admissions'/(retry_key+'.json'), {
            'version':scope.VERSION, 'resource_key':retry_key, 'slot_id':request['slot_id'],
            'technical_scoring_failure':True, 'same_candidate':True,
            'prior_request':request_ref, 'prior_completion':prior_completion})
        return scope.retain(scope.GRADING_ROOT/retry_key/'request.json', revised)

    value.prepare_score_retry = prepare_score_retry
    return value


def score_request(request, *, validate_only=False):
    scope.require_grading_allowed("v146.run", slot_id=request.get("slot_id"), instance_id=request["instance_id"])
    scoring = scorer(scope.dispatch_view(scope.require_grading_allowed))
    folder = Path(request["directory"]).resolve()
    if folder != scope.GRADING_ROOT/request["resource_key"] or (folder/"quiescence.json").exists():
        raise ValueError("Foreign or already consumed official scoring identity")
    execution = scoring.resolve_execution_request(request)
    from .software_benchmark_rescore_v095 import host_limits
    limits = host_limits(execution["cpuset_cpus"])
    if validate_only:
        scoring.validate_request(execution)
        return {"passed": True, "actual_original_validate_request_executed": True,
                "host_limits": limits, "Docker_operations": 0, "model_calls": 0}
    write_new(folder/"v146-host-limits.json", limits)
    return scoring.score_request(request)


def run_request(self, request_ref, stop_event=None):
    namespace = {**prior.run_request.__globals__, "scope": scope,
                 "FRESH_CONTROL_TASKS": TLS_TASKS, "_namespace": _namespace}
    source = inspect.getsource(prior.run_request)
    if source.count("'v131.run'") != 1:
        raise ValueError("The exact child scoring guard changed")
    source = source.replace("'v131.run'", "'v146.run'")
    compiled = {}
    exec(compile(source, __file__+":new-scoring-child", "exec"), namespace, compiled)
    return compiled["run_request"](self, request_ref, stop_event=stop_event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--manifest", action="store_true")
    group.add_argument("--prepare-qualifications", action="store_true")
    group.add_argument("--request", type=Path)
    group.add_argument("--validate-request", type=Path)
    args = parser.parse_args()
    if args.manifest:
        value = scorer(scope.dispatch_view(scope.require_grading_allowed)).installation_manifest()
    elif args.prepare_qualifications:
        value = prepare_environment_qualifications_local()
    else:
        value = score_request(json.loads((args.request or args.validate_request).read_bytes()),
                              validate_only=args.validate_request is not None)
        if args.request:
            value = {key: value[key] for key in ("resource_key", "status", "resolved")}
    print(json.dumps(value, ensure_ascii=False))


_namespace.update(private_environment=private_environment, scorer=scorer, host=host,
    prepare_environment_qualifications_local=prepare_environment_qualifications_local,
    score_request=score_request, main=main)
_namespace["cold_manifest"] = lru_cache(maxsize=1)(clone_function(base.cold_manifest.__wrapped__, _namespace))
_namespace["Grading"] = type("Grading", (base.Grading,), {name: clone_function(value, _namespace)
    for name, value in vars(base.Grading).items() if isinstance(value, FunctionType)})
_namespace["Grading"].run_request = run_request
globals().update({key: value for key, value in _namespace.items() if not key.startswith("__")})


if __name__ == "__main__":
    main()
