"""New-root CPU controls; scripted reference routes are never model evidence."""
import ast
import copy
import json
import os
from pathlib import Path

import pytest

from proworksim import software_collaboration_v034 as world
from proworksim import software_runtime_v034 as runtime
from proworksim import software_tasks_v034 as source
from proworksim.software_context_v034 import SoftwareContextTransport
from proworksim.storage import atomic_write, json_bytes, read_json
from test_software_v033 import ScriptedCPUOwner


def output(tmp_path, name):
    return Path(os.environ.get("PROWORKSIM_V034_CONTROL_RUN", str(tmp_path))) / name


def returned(trace, api):
    return [row["value"] for row in trace if row["api"] == api and row["returned"]]


@pytest.mark.parametrize("case_id", source.TASK_IDS)
def test_actual_four_program_controls_and_schema_result_dependency(tmp_path, case_id):
    root = output(tmp_path, "program-controls/" + case_id)
    results = {}
    for name, files in source.dependency_controls(case_id).items():
        result = source.assess_files(case_id, files, run_root=root / name)
        atomic_write(root / (name + ".json"), json_bytes(result))
        results[name] = result
    assert all(result["executed"] for result in results.values())
    assert {name: result["passed"] for name, result in results.items()} == {
        "original": False, "shared_api_only": False, "consumer_only": False, "joint_reference": True}
    shared = [check for check in results["shared_api_only"]["independent_acceptance"]["checks"] if check["group"] == "reusable_api"]
    assert shared and all(check["passed"] for check in shared)
    joint = results["joint_reference"]
    assert joint["content_correct"] is joint["required_process_satisfied"] is joint["process_observation_complete"] is True
    witnesses = []
    for check in joint["independent_acceptance"]["checks"]:
        if check["group"] != "consumer":
            continue
        observed = check["observed"]
        api = "models." + ("RecordSchema" if case_id == source.TASK_IDS[0] else "NameSchema")
        loads = returned(observed["source_api_trace"], api + ".load")
        dumps = returned(observed["source_api_trace"], api + ".dump")
        assert loads and dumps
        if case_id == source.TASK_IDS[0]:
            assert observed["value"]["records"] == dumps[0]
            assert observed["value"]["total_quantity"] == sum(row["quantity"] for row in loads[0])
            relation = "consumer records equal actual shared-schema dump; total consumes loaded integer quantities"
        elif check["case_id"].endswith("export"):
            assert observed["value"] == [row["name"] for row in dumps[0]]
            relation = "export consumes the actual shared-schema canonical name results"
        else:
            assert observed["value"] == [index for index, row in enumerate(dumps[0]) if row["name"] == dumps[1]["name"]]
            relation = "search indices equal matches between actual shared-schema row and query results"
        witnesses.append({"case_id": check["case_id"], "relation": relation, "actual_load_results": loads,
                          "actual_dump_results": dumps, "consumer_output": observed["value"], "passed": True})
    assert witnesses
    atomic_write(root / "dependency-witnesses.json", json_bytes({"version": "actual-schema-dependency-controls-v0.34",
        "case_id": case_id, "witnesses": witnesses, "real_model_calls": 0,
        "scope": "Actual sandboxed API results and consumer outputs, beyond side-only failures; no policy support or teaching material."}))


class ReferenceRouteCPUOwner(ScriptedCPUOwner):
    """Emit explicit controller reference tool choices into the real SDK harness."""
    def __init__(self, directory):
        super().__init__(directory)
        self.window_id = "v034-scripted-cpu"
        self.facade.transport = SoftwareContextTransport(self, directory)
        self.script = {}
        self.actions = []
        self.current_slot = None

    def reseed(self, seed, *, label):
        super().reseed(seed, label=label)
        self.current_slot = label
        row = next(row for row in runtime.inventory() if row["slot_id"] == label)
        reference = source.reference_solution(row["case_id"])
        _, material, _ = source._entry(row["case_id"])
        def task(task_id):
            return [("create_task", {"task_id": task_id, "description": "Explicit CPU route witness, not a task supplied to model episodes"}),
                    ("claim_task", {"task_id": task_id})]
        def writes(names):
            return [("write_file", {"path": name, "text": reference[name]}) for name in names]
        done = ("staff_done", {"reason": "Explicit CPU reference route ended"})
        if label.startswith("p1-0"):
            self.script = {"member_a": [*task("CompleteRoot"), *writes(material["editable_paths"]),
                ("run_tests", {}), ("fix_patch", {"task_ids": ["CompleteRoot"], "message": "CPU complete fixed version"}),
                ("submit_integration", {}), done], "member_b": [done]}
        else:
            self.script = {"member_a": [*task("SharedAPI"), *writes(material["shared_api_paths"]),
                ("fix_patch", {"task_ids": ["SharedAPI"], "message": "CPU shared API fixed branch"}), done],
                "member_b": [*task("Consumer"), *writes(material["consumer_paths"]),
                ("integrate_patch", {}), ("run_tests", {}),
                ("fix_patch", {"task_ids": ["Consumer"], "message": "CPU integrated fixed version"}),
                ("submit_integration", {}), done]}

    def complete(self, request, **kwargs):
        response = super().complete(request, **kwargs)
        observation = next(json.loads(message["content"])["observation"] for message in reversed(request["messages"])
                           if message.get("role") == "user" and "observation" in json.loads(message["content"]))
        member = observation["actor_id"]
        name, arguments = self.script[member][0]
        if name == "integrate_patch":
            partner = [patch for patch in observation["patches"] if patch["author"] != member]
            if not partner:
                name, arguments = "staff_wait", {"reason": "CPU branch witness waits for its already-runnable partner publication"}
            else:
                arguments = {"patch_id": partner[-1]["patch_id"]}
                self.script[member].pop(0)
        else:
            self.script[member].pop(0)
        response["body"]["choices"][0]["message"]["tool_calls"][0]["function"] = {"name": name, "arguments": json.dumps(arguments)}
        response["raw_body"] = json.dumps(response["body"])
        self.actions.append({"slot_id": self.current_slot, "member": member, "action": name})
        return response


def test_real_sdk_four_slots_complete_central_and_import_routes_with_budget_margin(tmp_path):
    pytest.importorskip("openhands.sdk")
    root = output(tmp_path, "sdk-routes")
    owner = ReferenceRouteCPUOwner(root / "projection")
    entries = runtime.collect_software_window(owner.facade, runtime.window_spec(owner.window_id), root / "window")
    progress = read_json(root / "window/progress.json")
    assert len(entries) == len(progress) == 4
    assert owner.seeds == [(row["sampling_seed"], row["slot_id"]) for row in runtime.inventory()]
    assert len(read_json(root / "window/initial-team-proofs.json")) == 4
    witnesses = []
    for index, (entry, row) in enumerate(zip(entries, progress, strict=True)):
        assert row["status"] == "closed" and row["record_validity"] is True and row["R"] == 1
        assert row["content_correct"] is row["required_process_satisfied"] is row["process_observation_complete"] is True
        assert entry["training_eligible"] is False and entry["rollout"]["online_scope"]["optimizer_update_allowed"] is False
        counts = row["process_diagnostics"]["counts"]
        assert counts["task_created"] == (1 if index < 2 else 2)
        assert counts["integrate"] == (0 if index < 2 else 1)
        assert counts["patch_fixed"] == (1 if index < 2 else 2)
        assert counts["test"] == counts["submit"] == 1
        budget = row["team_budget"]
        assert budget["model"]["decisions"] <= 20 and budget["model"]["attempts"] <= 20
        assert budget["model"]["charged_tokens"] < 150000 and budget["tests"]["used"] == 1
        assert budget["model"]["held_tokens"] == 0 and budget["model"]["integrity_failure"] is None
        assert all(read_json(root / f"window/slot-{index}/evaluation-guard.json")[key] for key in (
            "learning_unchanged", "rng_restored_exactly", "software_binding_unchanged", "actor_identity_unchanged"))
        witnesses.append({"slot_id": row["slot_id"], "route": "centralized" if index < 2 else "publish_then_explicit_import",
            "case_id": row["case_id"], "R": 1, "counts": counts,
            "team_budget": {"decisions": budget["model"]["decisions"], "attempts": budget["model"]["attempts"],
                "charged_synthetic_tokens": budget["model"]["charged_tokens"], "test_runs": budget["tests"]["used"],
                "remaining_decisions": budget["model"]["remaining_decisions"],
                "remaining_tokens": budget["model"]["available_tokens"], "remaining_test_runs": budget["tests"]["remaining"]},
            "scope": "Real world actions, fixed versions, CPU checks and archival; synthetic reference decisions/tokens only, not current-model success or method support."})
    atomic_write(root / "route-witnesses.json", json_bytes({"version": "new-root-legal-routes-v0.34", "witnesses": witnesses,
        "real_model_calls": 0, "optimizer_steps": 0, "gpu_used": False, "scripted_cpu_responses": len(owner.requests),
        "reference_choices_enter_p1_prompts": False, "reference_choices_enter_training": False}))


def test_process_failure_and_missing_observation_are_distinct_without_regrading_old_tasks():
    expected = {"kind": "return", "value": [], "source_api_used": {"models.NameSchema.load": True}, "source_api_observation_complete": True}
    observed = {"kind": "return", "value": []}
    independent = {"execution": {"executed": True}, "checks": [{"case_id": "explicit_cpu_fixture", "expected": expected, "observed": observed}]}
    public = {"execution": {"executed": True}, "tests": [{"test_id": "explicit_cpu_public", "passed": True}]}
    missing = source.acceptance_dimensions(independent, public)
    assert missing["content_correct"] is True
    assert missing["required_process_satisfied"] is missing["process_observation_complete"] is False
    observed.update(source_api_used={"models.NameSchema.load": False}, source_api_observation_complete=True)
    measured = source.acceptance_dimensions(independent, public)
    assert measured["required_process_satisfied"] is False and measured["process_observation_complete"] is True


def test_new_inventory_and_contracts_are_exact_and_do_not_admit_old_roots(tmp_path):
    rows = runtime.inventory()
    assert [row["slot_id"] for row in rows] == ["p1-0-directory-T", "p1-0-names-T", "p1-1-names-T", "p1-1-directory-T"]
    assert [row["first_member"] for row in rows] == ["member_a", "member_a", "member_b", "member_b"]
    assert runtime._validate_window(runtime.window_spec("explicit-cpu-v034")) == rows
    assert runtime.window_spec("explicit-cpu-v034")["budget"] == {"max_slots": 4, "max_model_calls": 512}
    for case_id in source.TASK_IDS:
        with pytest.raises(ValueError, match="two-executor"):
            world.case_spec(case_id, condition="S")
        files = source.build_case(case_id)["files"]
        assert "acceptance.json" not in files and not any("reference/" in name for name in files)
        changed = copy.deepcopy(files)
        changed["contract.md"] += "\nWeaker requirements\n"
        with pytest.raises(ValueError, match="editable"):
            source._validate_files(case_id, changed)
    with pytest.raises(ValueError, match="new development"):
        world.case_spec("mm-ledger-rootgoal")


def test_integer_outputs_preserve_json_types_in_public_independent_and_content_comparisons():
    node = next(node for node in ast.parse(source._public_driver(source.TASK_IDS[0])).body
                if isinstance(node, ast.FunctionDef) and node.name == "exact_json_equal")
    namespace = {"json": json}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "public_comparison_control", "exec"), namespace)
    public_compare = namespace["exact_json_equal"]
    positive = {"kind": "return", "value": {"records": [{"name": "Oak", "quantity": 1}], "total_quantity": 1}}
    floats = copy.deepcopy(positive)
    floats["value"]["records"][0]["quantity"] = 1.0
    floats["value"]["total_quantity"] = 1.0
    index_expected = {"kind": "return", "value": [1]}
    index_boolean = {"kind": "return", "value": [True]}
    for expected, observed in ((positive, positive), (positive, floats), (index_expected, index_boolean)):
        correct = observed is expected
        assert source.exact_json_equal(source.comparable(observed), expected) is correct
        assert public_compare(source.comparable(observed), expected) is correct
        dimensions = source.acceptance_dimensions(
            {"execution": {"executed": True}, "checks": [{"case_id": "typed_json_cpu_control", "expected": expected, "observed": observed}]},
            {"execution": {"executed": True}, "tests": [{"test_id": "fixed_upstream_cpu_control", "passed": True}]})
        assert dimensions["content_correct"] is correct
    assert positive == floats and index_expected == index_boolean  # Demonstrate the old Python equality ambiguity.


def test_public_feedback_projection_preserves_failures_member_output_and_current_version_guard(tmp_path):
    root = output(tmp_path, "public-feedback")
    prepared = world.build_software_collaboration_case(world.case_spec(), root / "world-case")
    port = world.SoftwareCollaborationPort(prepared.world.session("member_a", world.PROJECT), "member_a")
    def call(name, **arguments):
        response = port.call(name, **arguments)
        assert response["ok"], response
        return response
    call("create_task", task_id="Control", description="Explicit CPU feedback and version-guard control")
    call("claim_task", task_id="Control")
    reference = source.reference_solution(source.TASK_IDS[0])
    for name in ("models.py", "consumer.py"):
        call("write_file", path=name, text=reference[name])
    call("write_file", path="test_member.py", text="print('actual member-authored diagnostic retained')\n")
    before_test = port.call("submit_integration")
    assert not before_test["ok"] and "Run real tests" in before_test["error"]["message"]
    response = call("run_tests")
    shown = response["result"]
    state = prepared.world.store.load()
    event = next(event for event in state["software_events"] if event["kind"] == "test")
    raw = {key: copy.deepcopy(value) for key, value in event.items() if key not in (
        "sequence", "actor_id", "kind", "logical_time", "operation_id", "action_id", "responsibility_snapshot")}
    saved = copy.deepcopy(raw)
    assert source.project_public_test_feedback(raw) == shown and raw == saved
    assert source.project_public_test_feedback(shown) == shown
    assert state["operation_commits"][response["command_id"]]["public_result"]["result"] == shown
    for name in ("upstream_regressions", "public_normal"):
        assert shown["groups"][name]["passed"] is True
        assert all(set(row) == {"test_id", "requirement_group", "status"} for row in shown["groups"][name]["tests"])
    assert "output" not in shown["public_execution"] and "tests" not in shown["public_execution"]
    assert raw["public_execution"]["execution"]["output"]
    member = raw["groups"]["member_tests"]
    assert "actual member-authored diagnostic retained" in member["execution"]["output"]
    assert all(shown["groups"]["member_tests"][key] == value for key, value in member.items())
    assert port.observe()["current_version_test_coverage"]["public_normal"]["passed"] is True
    call("fix_patch", task_ids=["Control"], message="Current tested CPU version")
    call("submit_integration")
    call("write_file", path="consumer.py", text=reference["consumer.py"] + "\n# Untested later version\n")
    call("fix_patch", task_ids=["Control"], message="New CPU version without a new test")
    stale = port.call("submit_integration")
    assert not stale["ok"] and "Run real tests" in stale["error"]["message"]
    assert prepared.world.test_budget.snapshot()["used"] == 1
    assert port.observe()["current_version_test_coverage"]["public_normal"]["status"] == "untested"
    failed = copy.deepcopy(raw)
    expected = {"kind": "return", "value": {"name": "Oak", "quantity": 2},
                "source_api_used": {"models.RecordSchema.load": True}, "source_api_observation_complete": True, "input_unchanged": True}
    observed = {"kind": "exception", "type": "ValueError", "text": "actual controlled first failure",
                "source_api_used": {"models.RecordSchema.load": True}, "source_api_observation_complete": True,
                "input_unchanged": True, "source_api_trace": [{"api": "models.RecordSchema.load", "returned": False, "exception": "ValueError"}]}
    failed["groups"]["public_normal"].update(status="failed", passed=False, tests=[{
        "test_id": "explicit_failure_projection_control", "requirement_group": "reusable_api", "passed": False,
        "expected": expected, "observed": observed}])
    snapshot = copy.deepcopy(failed)
    projected_failure = source.project_public_test_feedback(failed)
    failure = projected_failure["groups"]["public_normal"]["tests"][0]
    assert failed == snapshot and failure["expected"] == expected and failure["observed"] == source.comparable(observed)
    assert failure["first_exception"] == {"type": "ValueError", "text": "actual controlled first failure"}
    assert failure["process_observation_complete"] is True and failure["required_process_satisfied"] is True
    atomic_write(root / "raw-test-result.json", json_bytes(raw))
    atomic_write(root / "presented-test-result.json", json_bytes(shown))
    atomic_write(root / "projection-controls.json", json_bytes({"version": "structured-public-feedback-controls-v0.34",
        "passed": True, "raw_unchanged": True, "passed_items_compact": True, "failed_business_observations_complete": True,
        "member_authored_stdout_preserved": True, "current_version_guard_before_test_and_after_edit": True,
        "actual_member_run_tests": 1, "actual_cpu_sandbox_executions": 2, "model_calls": 0, "optimizer_steps": 0,
        "scope": "New deliberate Gamma feedback projection; no claim of lossless deduplication. One real public+member test call and pure failure projection control, no SDK or model rerun."}))


def test_real_driver_detects_integer_to_float_input_mutation(tmp_path):
    root = output(tmp_path, "typed-input-preservation")
    files = source.reference_solution(source.TASK_IDS[0])
    original = '    return {"records": rendered, "total_quantity": sum(row["quantity"] for row in loaded)}'
    replacement = '    records[0]["quantity"] = float(records[0]["quantity"])\n' + original
    assert files["consumer.py"].count(original) == 1
    files["consumer.py"] = files["consumer.py"].replace(original, replacement)
    request = {"module": "consumer", "function": "catalog", "args": [[{"name": "Oak", "quantity": 1}]],
               "trace": [["models", "RecordSchema", "load"], ["models", "RecordSchema", "dump"]],
               "check_input_unchanged": True}
    execution = source.run_isolated(files, "REQUESTS = " + repr([request]) + "\n" + source.API_DRIVER
        + "\nprint(" + repr(source.MARKER) + " + json.dumps(OBSERVATIONS, sort_keys=True, allow_nan=False))\n", run_root=root / "execution")
    observed = source.pinned._decode(execution, source.MARKER)
    assert observed is not None and len(observed) == 1
    value = observed[0]
    assert value["kind"] == "return" and value["value"] == {"records": [{"name": "Oak", "quantity": 1}], "total_quantity": 1}
    assert value["input_unchanged"] is False
    assert value["source_api_used"] == {"models.RecordSchema.load": True, "models.RecordSchema.dump": True}
    assert value["source_api_observation_complete"] is True
    atomic_write(root / "control.json", json_bytes({"version": "typed-input-preservation-control-v0.34", "passed": True,
        "request": request, "observed": value, "execution": execution,
        "mutated_consumer": files["consumer.py"], "input_domain_changed": False,
        "new_model_calls": 0, "actual_cpu_sandbox_executions": 1,
        "scope": "One actual integer-to-float caller mutation, on a legal input and otherwise correct returned values; this is an observation repair, not a new input obligation."}))
