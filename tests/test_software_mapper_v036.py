"""Finite real World routes plus explicit CPU input-boundary counter-controls.

World edits, three-way imports, fixed artifacts, public tests and acceptance are
real. Input records below are explicitly constructed CPU observations, not model
generations or current-policy support; native archival seals reuse v035's reader.
"""
import copy
import json
import os
from pathlib import Path

import pytest

from proworksim import software_collaboration_v036 as world
from proworksim import software_tasks_v035 as source
from proworksim.software_mapper_v036 import CLASS_ORDER, map_software_method, mapping_spec
from proworksim.software_method_evidence_v036 import VERSION, _Evidence, _unit_dependencies
from proworksim.storage import atomic_write, digest, json_bytes


def sha(value):
    return digest(json_bytes(value))


def seal(evidence):
    evidence = copy.deepcopy(evidence)
    evidence.pop("evidence_sha256", None)
    evidence["evidence_sha256"] = sha(evidence)
    return evidence


def mapping_pair(chain, *, current=True, training=True):
    window = {name: "explicit-cpu-" + name for name in
              ("window_id", "xi_id", "xi_fingerprint", "gamma_fingerprint", "team_policy_fingerprint")}
    case = {"training_eligible": training, "usage": "policy_training" if training else "model_interface_development"}
    rollout = {"rollout_id": "v036-explicit-cpu", "manifest_sha256": "fixture-manifest", "window": window,
               "manifest": {"scenario": {"variation": {"software_case": case}}},
               "online_scope": {"purpose": case["usage"], "source_training_admission": training,
                                "optimizer_update_allowed": training},
               "members": {m: {"origin": "target_model"} for m in world.MEMBERS},
               "work_validity": {"value": True}}
    if current:
        rollout["online_scope"]["method_mapper_spec_sha256"] = sha(mapping_spec())
    evidence = {"version": VERSION, "mapper_spec_sha256": sha(mapping_spec()),
                "rollout_id": rollout["rollout_id"], "rollout_sha256": sha(rollout),
                "manifest_sha256": rollout["manifest_sha256"], "window": window,
                "actual_visibility_complete": True, "delivery_chain": chain,
                "members": {m: {"member_id": m, "origin": "target_model", "own_action_count": 3,
                                "own_action_tokens": 15, "complete_actor_trajectory": True,
                                "own_targets_sha256": sha([m, "explicit-cpu-original-targets"]),
                                "actual_input_bindings_complete": True} for m in world.MEMBERS}}
    return rollout, seal(evidence)


class WorldRoute:
    """Actual World receipts with explicitly controlled private input histories."""
    def __init__(self, root):
        self.root = root
        self.prepared = world.build_software_collaboration_case(world.case_spec(source.TRAINING_CASE_ID), root / "case")
        self.start = copy.deepcopy(self.prepared.world.store.load())
        self.ports = {m: world.SoftwareCollaborationPort(self.prepared.world.session(m, world.PROJECT), m) for m in world.MEMBERS}
        self.actions, self.calls, self.inputs, self.presentations = [], [], [], []
        self.history = {m: [] for m in world.MEMBERS}

    def call(self, member, name, **arguments):
        n = len(self.actions) + 1
        seq, call_id = n * 10, "explicit-cpu-call-" + str(n)
        observation = self.ports[member].observe()
        messages = [{"role": "user", "content": json.dumps({"observation": observation})}]
        messages.extend({"role": "tool", "tool_call_id": "cpu-tool-" + str(a["sequence"]),
                         "content": json.dumps(a["payload"]["response"])} for a in self.history[member])
        request = {"model": "explicit-cpu-no-generator", "messages": messages}
        record = {"call_id": call_id, "sequence": seq, "member_id": member,
                  "selected_request_sha256": sha(request), "synthetic_CPU_input_not_native_generation": True}
        self.calls.append(record)
        self.inputs.append((record, request))
        for index, action in enumerate(self.history[member], 1):
            response = action["payload"]["response"]
            self.presentations.append({"member_id": member, "call_id": call_id, "input_sequence": seq,
                "message_index": index, "message_sha256": sha(messages[index]),
                "selected_request_sha256": sha(request), "action_sequence": action["sequence"],
                "action": action["payload"]["action"], "tool_call_id": "cpu-tool-" + str(action["sequence"]),
                "visible_result": copy.deepcopy(response.get("result")), "visible_error": response.get("error")})
        response = self.ports[member].call(name, request_key="v036-cpu-" + str(n), **arguments)
        assert response["ok"], response
        action = {"sequence": seq + 4, "worker_id": member, "kind": "tool_call",
                  "payload": {"model_call_id": call_id, "action": name, "arguments": arguments,
                              "response": copy.deepcopy(response)}}
        self.actions.append(action)
        self.history[member].append(action)
        return response["result"]

    def task(self, member, name):
        self.call(member, "create_task", task_id=name, description="Explicit CPU method control; never supplied to a model")
        self.call(member, "claim_task", task_id=name)

    def write(self, member, path, text):
        return self.call(member, "write_file", path=path, text=text)

    def finish(self):
        self.call("member_a", "run_tests")
        self.call("member_a", "fix_patch", task_ids=["recipient"], message="CPU fixed final version")
        self.call("member_a", "submit_integration")

    def archive(self):
        assessment = world.assess_software_collaboration(self.prepared, run_root=self.root / "assessment")
        assert assessment["R"] == 1 and assessment["required_process_satisfied"] is True
        state = self.prepared.world.store.load()
        archive = _Evidence.__new__(_Evidence)
        archive.start, archive.end, archive.case = self.start, state, self.prepared.case
        archive.facts = state["projects"][world.PROJECT]["software"]
        archive.assessment, archive.world = assessment, state["software_events"]
        operations = {a["payload"]["response"]["command_id"]: a for a in self.actions}
        archive.world_actions = {e["sequence"]: operations[e["operation_id"]] for e in archive.world}
        archive.calls, archive.inputs, archive.presentations = self.calls, self.inputs, self.presentations
        archive.action_by_tool_id = {(a["worker_id"], "cpu-tool-" + str(a["sequence"])): a for a in self.actions}
        def bundle(reference):
            artifact = state["artifacts"][reference["object_id"]]
            return json.loads(self.prepared.world.store.version_path(artifact, reference["version_id"]).read_text())
        archive.bundle = bundle
        atomic_write(self.root / "actual-actions.json", json_bytes(self.actions))
        atomic_write(self.root / "assessment.json", json_bytes(assessment))
        return archive


ALTERNATE_READER = '''import sqlparse

def statement_records(script):
    result = []
    for piece in sqlparse.split(script):
        parsed = sqlparse.parse(piece)
        result.append({"text": piece, "kind": parsed[0].get_type()})
    return result
'''
ALTERNATE_REPORT = '''import reader

def summarize(script):
    rows = reader.statement_records(script)
    counts = {name: sum(row["kind"] == name for row in rows) for name in ("SELECT", "UPDATE", "DELETE")}
    return {"statements": rows, "counts": counts, "total": len(rows)}
'''


def create_route(root, route):
    fixture = WorldRoute(root)
    original = source.build_case(source.TRAINING_CASE_ID)["files"]
    reference = source.reference_solution(source.TRAINING_CASE_ID)
    fixture.task("member_a", "recipient")
    if route in {"local", "off_branch"}:
        for path in ("reader.py", "report.py"):
            fixture.write("member_a", path, reference[path])
        fixture.finish()
        if route == "off_branch":
            fixture.write("member_b", "reader.py", ALTERNATE_READER)
            fixture.write("member_b", "report.py", ALTERNATE_REPORT)
            fixture.call("member_b", "integrate_patch", patch_id="patch-1")
        return fixture.archive()
    fixture.task("member_b", "producer")
    if route == "discard_then_consume":
        fixture.write("member_b", "reader.py", ALTERNATE_READER)
        first = fixture.call("member_b", "fix_patch", task_ids=["producer"], message="CPU first attempt")
        fixture.call("member_a", "integrate_patch", patch_id=first["patch_id"])
        fixture.write("member_a", "reader.py", original["reader.py"])
        fixture.write("member_b", "reader.py", reference["reader.py"])
        second = fixture.call("member_b", "fix_patch", task_ids=["producer"], message="CPU later fixed product")
        fixture.call("member_a", "integrate_patch", patch_id=second["patch_id"])
        fixture.write("member_a", "report.py", reference["report.py"])
        fixture.finish()
        return fixture.archive()
    if route in {"comment", "helper", "noop"}:
        for path in ("reader.py", "report.py"):
            fixture.write("member_a", path, reference[path])
        incoming = ("# Documentation only\n" + original["reader.py"] if route == "comment" else
                    original["reader.py"] + "\ndef unused_helper():\n    return 99\n" if route == "helper" else reference["reader.py"])
        fixture.write("member_b", "reader.py", incoming)
        patch = fixture.call("member_b", "fix_patch", task_ids=["producer"], message="CPU nonproductive delta")
        imported = fixture.call("member_a", "integrate_patch", patch_id=patch["patch_id"])
        if imported["conflicts"]:
            fixture.write("member_a", "reader.py", reference["reader.py"])
        fixture.finish()
        return fixture.archive()
    fixture.write("member_b", "reader.py", reference["reader.py"])
    if route != "direct":
        fixture.write("member_b", "report.py", reference["report.py"])
        fixture.write("member_a", "reader.py", "def statement_records(script):\n    return ['recipient-before']\n")
        fixture.write("member_a", "report.py", "def summarize(script):\n    return {'recipient': 1}\n")
    else:
        fixture.write("member_a", "report.py", reference["report.py"])
    patch = fixture.call("member_b", "fix_patch", task_ids=["producer"], message="CPU peer fixed source")
    imported = fixture.call("member_a", "integrate_patch", patch_id=patch["patch_id"])
    if route != "direct":
        assert set(imported["conflicts"]) == {"reader.py", "report.py"}
        for path in ("reader.py", "report.py"):
            fixture.call("member_a", "read_file", path=path, start_line=1, max_lines=100)
        fixture.write("member_a", "reader.py", ALTERNATE_READER if route in {"partial", "overwrite"} else reference["reader.py"])
        fixture.write("member_a", "report.py", ALTERNATE_REPORT if route == "overwrite" else reference["report.py"])
    fixture.finish()
    return fixture.archive()


@pytest.fixture(scope="module")
def world_routes(tmp_path_factory):
    root = Path(os.environ.get("PROWORKSIM_V036_METHOD_CONTROL_RUN", str(tmp_path_factory.mktemp("v036-methods"))))
    root.mkdir(parents=True, exist_ok=True)
    routes = {}
    for name in ("local", "direct", "conflict", "partial", "discard_then_consume", "overwrite", "comment", "helper", "noop", "off_branch"):
        archive = create_route(root / name, name)
        chain = archive.delivery_chain()
        rollout, evidence = mapping_pair(chain, training=False)
        mapping = map_software_method(rollout, evidence)
        atomic_write(root / name / "method-chain.json", json_bytes(chain))
        atomic_write(root / name / "mapping.json", json_bytes(mapping))
        routes[name] = archive
    atomic_write(root / "scope.json", json_bytes({"real_world_routes": len(routes), "target_model_calls": 0,
        "gpu_used": False, "optimizer_updates": 0, "synthetic_input_records": True,
        "scope": "Actual World commit/merge/test/fixed/submit/independent-acceptance controls; explicitly constructed private input histories, not native model generations, current-policy support or P3 material."}))
    return routes


@pytest.mark.parametrize("route,category", [("local", 0), ("off_branch", 0), ("direct", 1), ("conflict", 1), ("partial", 1), ("discard_then_consume", 1)])
def test_real_world_positive_routes_keep_original_member_targets(world_routes, route, category):
    chain = world_routes[route].delivery_chain()
    rollout, evidence = mapping_pair(chain)
    unchanged = copy.deepcopy(rollout)
    result = map_software_method(rollout, evidence)
    assert result["class_id"] == CLASS_ORDER[category], result
    assert rollout == unchanged
    assert all(row["own_action_tokens"] == 15 and row["base_actor_targets_unchanged"]
               and row["support_eligible"] for row in result["member_projections"].values())
    if route == "direct":
        assert chain["peer_integrations"][0]["process_attributes"]["direct_merge"]
        assert not chain["peer_integrations"][0]["source_text_presented"]
    if route == "partial":
        peer = chain["peer_integrations"][0]
        assert peer["process_attributes"]["conflict_resolved"] and peer["process_attributes"]["partial_rewrite"]
        assert [(u["path"], u["symbol"]) for u in peer["retained_production_units"]] == [("report.py", "summarize")]
    if route == "discard_then_consume":
        assert [p["route_state"] for p in chain["peer_integrations"]] == ["discarded", "consumed"]


@pytest.mark.parametrize("route", ["overwrite", "comment", "helper", "noop"])
def test_real_success_does_not_make_untracked_overwrite_or_nonproductive_import_a_peer_method(world_routes, route):
    archive = world_routes[route]
    assert archive.assessment["R"] == 1
    result = map_software_method(*mapping_pair(archive.delivery_chain()))
    assert result["status"] == "unmapped" and not result["composition_support_eligible"]


@pytest.mark.parametrize("missing", ["metadata", "receipt", "current_test", "late_receipt", "late_metadata"])
def test_actual_input_timing_and_missing_proofs_are_not_repaired_by_backend_facts(world_routes, missing):
    archive = copy.copy(world_routes["conflict"])
    archive.inputs = copy.deepcopy(archive.inputs)
    archive.presentations = copy.deepcopy(archive.presentations)
    integrate = next(e for e in archive.world if e["kind"] == "integrate")
    import_sequence = archive.world_action(integrate)["sequence"]
    edits = [e for e in archive.world if e["kind"] == "edit" and e["actor_id"] == "member_a" and e["sequence"] > integrate["sequence"]]
    last_edit_input = max(archive._input_sequence(archive.world_action(e)) for e in edits)
    if missing in {"metadata", "late_metadata"}:
        for record, request in archive.inputs:
            if missing == "metadata" or record["sequence"] <= last_edit_input:
                for message in request["messages"]:
                    if message["role"] == "user":
                        body = json.loads(message["content"])
                        body["observation"]["patches"] = []
                        body["observation"]["all_fixed_patches"] = []
                        message["content"] = json.dumps(body)
        # Tool-return patch metadata is producer-private, not recipient input.
    else:
        archive.presentations = [p for p in archive.presentations if not (
            missing == "receipt" and p["action_sequence"] == import_sequence
            or missing == "late_receipt" and p["action_sequence"] == import_sequence and p["input_sequence"] <= last_edit_input
            or missing == "current_test" and p["action"] == "run_tests")]
    result = map_software_method(*mapping_pair(archive.delivery_chain()))
    assert result["status"] == "unmapped", (missing, result)


def test_any_positive_does_not_hide_an_unexplained_earlier_import(world_routes):
    archive = copy.copy(world_routes["discard_then_consume"])
    first = next(e for e in archive.world if e["kind"] == "integrate")
    first_sequence = archive.world_action(first)["sequence"]
    archive.presentations = [p for p in archive.presentations if p["action_sequence"] != first_sequence]
    chain = archive.delivery_chain()
    assert chain["peer_integrations"][1]["qualifying_fixed_product_consumption"]
    assert chain["unexplained_critical_dependencies"]
    assert map_software_method(*mapping_pair(chain))["status"] == "unmapped"


@pytest.mark.parametrize("change", ["included_dependency", "manual_acquisition", "unrecognized_final", "invalid", "unknown", "missing_input"])
def test_critical_dependencies_and_original_validity_remain_hard_gates(world_routes, change):
    chain = world_routes["direct"].delivery_chain()
    if change == "included_dependency":
        chain["unresolved_peer_dependencies"] = ["unexplained-transitive-patch"]
    elif change == "manual_acquisition":
        chain["unexplained_critical_dependencies"] = [{"patch_id": "unimported", "reason": "actual_manual_source_acquisition"}]
    elif change == "unrecognized_final":
        chain["final_production_units_recognized"] = False
    rollout, evidence = mapping_pair(chain)
    if change in {"invalid", "unknown"}:
        rollout["work_validity"]["value"] = False if change == "invalid" else None
        evidence["rollout_sha256"] = sha(rollout)
    elif change == "missing_input":
        evidence["actual_visibility_complete"] = False
    result = map_software_method(rollout, seal(evidence))
    assert result["status"] == "unmapped"
    assert all(row["own_action_count"] == 3 and row["base_actor_targets_unchanged"] for row in result["member_projections"].values())


def test_structurally_same_unit_with_changed_or_unknown_helper_is_not_dependency_proof():
    code = "def helper():\n    return 1\n\ndef entry(x):\n    return helper() + x\n"
    source_tree = {"files": {"consumer.py": code}}
    final = {"files": {"consumer.py": code.replace("return 1", "return 2")}}
    proof = _unit_dependencies("consumer.py", "entry", source_tree, final, {"consumer.py": ["entry"]}, [])
    assert not proof["explained"] and proof["issues"]
    dynamic = {"files": {"consumer.py": "def entry(x):\n    return globals()[x]()\n"}}
    assert not _unit_dependencies("consumer.py", "entry", dynamic, dynamic, {"consumer.py": ["entry"]}, [])["explained"]
    nested = "VALUE = 1\ndef second():\n    return VALUE\ndef first():\n    return second()\ndef entry(x):\n    return first() + x\n"
    incoming = {"files": {"consumer.py": nested}}
    changed = {"files": {"consumer.py": nested.replace("VALUE = 1", "VALUE = 2")}}
    assert not _unit_dependencies("consumer.py", "entry", incoming, changed, {"consumer.py": ["entry"]}, [])["explained"]
    missing = {"files": {"consumer.py": nested.replace("return VALUE", "return MISSING")}}
    assert not _unit_dependencies("consumer.py", "entry", missing, missing, {"consumer.py": ["entry"]}, [])["explained"]


def test_function_local_import_does_not_depend_on_redundant_module_binding():
    report = "def summarize(script):\n    from reader import statement_records\n    return statement_records(script)\n"
    reader = "def statement_records(script):\n    return script\n"
    source_tree = {"files": {"report.py": report, "reader.py": reader}}
    final = {"files": {"report.py": "from reader import statement_records\n" + report, "reader.py": reader}}
    symbols = {"report.py": ["summarize"], "reader.py": ["statement_records"]}
    proof = _unit_dependencies("report.py", "summarize", source_tree, final, symbols, [])
    assert proof["explained"] and proof["cross_production_units"]
    assert any(binding.get("lexical_unit") == "summarize" for binding in proof["bindings"])
    changed = copy.deepcopy(final)
    changed["files"]["report.py"] = report.replace("import statement_records", "import missing as statement_records")
    assert not _unit_dependencies("report.py", "summarize", source_tree, changed, symbols, [])["explained"]


def test_nested_local_import_cannot_hide_an_outer_global_dependency_change():
    body = "def summarize(script):\n    def unused():\n        import other as reader\n        return reader\n    return reader.statement_records(script)\n"
    reader = "def statement_records(script):\n    return script\n"
    source_tree = {"files": {"report.py": "import reader\n" + body, "reader.py": reader}}
    final = {"files": {"report.py": "import other as reader\n" + body, "reader.py": reader}}
    symbols = {"report.py": ["summarize"], "reader.py": ["statement_records"]}
    assert not _unit_dependencies("report.py", "summarize", source_tree, final, symbols, [])["explained"]


def test_shadow_labels_and_other_purpose_never_enter_new_support(world_routes):
    chain = world_routes["conflict"].delivery_chain()
    for current, training in ((False, True), (True, False)):
        result = map_software_method(*mapping_pair(chain, current=current, training=training))
        assert result["status"] == "mapped" and not result["composition_support_eligible"]
        assert not any(p["support_eligible"] for p in result["member_projections"].values())


def test_new_rule_and_exact_evidence_window_are_sealed(world_routes):
    rollout, evidence = mapping_pair(world_routes["local"].delivery_chain())
    assert CLASS_ORDER == ("local_lineage_delivery", "evidenced_peer_product_delivery")
    for key in rollout["window"]:
        changed = copy.deepcopy(rollout)
        changed["window"][key] += "-different"
        with pytest.raises(ValueError, match="another exact"):
            map_software_method(changed, evidence)
    changed = copy.deepcopy(evidence)
    changed["members"]["member_a"]["own_action_tokens"] += 1
    with pytest.raises(ValueError, match="seal"):
        map_software_method(rollout, changed)
    with pytest.raises(ValueError, match="specification"):
        map_software_method(rollout, evidence, spec={"class_order": list(reversed(CLASS_ORDER))})
