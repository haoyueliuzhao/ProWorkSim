"""S1/FREE2/REVIEW2 controller with exact local content accounting; no host authority."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback


def _transport_module():
    path = Path(__file__).resolve().with_name('run_fixed_organization_controller_v132.py')
    if not path.is_file():
        path = Path(__file__).resolve().parent/'project/tools/run_fixed_organization_controller_v132.py'
    spec = importlib.util.spec_from_file_location('_v141_unchanged_managed_rpc', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_transport = _transport_module()
ManagedRPC = _transport.ManagedRPC
initial_sync_preflight = _transport.initial_sync_preflight
install_deadline = _transport.install_deadline
copy_registry = _transport.copy_registry


def validate_config(config):
    from proworksim.software_benchmark_alignment_contract_v146 import validate_controller_identity
    from proworksim.software_benchmark_content_tokenizer_v141 import validate_descriptor
    allowed = {'version','slot_id','source_slot_id','seed','condition_id','organization_id',
        'group_id','fixed_members','member_count','execution_arm','model_key','configuration',
        'public_task','ref_endpoint','model_identity_value','output','start','ready','diagnostic',
        'measurement_kind','public_context','public_environment','lifecycle_deadline',
        'maximum_lifecycle_seconds','file_policy','dataset_revision','gitlinks','public_test_entry',
        'execution_alignment','public_test_contract_sha256','public_test_result_revision',
        'public_test_files_sha256','role_contract_version','role_catalog_sha256','content_tokenizer'}
    if (set(config)-allowed or config.get('version') != 'v146-role-baseline-controller-r1'
            or not str(config.get('slot_id','')).startswith('v146:')
            or config.get('execution_arm') != 'PROJECT' or config.get('model_key') != 'DEEPSEEK'
            or config.get('output') != '/pws/output' or config.get('start') != '/pws/control/start.json'
            or config.get('ready') != '/pws/control/actor-ready.json'
            or config.get('configuration',{}).get('path') != '/pws/control/condition.json'
            or type(config.get('diagnostic')) is not bool
            or config.get('measurement_kind') != ('zero_model_diagnostic' if config.get('diagnostic') else 'full_verified_comparison')
            or set(config.get('public_task',{})) != {'instance_id','repo','base_commit','problem_statement'}
            or set(config.get('public_context',{})) != {'version','visible_text','visible_facts'}
            or not isinstance(config.get('dataset_revision'),str)):
        raise ValueError('Controller requires the exact new public task and private layout')
    validate_descriptor(config.get('content_tokenizer'))
    return validate_controller_identity(config,'PROJECT')


def validate_ready(config, ready):
    from proworksim.software_benchmark_runtime_inputs_v141 import PUBLIC_FILES, RESULT_REVISION
    from proworksim import software_role_baseline_contract_v141 as roles
    expected = {'public_test_result_revision': RESULT_REVISION,
        'role_contract_version': roles.VERSION, 'role_catalog_sha256': roles.catalog_sha256(),
        'public_test_selection_revision': 'v110-public-test-selection-r1',
        **{key: config[key] for key in ('organization_id','fixed_members','member_count',
            'public_test_contract_sha256','public_test_files_sha256')}}
    if (any(ready.get(key) != value for key,value in expected.items())
            or set(ready.get('public_test_files_sha256',{})) != set(PUBLIC_FILES)):
        raise ValueError('Actor ready differs from the current role and runtime file binding')
    return ready


def load_content_counter(config):
    from proworksim.software_benchmark_content_tokenizer_v141 import load_counter
    return load_counter(config['content_tokenizer'])


def process_resource_peak():
    import resource
    return {'source': 'resource.getrusage(RUSAGE_SELF).ru_maxrss',
        'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
        'scope': 'current_controller_process', 'measured': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    config = validate_config(json.loads(parser.parse_args().config.read_bytes()))
    if os.getpid() != 1 or not Path("/testbed").is_dir():
        raise ValueError("Managed controller must be PID1 with the read-only actual actor checkout")
    install_deadline(config)
    output = Path(config["output"])
    os.environ.update(
        OH_PERSISTENCE_DIR=str(output / "empty-user-config"),
        OPENHANDS_SUPPRESS_BANNER="1",
        LITELLM_LOCAL_MODEL_COST_MAP="True",
    )
    from proworksim import software_role_baseline_runtime_v141 as managed
    from proworksim import software_role_baseline_world_v141 as world
    from proworksim.software_benchmark_candidates_v054 import checked, write_new
    from proworksim.software_benchmark_managed_actor_v110 import make_delta, validate_public_entry
    from proworksim.software_benchmark_project_closure_v141 import export_managed_closure
    from proworksim.software_benchmark_alignment_contract_v146 import (
        validate_condition,
        shared_strategy,
    )
    from proworksim.software_benchmark_model_fifo_v064 import FifoModelTransport
    from proworksim.software_benchmark_alignment_contract_v146 import initial_message
    from proworksim.software_role_baseline_runtime_v141 import run_fragment, close_runtime
    from proworksim.software_calibration_collector_v051 import budget_snapshot
    from proworksim.software_organization_runtime_v047 import DispatchDeadline
    from proworksim.repository_sources_v054 import capture_repository, normalize_policy
    from proworksim.harness_port import HarnessPort
    from proworksim.storage import atomic_write, digest, json_bytes

    condition = json.loads(checked(config["configuration"]).read_bytes())
    limits = validate_condition(condition)
    if condition["arm"] != "PROJECT" or condition["model_key"] != config["model_key"]:
        raise ValueError("Managed condition identity changed")
    ready = json.loads(Path(config["ready"]).read_bytes())
    from proworksim.software_benchmark_public_tests_v110 import VERSION as PUBLIC_TEST_VERSION

    if (
        ready.get("public_test_result_revision") != "v141-session-bound-public-test-execution-r1"
        or ready.get("public_test_selection_revision") != PUBLIC_TEST_VERSION
        or ready.get("public_test_contract_sha256") != config["public_test_contract_sha256"]
    ):
        raise ValueError("The managed actor lacks the same selected-public-test contract")
    validate_ready(config, ready)
    content_counter, counter_metadata = load_content_counter(config)
    entry = validate_public_entry(
        config["public_test_entry"],
        instance_id=config["public_task"]["instance_id"],
        public_python=config["public_environment"]["public_python"],
    )
    if ready.get("public_test_entry_sha256") != digest(json_bytes(entry)):
        raise ValueError("Actor and controller must use the identical public test entrypoint")
    write_new(
        output / "controller-ready.json",
        {
            "trusted_SDK_imports_complete": True,
            "content_tokenizer": counter_metadata,
            "version": config["version"],
            "model_calls": 0,
            "tool_calls": 0,
            "managed_interface_revision": managed.REPAIR_REVISION,
            "thinking": False,
            "output_budget_policy": "v105-same-arm-remaining-output-reservation-r1",
        },
    )
    until = time.monotonic() + 120
    while not Path(config["start"]).exists():
        if time.monotonic() >= until:
            raise TimeoutError("Host did not admit the new controller before startup timeout")
        time.sleep(0.05)
    start = json.loads(Path(config["start"]).read_bytes())
    if start.get("guard_path") != "/pws/output/guard.json" or any(
        (
            not isinstance(start.get(key), (int, float)) or not math.isfinite(start[key])
            for key in ("started", "soft_at", "hard_at")
        )
    ):
        raise ValueError("Controller start lacks the exact private guard and finite deadlines")
    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    deadline.started = deadline.last_clock = start["started"]
    deadline.soft_at, deadline.hard_at = (start["soft_at"], start["hard_at"])
    result = {
        "version": config["version"],
        "arm": "PROJECT",
        "model_key": config["model_key"],
        "managed_interface_revision": managed.REPAIR_REVISION,
        "thinking": False,
        "output_budget_policy": "v105-same-arm-remaining-output-reservation-r1",
        "closure_revision": "v141-role-baseline-member001-dual-endpoint-closure-r1",
        "condition_id": condition["condition_id"],
        "slot_id": config["slot_id"],
        "source_slot_id": config["source_slot_id"],
        "execution_arm": "PROJECT",
        "measurement_kind": config["measurement_kind"],
        "status": "running",
        "preparation_only": config["diagnostic"],
        "hidden_feedback_received": False,
        "automatic_retry": False,
        "model_key_present": False,
        "execution_alignment": shared_strategy(config["organization_id"]),
        "organization_id": config["organization_id"],
        "group_id": config["group_id"],
        "fixed_members": list(config["fixed_members"]),
    }
    runtime = adapter = owner = rpc = transport = None
    try:
        rpc = ManagedRPC(
            ready,
            reader=sys.stdin,
            writer=sys.stdout,
            directory=output / "managed-actor-rpc",
            hard_at=start["hard_at"],
        )
        policy = normalize_policy(config.get("file_policy"))
        if ready.get("file_policy") != policy:
            raise ValueError("Actor and controller baseline access policy differs")
        manifest = capture_repository(
            "/testbed",
            output / "source-snapshot",
            task_id=config["public_task"]["instance_id"],
            problem_statement=config["public_task"]["problem_statement"],
            source_identity={
                **{
                    key: config["public_task"][key]
                    for key in ("instance_id", "repo", "base_commit")
                },
                "dataset_revision": config["dataset_revision"],
            },
            file_policy=policy,
            gitlinks=config.get("gitlinks", []),
        )
        baseline = json.loads((manifest.parent / "initial-tree.json").read_bytes())
        if baseline["tree"]["tree_sha256"] != ready.get("initial_tree_sha256"):
            raise ValueError(
                "The read-only controller view is not the complete actual actor baseline"
            )
        preflight = initial_sync_preflight(
            rpc,
            baseline,
            instance_id=config["public_task"]["instance_id"],
            hard_at=start["hard_at"],
        )
        result["initial_sync_preflight"] = write_new(
            output / "initial-sync-preflight.json", preflight
        )

        def public_test(**payload):
            return rpc.request(
                "managed_public_test",
                make_delta(
                    baseline,
                    payload["files"],
                    payload["entry_metadata"],
                    request=payload["request"],
                ),
            )

        prepared = managed.prepare_case(
            manifest,
            output / "managed-world",
            organization_id=config["organization_id"],
            max_total_tokens=limits["input_plus_output_tokens"],
            public_test_callback=public_test,
            deadline=deadline,
            public_test_entry=entry,
        )
        gateway = HarnessPort(
            world.SoftwareCollaborationPort(
                prepared.world.session("member_001", world.PROJECT), "member_001"
            ),
            "member_001",
            project_id=world.PROJECT,
            public_sink=lambda *_: None,
            world_sink=lambda *_: None,
            harness_sink=lambda *_: None,
        )
        if config["diagnostic"]:
            probe = ".pws-v141-managed-probe"
            if probe in baseline["files"]:
                raise ValueError("The predetermined diagnostic path belongs to the task")
            for i, (name, args) in enumerate((("create_file", {"path": probe, "text": "private-team-probe\n"}),
                    ("search_repository", {"text": "private-team-probe"}), ("delete_file", {"path": probe}),
                    ("delivery_status", {}))):
                value = gateway.call(name, request_key=f"diagnostic-{i}", association={}, **args)
                if value.get("ok") is not True:
                    raise RuntimeError("Fixed-team zero-model control failed: " + name)
            def post(*_args, **_kwargs):
                raise RuntimeError("No model or tokenization request is authorized in the zero-model diagnostic")
        else:
            transport = FifoModelTransport(config["ref_endpoint"])
            post = transport.post
        owner = managed.build_team_owner(post, organization_id=config["organization_id"],
            slot_id=config["slot_id"], condition_id=condition["condition_id"],
            folder=output / "model-ledger", deadline=deadline,
            identity={"policy_version": "v141-role-baseline-broker-model",
                "model_key": config["model_key"], "model_identity": config["model_identity_value"],
                "trained_adapter_loaded": False},
            observation_token_counter=content_counter,
            observation_tokenizer_id=counter_metadata["tokenizer_id"], require_content_counter=True)
        adapter = owner.adapter
        runtime, _, _ = managed.build_runtime(
            owner,
            prepared,
            output / "managed-runtime",
            deadline=deadline,
            public_initial_message=initial_message(
                config["public_task"]["problem_statement"],
                public_context=config["public_context"]["visible_text"],
            ),
        )
        actual_tools = {member: [dict(type="function", function=tool) for tool in worker.definitions]
                        for member, worker in runtime.policies.items()}
        expected_tools = managed.prepare_schema_inventory()["schemas"][config["organization_id"]]
        if actual_tools != expected_tools:
            raise ValueError("Actual member SDK schemas differ from frozen broker admission")
        private_sessions = {member: str(worker.conversation.id) for member, worker in runtime.policies.items()}
        registry = prepared.world._software()["registry"]
        if (list(registry) != config["fixed_members"] or len(set(private_sessions.values())) != config["member_count"]
                or any(row["status"] != "live" for row in registry.values())):
            raise ValueError("Actual fixed registry or private SDK session roster differs")
        result.update(actual_member_registry=copy_registry(registry), private_sessions=private_sessions,
                      process_resource_peak=process_resource_peak(), content_tokenizer=counter_metadata)
        if config["diagnostic"]:
            result.update(diagnostic=True, diagnostic_passed=True,
                public_fixture_qualification=ready.get("public_fixture_qualification"), model_calls=0,
                actual_SDK_initialized=True, initialized_managed_tools=actual_tools,
                team_diagnostic={"passed": True, "organization_id": config["organization_id"],
                    "group_id": config["group_id"], "fixed_members": list(config["fixed_members"]),
                    "registry_members": list(registry), "private_session_ids": private_sessions,
                    "model_calls": 0}, ledger=owner.save())
        else:
            boundary = run_fragment(
                prepared,
                runtime,
                on_opportunity=lambda _: atomic_write(
                    output / "managed-live-ledger.json",
                    json_bytes(budget_snapshot(runtime, prepared)),
                ),
            )
            write_new(output / "managed-boundary.json", boundary)
            result.update(
                managed_boundary=boundary,
                managed_budget=budget_snapshot(runtime, prepared),
                closure_reason=boundary["closure_reason"],
                actions=runtime.actions,
                opportunities=runtime.opportunities,
                ledger=adapter.ledger.snapshot(),
                finish_review={member: policy.snapshot() for member, policy in runtime.finish_review_policies.items()},
                cash_censored=boundary["cash_censored"],
                member_usage=adapter.ledger.snapshot()["per_member"],
            )
            if boundary["execution_integrity_failure"] is not None:
                raise RuntimeError("Managed execution integrity failed; no replay")
            if (
                result["ledger"]["complete_actual_tokens"] is None
                or result["ledger"].get("inflight")
                or result["ledger"].get("uncertain_reserved_tokens")
            ):
                raise RuntimeError(
                    "A closed managed controller cannot conceal uncertain provider usage"
                )
        close_runtime(runtime)
        runtime = None
        closure = export_managed_closure(
            prepared, output, slot_id=config["slot_id"], sdk_closed=True
        )
        bundle = closure.pop("terminal_bundle")
        synced = rpc.request(
            "sync_terminal",
            make_delta(
                baseline,
                bundle["files"],
                bundle["entry_metadata"],
                request={
                    "instance_id": config["public_task"]["instance_id"],
                    "source_reference": closure["terminal_source_reference"],
                    "tree_sha256": closure["terminal_tree_sha256"],
                    "hard_deadline_monotonic": start["hard_at"],
                    "hidden_evaluation": False,
                    "arbitrary_command": False,
                },
            ),
        )
        if (
            synced.get("tree_sha256") != closure["terminal_tree_sha256"]
            or synced.get("terminal_locked") is not True
        ):
            raise ValueError(
                "Stopped actor code does not equal the uniquely locked managed terminal tree"
            )
        result.update(
            project_closure=closure,
            terminal_sync=synced,
            actor_close=rpc.close(),
            status="closed",
            actual_managed_fixed_team_runtime=True,
            designated_delivery_member="member_001",
            collaboration_observation=closure["collaboration_observation"],
            best_of_members=False,
            original_Gamma1_permissions=True,
            source_bound_history_summary=True,
            silent_history_sliding=False,
            actual_SDK_worker=True,
            model_can_resume=False,
            process_tree_quiescence_proven=False,
        )
    except BaseException as error:
        result.update(
            status="technical_unknown",
            error={"type": type(error).__name__, "message": str(error)},
            failure_classification=getattr(error, "classification", "technical_unknown"),
            traceback=traceback.format_exc(),
            automatic_retry=False,
        )
    finally:
        if runtime is not None:
            close_runtime(runtime)
        if transport is not None:
            close = getattr(transport, "close", None)
            if close is not None:
                close()
        if owner is not None:
            result["ledger"] = owner.save()
            result["member_usage"] = result["ledger"]["per_member"]
            observation_path = output / "model-ledger/collaboration-observation/summary.json"
            if observation_path.is_file():
                from proworksim.software_benchmark_candidates_v054 import reference
                result["collaboration_observation"] = reference(observation_path)
        write_new(output / "controller-result.json", result)
    if result["status"] != "closed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
