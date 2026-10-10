"""Finite original-record controls; no model, tokenizer, GPU or business execution."""
import copy
import json

import pytest

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_work_v045 as measure

BASE = "def public_value(value):\n    return value + 1\n"
CHANGED = "def public_value(value):\n    return value + 2\n"
OTHER = "def public_value(value):\n    return value + 9\n"
IDENTITY = {"adapter_sha256": "fixture-frozen-actor"}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json_bytes(value))


def ref(name, version):
    return {"object_id": name, "version_id": version}


class Archive:
    """Original receipt fixture with exact hashes, not a model simulation."""

    def __init__(self, root, *, condition="F2", members=2):
        self.root, self.condition = root, condition
        self.control = root / "prepared/world/control"
        self.control.mkdir(parents=True)
        self.members = [f"member_{i:03d}" for i in range(1, members + 1)]
        self.initial_members = list(self.members)
        self.state = {"software_events": [], "shares": [], "artifacts": {},
            "projects": {"SOFTWARE27": {"software": {"registry": {}, "test_reports": {}, "patches": {},
                "initial_diagnostics": {}, "case": {"condition": condition,
                    "editable_paths": ["product.py", "test_member.py"], "source_contract": {
                        "public_production_files": ["product.py"], "contract_symbols": {"product.py": ["public_value"]}}}}}}}
        self.software = self.state["projects"]["SOFTWARE27"]["software"]
        self.files = {}
        self.initial = self.version("baseline", "v1", BASE)
        for member in self.members:
            self.software["registry"][member] = {"origin": "initial_configuration", "initial_source_reference": self.initial,
                                                 "status": "live"}
            self.version(member, "v1", BASE)
        self.budget = {"records": {}, "members": list(self.members), "available_tokens": 500000,
            "charged_tokens": 0, "remaining_decisions": 128, "remaining_attempts": 128,
            "decisions": 0, "attempts": 0, "limits": {"max_total_tokens": 500000, "max_decisions": 128, "max_attempts": 128}}
        self.attempts, self.experience, self.responses = [], [], {}
        self.count = 0

    def version(self, name, version, code, script="pass\n"):
        reference = ref(name, version)
        files = {"product.py": code, "test_member.py": script, "contract.md": "Public fixture contract"}
        self.files[(name, version)] = files
        self.state["artifacts"][name] = {"filename": name + ".json"}
        save(self.control / "versions" / name / version / (name + ".json"), {"files": files, "included_patch_ids": []})
        return reference

    def emit(self, kind, member, payload):
        row = {"kind": kind, "worker_id": member, "payload": copy.deepcopy(payload), "sequence": len(self.experience)}
        self.experience.append(row)
        return row

    def act(self, member, action, arguments, kind, facts, *, result=None, inputs=None, prompt=8, rejected=False):
        self.count += 1
        ordinal, cid = self.count, f"call-{self.count}"
        opportunity = f"staff-opportunity-fixture-{ordinal}"
        action_id, operation = f"action-{ordinal}", f"command-{ordinal}"
        availability = {m: {"can_receive_work": True, "status": "ready"} for m in self.members}
        before = {"member_id": member, "opportunity_ordinal": ordinal, "opportunity_id": opportunity,
            "phase": "before", "team_budget": copy.deepcopy(self.budget), "availability": availability,
            "world_event_sequence": len(self.state["software_events"]), "model_visible": False}
        self.emit(measure.OPPORTUNITY_VERSION, member, before)
        selected = {"messages": inputs or [{"role": "user", "content": json.dumps({"observation": {
            "actor_id": member, "patches": list(self.software["patches"].values())}})}], "max_tokens": 2048}
        input_ids, output_ids = list(range(prompt)), [7, 8]
        prep = {"version": "resident-request-budget-v0.31r3", "prompt_tokens": prompt,
            "reserved_output_tokens": 2048, "context_limit": 16384, "fits": prompt + 2048 <= 16384,
            "selected_request_sha256": digest(json_bytes(selected)), "input_ids_sha256": digest(json_bytes(input_ids)),
            "window_id": "organization-v045:fixture", "actor_identity": IDENTITY,
            "original_request_sha256": digest(json_bytes(selected))}
        prep["preparation_sha256"] = digest(json_bytes(prep))
        reservation = {"preparation": prep, "token_reservation": prompt + 2048}
        self.emit("model_call", member, {"stage": "started", "call_id": cid, "opportunity_id": opportunity,
                                         "reservation": reservation})
        self.budget["decisions"] += 1
        self.budget["remaining_decisions"] -= 1
        if rejected:
            self.budget["records"][cid] = {"call_id": cid, "member": member, "status": "admission_rejected",
                "attempt_started": False, "rejected_reservation": reservation,
                "admission_limits": ["context_capacity"], "budget_kind": "context_capacity"}
            self.emit("model_boundary_error", member, {"opportunity_id": opportunity, "status": "model_budget_exhausted",
                "limits": ["context_capacity"], "team_budget": self.budget})
            self.emit(measure.OPPORTUNITY_VERSION, member, {**before, "phase": "after",
                "team_budget": self.budget, "outcome_status": "model_budget_exhausted"})
            return None
        usage = {"prompt_tokens": prompt, "completion_tokens": 2, "total_tokens": prompt + 2}
        native = {"id": "tool-" + cid, "type": "function", "function": {"name": action, "arguments": json.dumps(arguments)}}
        body = {"id": "response-" + cid, "actor_identity": IDENTITY, "online_window_id": prep["window_id"],
            "protocol_parse_error": None, "usage": usage, "token_trace": {"input_ids": input_ids, "output_ids": output_ids},
            "choices": [{"message": {"role": "assistant", "content": "", "tool_calls": [native]}}]}
        original_seq = self.emit("model_attempt", member, {"stage": "finished", "call_id": cid})["sequence"]
        self.attempts.append({"call_id": cid, "worker_id": member, "experience_sequence": original_seq,
            "status": "success", "original_output_present": True, "response_id": body["id"], "usage": usage,
            "response_body_sha256": digest(json_bytes(body)), "input_ids_sha256": prep["input_ids_sha256"],
            "output_ids_sha256": digest(json_bytes(output_ids))})
        self.budget["records"][cid] = {"call_id": cid, "member": member, "status": "settled", "attempt_started": True,
            "reservation": reservation, "charge": {"response_id": body["id"], "response_body_sha256": digest(json_bytes(body)),
                "reported_usage": usage, "charged_tokens": usage["total_tokens"]}}
        self.budget["charged_tokens"] += usage["total_tokens"]
        self.budget["available_tokens"] -= usage["total_tokens"]
        self.budget["attempts"] += 1
        self.budget["remaining_attempts"] -= 1
        event = {"sequence": len(self.state["software_events"]) + 1, "kind": kind, "actor_id": member,
            "action_id": action_id, "operation_id": operation, "logical_time": ordinal, **copy.deepcopy(facts)}
        self.state["software_events"].append(event)
        response = {"ok": True, "result": copy.deepcopy(result if result is not None else facts),
            "action_id": action_id, "command_id": operation, "command_committed": True}
        self.responses[cid] = response
        association = {"model_call_id": cid, "model_tool_call_id": native["id"], "decision_id": cid,
                       "opportunity_id": opportunity}
        self.emit("tool_call", member, {"action": action, "arguments": arguments, "response": response, **association})
        self.emit("model_action_link", member, {"world_action_id": action_id, "world_command_id": operation,
            "world_response": response, **association})
        self.emit("model_tool_result", member, {"call_id": cid, "model_tool_call_id": native["id"], "world_response": response})
        self.emit(measure.OPPORTUNITY_VERSION, member, {**before, "phase": "after", "team_budget": self.budget,
            "world_event_sequence": len(self.state["software_events"]), "outcome_status": "acted"})
        directory = self.root / "raw-transport" / f"request-{ordinal:05d}"
        save(directory / "runner-turn.json", {"member_id": member, "association": {"call_id": cid, "worker_id": member}})
        save(directory / "selected-request.json", selected)
        save(directory / "budget-preparation.json", prep)
        save(directory / "projection.json", {"selected_request_sha256": prep["selected_request_sha256"],
                                              "input_ids_sha256": prep["input_ids_sha256"]})
        save(directory / "response.json", {"http_status": 200, "body": body})
        return event

    def edit(self, member, before, after, *, inputs=None):
        old, new = self.files[measure.base.ref_key(before)]["product.py"], self.files[measure.base.ref_key(after)]["product.py"]
        return self.act(member, "write_file", {"path": "product.py", "text": new}, "edit",
            {"path": "product.py", "previous_reference": before, "source_reference": after,
             "before_sha256": digest(old.encode()), "after_sha256": digest(new.encode())}, inputs=inputs)

    def patch(self, member, reference, patch_id):
        facts = {"patch_id": patch_id, "source_reference": reference, "base_reference": self.initial,
            "files_sha256": digest(json_bytes(self.files[measure.base.ref_key(reference)])), "author": member}
        event = self.act(member, "fix_patch", {"task_ids": [], "message": "Current work"}, "patch_fixed", facts)
        self.software["patches"][patch_id] = facts
        self.state["shares"].append({"project_id": "SOFTWARE27", **reference,
            "actor_ids": [f"member_{i:03d}" for i in range(1, 7)], "shared_by": member, "at": event["logical_time"]})
        return event

    def test(self, member, reference, *, passed=True, inputs=None, report=False):
        groups = {key: {"executed": True, "passed": passed} for key in measure.base.PUBLIC_GROUPS}
        facts = {"source_reference": reference, "groups": groups, "executed": True, "passed": passed,
                 "files_sha256": digest(json_bytes(self.files[measure.base.ref_key(reference)]))}
        page_result = None
        if report:
            report_id = f"report-{self.count + 1}"
            body = json_bytes(facts).decode()
            page = {"index": 0, "text": body, "sha256": digest(body.encode()), "start": 0, "end": len(body)}
            page_result = {"report_id": report_id, "body_sha256": digest(body.encode()), "page": page}
        event = self.act(member, "run_tests", {}, "test", facts, result=page_result, inputs=inputs)
        if report:
            self.software["test_reports"][report_id] = {"report_id": report_id, "actor_id": member,
                "event_identity": {"test_event_sequence": event["sequence"], "operation_id": event["operation_id"]},
                "visible_result": facts, "body": body, "body_sha256": digest(body.encode()), "pages": [page]}
        return event

    def finish(self, *, R=0, submitted=False):
        save(self.control / "state.json", self.state)
        result = {"version": "software-organization-runtime-v0.45", "slot_id": "fixture", "status": "closed",
            "condition": self.condition, "purpose": "organization_development", "R": R, "submitted": submitted,
            "complete_delivery": bool(R), "actor_identity": IDENTITY, "team_budget": {"model": self.budget},
            "member_lifecycle": {"initial_members": self.initial_members}}
        save(self.root / "slot-result.json", result)
        save(self.root / "team-budget.json", {"model": self.budget})
        save(self.root / "organization-evidence.json", {"original_attempts": self.attempts, "team_budget": {"model": self.budget}})
        (self.root / "experience.jsonl").write_text("\n".join(json.dumps(row) for row in self.experience) + "\n")
        return self.root


def program_fixture(root, *, submit=True, passed=True, publication=True, mode="import", changed=CHANGED,
                    receiver_before=BASE, birth=False):
    a = Archive(root, condition="O3" if birth else "F2")
    producer, recipient = "member_001", "member_003" if birth else "member_002"
    original = ref(producer, "v1")
    produced = a.version(producer, "v2", changed)
    a.edit(producer, original, produced)
    if not publication:
        return a.finish()
    a.patch(producer, produced, "patch-source")
    previous = a.version(recipient, "v1", receiver_before)
    integrated = a.version(recipient, "v2", OTHER if mode == "conflict" else changed)
    if birth:
        a.act(producer, "spawn_member", {"briefing": "", "patch_id": "patch-source"}, "member_spawned",
            {"member_id": recipient, "recipient": recipient, "initial_patch_id": "patch-source",
             "initial_source_reference": produced, "workspace_reference": integrated, "origin": "member_request"})
        a.members.append(recipient)
        a.software["registry"][recipient] = {"origin": "member_request", "initial_source_reference": produced, "status": "live"}
    elif mode in {"import", "conflict"}:
        a.act(recipient, "integrate_patch", {"patch_id": "patch-source"}, "integrate",
            {"patch_id": "patch-source", "input_reference": produced,
             "previous_reference": previous, "source_reference": integrated, "conflicts": []})
    elif mode in {"read", "copy"}:
        event = a.act(recipient, "read_file", {"path": "product.py", "start_line": 1, "max_lines": 80, "patch_id": "patch-source"},
            "read", {"source_reference": produced, "path": "product.py", "patch_id": "patch-source"},
            result={"source_reference": produced, "path": "product.py", "text": changed.strip(), "total_lines": 2})
        feedback = [{"role": "tool", "content": json.dumps(a.responses["call-3"])}]
        if mode == "copy":
            a.edit(recipient, previous, integrated, inputs=feedback)
        else:
            a.act(recipient, "read_file", {"path": "contract.md"}, "read",
                  {"source_reference": previous, "path": "contract.md"}, inputs=feedback)
            return a.finish()
        assert event["kind"] == "read"
    else:
        a.act(recipient, "read_file", {"path": "contract.md"}, "read", {"source_reference": previous, "path": "contract.md"})
        return a.finish()
    test = a.test(recipient, integrated, passed=passed)
    if submit:
        a.patch(recipient, integrated, "patch-recipient")
        a.act(recipient, "submit_integration", {"message": "Finished"}, "submit",
            {"delivery_id": "delivery-1", "source_reference": integrated, "test_sequence": test["sequence"]})
    return a.finish(R=int(submit and passed), submitted=submit)


def test_program_five_stages_and_original_opportunity_resources(tmp_path):
    folder = program_fixture(tmp_path)
    before = {str(path): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    value = measure.measure_episode(folder)
    assert value["status"] == "measured", value["measurement_gaps"]
    assert value["has_evidenced_cross_member_chain"] is True
    assert value["has_use_linked_to_final_fixed_delivery"] is True
    chain = value["program_work_chains"][0]
    assert [chain["stages"][key]["value"] for key in measure.STAGES] == [True] * 5
    first = chain["first_eligible_share_opportunity"]["resource"]
    assert first["call_id"] == "call-2"
    assert first["prompt_tokens"] == 8 and first["reserved_output_tokens"] == 2048
    assert first["hard_headroom_tokens"] == 14328
    assert first["team_available_tokens_before_opportunity"] == 499990
    assert first["team_available_tokens_before_opportunity"] != 499940
    assert chain["stages"]["acquired"]["resource"]["call_id"] == "call-3"
    assert chain["stages"]["used"]["resource"]["call_id"] == "call-4"
    assert all(path.read_bytes() == before[str(path)] for path in folder.rglob("*") if path.is_file())
    assert value["new_model_calls"] == value["new_tokenizer_calls"] == value["new_world_actions"] == 0


@pytest.mark.parametrize("submit,passed", [(False, True), (True, False), (False, False)])
def test_real_use_survives_business_failure_or_no_submission(tmp_path, submit, passed):
    value = measure.measure_episode(program_fixture(tmp_path, submit=submit, passed=passed))
    assert value["recorded_R"] == 0
    assert value["has_evidenced_cross_member_chain"] is True
    assert value["has_use_linked_to_final_fixed_delivery"] is submit


@pytest.mark.parametrize("mode,acquired,used", [("metadata", False, False), ("read", True, False), ("copy", True, None)])
def test_access_reading_and_similar_manual_copy_do_not_become_use(tmp_path, mode, acquired, used):
    value = measure.measure_episode(program_fixture(tmp_path, mode=mode))
    row = value["five_stage_relations"][0]
    assert row["stages"]["published"]["value"] is True
    assert row["stages"]["acquired"]["value"] is acquired
    assert row["stages"]["used"]["value"] is used
    assert value["has_evidenced_cross_member_chain"] is used


def test_current_work_without_publication_locates_stage_two(tmp_path):
    value = measure.measure_episode(program_fixture(tmp_path, publication=False))
    row = value["five_stage_relations"][0]
    assert row["stages"]["produced"]["value"] is True
    assert row["stages"]["published"]["value"] is False
    assert value["has_evidenced_cross_member_chain"] is False


@pytest.mark.parametrize("changed,before", [("# comment only\n" + BASE, BASE), (CHANGED, CHANGED)])
def test_initial_code_and_independently_present_code_are_not_adoption(tmp_path, changed, before):
    value = measure.measure_episode(program_fixture(tmp_path, changed=changed, receiver_before=before))
    assert value["has_evidenced_cross_member_chain"] is False
    assert value["program_work_chains"] == []


def test_conflicted_import_is_acquisition_but_use_remains_pending(tmp_path):
    value = measure.measure_episode(program_fixture(tmp_path, mode="conflict"))
    row = value["five_stage_relations"][0]
    assert row["stages"]["acquired"]["value"] is True
    assert row["stages"]["used"]["value"] is None
    assert value["has_evidenced_cross_member_chain"] is None


def test_o3_birth_from_current_published_patch_then_validation_is_partner_use(tmp_path):
    value = measure.measure_episode(program_fixture(tmp_path, birth=True))
    assert value["status"] == "measured", value["measurement_gaps"]
    chain = value["program_work_chains"][0]
    assert chain["recipient"] == "member_003"
    assert chain["stages"]["acquired"]["route"] == "authorized_snapshot_at_member_birth"
    assert chain["stages"]["acquired"]["acquisition_resource_actor"] == "member_001"
    assert chain["stages"]["used"]["resource"]["member"] == "member_003"
    assert value["member_work"]["member_003"]["current_program_work"] == 0


def test_s1_has_no_hidden_partner_and_normal_false_not_applicable(tmp_path):
    a = Archive(tmp_path, condition="S1", members=1)
    changed = a.version("member_001", "v2", CHANGED)
    a.edit("member_001", ref("member_001", "v1"), changed)
    a.patch("member_001", changed, "own-only")
    value = measure.measure_episode(a.finish())
    assert value["status"] == "measured", value["measurement_gaps"]
    assert value["has_evidenced_cross_member_chain"] is False
    assert value["cross_member_applicability"] == "not_applicable_no_partner"
    assert value["totals"]["observed_members"] == 1


@pytest.mark.parametrize("mutation", ["selected_bytes", "native_tool", "grant", "opportunity"])
def test_broken_original_bindings_remain_pending(tmp_path, mutation):
    folder = program_fixture(tmp_path)
    if mutation == "selected_bytes":
        path = folder / "raw-transport/request-00003/selected-request.json"
        value = json.loads(path.read_text())
        value["messages"] = []
        save(path, value)
    elif mutation == "native_tool":
        path = folder / "raw-transport/request-00003/response.json"
        value = json.loads(path.read_text())
        value["body"]["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "read_file"
        save(path, value)
    elif mutation == "grant":
        path = folder / "prepared/world/control/state.json"
        value = json.loads(path.read_text())
        value["shares"] = []
        save(path, value)
    else:
        path = folder / "experience.jsonl"
        values = [json.loads(line) for line in path.read_text().splitlines()]
        values = [row for row in values if not (row["kind"] == measure.OPPORTUNITY_VERSION
                  and row["payload"]["phase"] == "before" and row["payload"]["opportunity_ordinal"] == 3)]
        path.write_text("\n".join(json.dumps(row) for row in values) + "\n")
    value = measure.measure_episode(folder)
    assert value["status"] == "measurement_pending" or value["pending_program_relations"]
    if mutation != "opportunity":
        assert value["has_evidenced_cross_member_chain"] is None
    else:
        assert value["program_work_chains"][0]["stages"]["acquired"]["resource"]["status"] == "measurement_pending"


def test_rejected_first_sharing_opportunity_keeps_original_context_and_pool(tmp_path):
    a = Archive(tmp_path)
    changed = a.version("member_001", "v2", CHANGED)
    a.edit("member_001", ref("member_001", "v1"), changed)
    a.act("member_001", "fix_patch", {}, "unused", {}, prompt=15000, rejected=True)
    value = measure.measure_episode(a.finish())
    assert value["status"] == "measured", value["measurement_gaps"]
    first = value["current_program_work"][0]["first_eligible_share_opportunity"]["resource"]
    assert first["actual_generation_started"] is False
    assert first["hard_headroom_tokens"] == -664
    assert first["team_available_tokens_before_opportunity"] == 499990
    assert value["has_evidenced_cross_member_chain"] is False


def information_fixture(root, *, initial=False, actual_recipient=True):
    a = Archive(root)
    sender, recipient = "member_001", "member_002"
    reference = ref(sender, "v1")
    if not initial:
        reference = a.version(sender, "v2", CHANGED)
        a.edit(sender, ref(sender, "v1"), reference)
    test = a.test(sender, reference, report=True)
    test_call = "call-" + str(a.count)
    report = next(iter(a.software["test_reports"].values()))
    message = a.act(sender, "send_message", {"recipient": recipient, "task_id": "root_goal", "body": report["body"]},
        "work_message", {"recipient": recipient, "task_id": "root_goal", "body": report["body"]},
        inputs=[{"role": "tool", "content": json.dumps(a.responses[test_call])}])
    changed = a.version(recipient, "v2", OTHER)
    observed = {"actor_id": recipient, "messages": [message] if actual_recipient else []}
    a.edit(recipient, ref(recipient, "v1"), changed,
           inputs=[{"role": "user", "content": json.dumps({"observation": observed})}])
    a.test(recipient, changed)
    assert test["kind"] == "test"
    return a.finish()


def test_current_report_transmission_and_actual_read_do_not_prove_information_use(tmp_path):
    value = measure.measure_episode(information_fixture(tmp_path))
    rows = [row for row in value["five_stage_relations"] if row["work_kind"] == "information"]
    assert len(rows) == 1
    assert [rows[0]["stages"][key]["value"] for key in measure.STAGES] == [True, True, True, None, None]
    assert value["information_work_chains"] == []
    assert value["has_evidenced_cross_member_chain"] is None
    assert value["pending_semantic_relations"]


def test_initial_report_relay_stays_separate_from_current_member_reuse(tmp_path):
    value = measure.measure_episode(information_fixture(tmp_path, initial=True))
    assert value["initial_material_forwarding"][0]["status"] == "exact_initial_material_forwarding"
    assert value["initial_material_forwarding"][0]["current_member_work_reuse"] is False
    assert value["current_information_work"] == []
    assert value["has_evidenced_cross_member_chain"] is False


def test_addressed_message_not_in_actual_input_is_not_acquired(tmp_path):
    value = measure.measure_episode(information_fixture(tmp_path, actual_recipient=False))
    row = next(row for row in value["five_stage_relations"] if row["work_kind"] == "information")
    assert row["stages"]["published"]["value"] is True
    assert row["stages"]["acquired"]["value"] is False
    assert row["stages"]["used"]["value"] is False
