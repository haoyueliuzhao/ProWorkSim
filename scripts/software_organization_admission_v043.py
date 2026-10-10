"""v043 layered admission from immutable v042 CPU evidence, without new replay.

Old qualification results remain false. Source/evidence identity, original
visible pages and permissions, completed routes, and actual selected hard
capacity are mandatory. The original 1024-token protected margin is retained
with every deficient location as a nonblocking diagnostic for a catalog first
block; the other twelve slots still require the separate real first-block gate.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import subprocess

from proworksim.software_context_v041 import deduplicate_static_snapshots
from proworksim.software_context_v042 import protected_software_request
from proworksim.software_collaboration_v036 import project_public_test_feedback
from proworksim.software_organization_v042 import build_test_report, test_result_page
from proworksim.storage import atomic_write, digest, json_bytes
from scripts.software_context_replay_v042 import reshape_archived_request
from scripts.software_feedback_qualification_v042 import (
    CORE_REQUIRED_STAGES, INVARIANT_KEYS, PAGINATION_COMBINATIONS, PAGINATION_REQUIRED_STAGES,
    REPRESENTATIVE_REQUIRED_STAGES, configuration_inventory, feedback_invariants,
    pagination_inventory, representative_inventory,
)

VERSION = "software-organization-admission-v0.43"
SOURCE = Path(__file__).resolve().parents[1]
SELF = "scripts/software_organization_admission_v043.py"
EVIDENCE_KEYS = frozenset({"archived_context_replay", "complete_feedback_routes", "code_controls"})
REQUIRED_BINDINGS = frozenset({
    "src/proworksim/software_organization_v042.py", "src/proworksim/software_organization_v040.py",
    "src/proworksim/software_organization_tasks_v040.py", "src/proworksim/software_organization_runtime_v042.py",
    "src/proworksim/software_context_v042.py", "src/proworksim/software_context_v041.py",
    "src/proworksim/software_context_v034.py", "src/proworksim/software_context_v028.py",
    "src/proworksim/software_context_replay_v042.py", "src/proworksim/software_context_replay_v041.py",
    "src/proworksim/candidate_runtime_v015.py", "src/proworksim/training.py", "src/proworksim/harness_sdk.py",
    "src/proworksim/harness_policy_v040.py", "src/proworksim/harness_runtime.py", "src/proworksim/harness_port.py",
    "src/proworksim/team_budget_v033.py", "scripts/software_context_replay_v042.py",
    "scripts/software_feedback_qualification_v042.py", "scripts/measure_organization_feedback_v042.py"})
EVENT_METADATA = frozenset({"sequence", "actor_id", "kind", "logical_time", "operation_id", "action_id", "responsibility_snapshot"})
INHERITED_ORGANIZATION_SOURCES = (
    "src/proworksim/software_organization_v038.py", "src/proworksim/software_organization_v039.py",
    "src/proworksim/software_organization_runtime_v038.py", "src/proworksim/software_organization_runtime_v039.py",
    "src/proworksim/software_organization_tasks_v038.py", "src/proworksim/software_organization_tasks_v039.py",
    "src/proworksim/model_policy.py")


def require(condition, reason):
    if not condition:
        raise ValueError("v043 admission rejected: " + reason)


def reference(path):
    path = Path(path).resolve()
    body = path.read_bytes()
    return {"path": str(path), "sha256": digest(body), "bytes": len(body)}


class EvidenceReader:
    """Read and hash evidence files only; never follow a model weight manifest."""
    def __init__(self):
        self.verified = {}

    def checked(self, ref):
        require(isinstance(ref, dict) and isinstance(ref.get("path"), str)
                and isinstance(ref.get("sha256"), str), "missing immutable evidence reference")
        path = Path(ref["path"]).resolve()
        key = str(path)
        if key not in self.verified:
            data = path.read_bytes()
            self.verified[key] = {"path": key, "sha256": digest(data), "bytes": len(data)}
        actual = self.verified[key]
        require(actual["sha256"] == ref["sha256"] and ("bytes" not in ref or actual["bytes"] == ref["bytes"]),
                "source/evidence SHA or size mismatch: " + key)
        return path

    def json(self, ref):
        return json.loads(self.checked(ref).read_text())

    def existing(self, path):
        ref = reference(path)
        self.checked(ref)
        return ref


def _bindings(values, reader, source_root):
    bindings = {}
    for value in values:
        declared = value.get("source_files")
        require(isinstance(declared, dict) and bool(declared), "missing implementation source bindings")
        for name, expected in declared.items():
            require(not Path(name).is_absolute() and ".." not in Path(name).parts, "invalid source binding path")
            sha = expected["sha256"] if isinstance(expected, dict) else expected
            ref = {"path": str(source_root / name), "sha256": sha}
            if isinstance(expected, dict) and "bytes" in expected:
                ref["bytes"] = expected["bytes"]
            reader.checked(ref)
            require(name not in bindings or bindings[name] == sha, "different old controls bind different source bytes: " + name)
            bindings[name] = sha
    require(REQUIRED_BINDINGS <= bindings.keys(), "incomplete world/page/context/native-renderer bindings")
    return bindings


def _native_identity(a, b, reader):
    require(a == b, "P0-A and P0-B/C native measurement identities differ")
    require(a.get("version") == "software-native-context-measurement-v0.42"
            and a.get("context_limit") == 16384 and a.get("reserved_output_tokens") == 2048
            and a.get("chat_template_kwargs") == {"enable_thinking": False, "preserve_thinking": False}
            and a.get("model_weights_loaded") is False and a.get("new_model_calls") == 0,
            "native measurement profile or bounds changed")
    for name in ("plan", "owner", "base_manifest", "renderer_source"):
        reader.checked(a[name])
    owner, manifest = reader.json(a["owner"]), reader.json(a["base_manifest"])
    profile = owner["inference_profile"]
    require(profile["candidate_id"] == "qwen3.5-9b" and profile["native_tool_prompt"] == "official_xml_single_call"
            and profile["transformers"] == a["transformers_version"]
            and profile["chat_template_kwargs"] == a["chat_template_kwargs"], "original 9B tokenizer/native profile mismatch")
    require(set(a["tokenizer_files"]) == {"tokenizer.json", "tokenizer_config.json", "chat_template.jinja", "vocab.json", "merges.txt", "config.json"},
            "missing original tokenizer/template file bindings")
    for name, ref in a["tokenizer_files"].items():
        reader.checked(ref)
        require(ref["sha256"] == manifest["files"][name]["sha256"] and ref["bytes"] == manifest["files"][name]["bytes"],
                "tokenizer input differs from original base manifest: " + name)
    # This small Python file records the installed version without importing a
    # tokenizer, Torch or Transformers, and without reading any model shard.
    package = reader.existing(a["transformers_module"])
    text = Path(package["path"]).read_text()
    require(re.search(r'__version__\s*=\s*["\x27]' + re.escape(a["transformers_version"]) + r'["\x27]', text) is not None,
            "installed tokenizer library version differs from recorded native profile")
    return copy.deepcopy(a)


def _inherited_bindings(native, reader, source_root):
    """Bind the existing organization dependencies omitted by old source lists.

    These bytes are read from the original v040 execution commit named by its
    already-hashed plan, not inferred from today's files or requalified here.
    """
    plan = reader.json(native["plan"])
    commit = plan["source"]["code_commit"]
    require(re.fullmatch(r"[0-9a-f]{40}", commit) is not None and plan["source"]["code_dirty"] is False,
            "original v040 execution source identity is incomplete")
    bindings = {}
    for name in INHERITED_ORGANIZATION_SOURCES:
        original = subprocess.check_output(["git", "show", commit + ":" + name], cwd=source_root)
        sha = digest(original)
        reader.checked({"path": str(source_root / name), "sha256": sha, "bytes": len(original)})
        bindings[name] = sha
    return bindings, {"original_plan": copy.deepcopy(native["plan"]), "code_commit": commit,
        "source_files": bindings, "scope": "Additional exact bindings for unchanged inherited organization/prompt code; no world or tokenizer replay"}


def verify_encoding(request, encoding, *, prompt=None, ids=None, hard=True):
    """Check saved complete native encodings; do not render or tokenize again."""
    prompt = encoding.get("rendered_prompt") if prompt is None else prompt
    ids = encoding.get("input_ids") if ids is None else ids
    require(isinstance(prompt, str) and isinstance(ids, list) and bool(ids)
            and all(type(value) is int for value in ids), "missing complete native prompt or input IDs")
    tokens = len(ids)
    require(encoding.get("prompt_tokens") == tokens and encoding.get("context_limit") == 16384
            and encoding.get("reserved_output_tokens") == request.get("max_tokens") == 2048,
            "saved actual token count or fixed bounds mismatch")
    require(encoding.get("input_ids_sha256") == digest(json_bytes(ids))
            and encoding.get("rendered_prompt_sha256") == digest(prompt.encode()), "native encoding hash mismatch")
    require(encoding.get("headroom_tokens") == 14336 - tokens and encoding.get("fits") is (tokens <= 14336),
            "saved actual capacity arithmetic mismatch")
    require(encoding.get("native_projection", {}).get("request_sha256") == digest(json_bytes(request)),
            "native prompt is not bound to its exact selected request")
    if hard:
        require(tokens <= 14336, "actual selected hard context capacity exceeded")
    return tokens


def margin_record(location, tokens):
    require(type(tokens) is int and tokens > 0, "invalid protected token diagnostic")
    return {**location, "protected_prompt_tokens": tokens, "hard_headroom_tokens": 14336 - tokens,
            "original_margin_tokens": 1024, "headroom_after_margin_tokens": 13312 - tokens,
            "margin_satisfied": tokens <= 13312, "blocks_v043_first_block": False}


def _projection(original, selected, protected, projection):
    require(projection.get("version") == "software-context-v0.42", "wrong actual context projection version")
    deduplicated, deletion = deduplicate_static_snapshots(original)
    expected_protected, protected_audit = protected_software_request(original)
    require(protected == expected_protected and projection.get("deduplication") == deletion,
            "protected request or permitted exact static deletion differs")
    indices = projection.get("selected_indices", [])
    count = len(original["messages"])
    require(indices == sorted(set(indices)) and all(type(i) is int and 0 <= i < count for i in indices), "invalid selected message indices")
    expected = copy.deepcopy(deduplicated)
    expected["messages"] = [expected["messages"][i] for i in indices]
    require(selected == expected, "selected request changed original text beyond declared exact deletion")
    removed = set(range(count)) - set(indices)
    pairs = protected_audit["complete_tool_rounds"]
    removable = {index for pair in pairs[:-1] for index in pair}
    require(removed <= removable and all(not (set(pair) & removed) or set(pair) <= removed for pair in pairs),
            "selected request removed a protected message or split a tool round")
    require(projection["selected_request_sha256"] == digest(json_bytes(selected))
            and projection["protected_request_sha256"] == digest(json_bytes(protected)), "projection request hash mismatch")
    for request in (selected, protected):
        checks = feedback_invariants(original, request)
        require(set(checks) == INVARIANT_KEYS and all(value is True for value in checks.values()),
                "complete latest visible feedback or dynamic/member facts were changed")


def verify_report(report):
    """A report is an exact fixed Pi040 body and deterministic complete pages."""
    expected = build_test_report(report["visible_result"], actor_id=report["actor_id"], event_identity=report["event_identity"])
    require(report == expected, "untrusted report identity, original body, directory, page boundary or cursor")
    return report


def _visible_test_event(event):
    raw = {key: value for key, value in event.items() if key not in EVENT_METADATA}
    visible = project_public_test_feedback(raw)
    visible["public_diagnostics"] = copy.deepcopy(raw["public_diagnostics"])
    return visible


def _state_reports(state):
    software = state["projects"]["SOFTWARE27"]["software"]
    reports, events = software["test_reports"], state["software_events"]
    for report_id, report in reports.items():
        verify_report(report)
        identity = report["event_identity"]
        require(report_id == report["report_id"] and identity["project_id"] == "SOFTWARE27"
                and all(identity[key] == state[key] for key in ("world_id", "instance_id", "branch_id")),
                "report world/branch binding mismatch")
        tests = [event for event in events if event["kind"] == "test" and event["sequence"] == identity["test_event_sequence"]]
        require(len(tests) == 1 and tests[0]["actor_id"] == report["actor_id"]
                and tests[0]["operation_id"] == identity["operation_id"]
                and _visible_test_event(tests[0]) == report["visible_result"], "report is not the exact original actor/event/version Pi040 feedback")
        saves = [event for event in events if event["kind"] == "test_report_saved" and event["report_id"] == report_id]
        require(len(saves) == 1 and saves[0]["actor_id"] == report["actor_id"]
                and saves[0]["test_event_sequence"] == identity["test_event_sequence"]
                and saves[0]["body_sha256"] == report["body_sha256"], "missing exact report save event")
    return reports


def _p0a(value, reader):
    require(value.get("version") == "software-context-replay-v0.42" and value.get("checked_prefixes") == 32
            and value.get("old_records_reproduced") == 32 and value.get("fit_prefixes") == 32
            and value.get("source_unchanged_during_measurement") is True, "incomplete original 32-prefix hard-capacity evidence")
    rows = value["rows"]
    require(len(rows) == 32 and len({(row["slot_id"], row["member"]) for row in rows}) == 32, "missing or duplicate historical prefix")
    risks, tokens = [], []
    for row in rows:
        require(row["old_record_reproduced"] is True and row["original_request_hash_verified"] is True
                and row["selected_message_hashes_verified"] is True
                and all(item is True for item in row["old_reproduction_checks"].values())
                and row["new_fits"] is True and row["new_page_read_actions"] == 0, "historical input reproduction or copied-prefix hard fit failed")
        files = row["artifacts"]
        for ref in [*files.values(), *row["sources"]]:
            reader.checked(ref)
        def encoded(prefix, hard):
            request = reader.json(files[prefix + "-request.json"])
            encoding = reader.json(files[prefix + "-encoding.json"])
            length = verify_encoding(request, encoding, prompt=reader.checked(files[prefix + "-native-prompt.txt"]).read_text(),
                ids=reader.json(files[prefix + "-input-ids.json"]), hard=hard)
            return request, encoding, length
        archived, _, _ = encoded("archived-original", False)
        old, old_encoding, _ = encoded("v040-selected", False)
        shaped, _, _ = encoded("v042-reshaped", False)
        selected, encoding, length = encoded("v042-selected", True)
        protected, protected_encoding, protected_tokens = encoded("v042-protected", False)
        preparation = row["recorded_preparation"]
        require(digest(json_bytes(archived)) == preparation["original_request_sha256"]
                and digest(json_bytes(old)) == preparation["selected_request_sha256"]
                and all(old_encoding[key] == preparation[key] for key in ("prompt_tokens", "input_ids_sha256", "rendered_prompt_sha256", "context_limit", "reserved_output_tokens")),
                "original native record no longer reproduced by its saved exact encoding")
        transform = reader.json(files["transformation.json"])
        state = reader.json(transform["historical_test_event_source"])
        test_events = {event["operation_id"]: event for event in state["software_events"] if event["kind"] == "test"}
        expected, witness = reshape_archived_request(archived, row, test_events)
        require(shaped == expected and transform["report_copies"] == witness["report_copies"]
                and transform["changes"] == witness["changes"], "copied request added, omitted or changed facts beyond the declared paging transform")
        for report in transform["report_copies"]:
            verify_report(report)
        projection = reader.json(files["v042-selected-projection.json"])
        _projection(shaped, selected, protected, projection)
        require(row["new_selected_prompt_tokens"] == length and row["protected_prompt_tokens"] == protected_tokens
                and row["new_input_ids_sha256"] == encoding["input_ids_sha256"]
                and projection["protected_input_ids_sha256"] == protected_encoding["input_ids_sha256"], "P0-A summary differs from original complete encodings")
        risks.append(margin_record({"evidence": "P0-A", "slot_id": row["slot_id"], "member": row["member"], "call_id": row["call_id"]}, protected_tokens))
        tokens.append(length)
    return {"prefixes": 32, "original_records_reproduced": 32, "hard_fit_prefixes": 32, "max_selected_prompt_tokens": max(tokens)}, risks


def _route_reports(route, directory, reader, actions):
    state_ref = reader.existing(directory / "prepared/world/control/state.json")
    state = reader.json(state_ref)
    reports = _state_reports(state)
    calls, denials = 0, 0
    for action in actions:
        name, member, arguments = action["program_action"], action["member"], action["arguments"]
        response = action["outcome"].get("response") or {}
        if name == "run_tests":
            require(response.get("ok") is True, "CPU route has an unsuccessful test tool response")
            report = reports[response["result"]["report_id"]]
            require(report["actor_id"] == member and response["result"] == test_result_page(report), "test homepage belongs to another actor or changed body")
            calls += 1
        elif name == "read_test_result":
            report = reports.get(arguments["report_id"])
            if report is None or report["actor_id"] != member:
                require(response.get("ok") is False and "result" not in response
                        and response.get("error", {}).get("rejection", {}).get("code") == "test_report_not_readable", "unauthorized report access was not denied without body")
                denials += 1
            else:
                require(response.get("ok") is True and response["result"] == test_result_page(report, arguments["cursor"]),
                        "page read did not preserve its original report, cursor or source version")
    require(calls == route["accepted_cpu_run_tests_calls"] == len(reports)
            == sum(event["kind"] == "test" for event in state["software_events"]), "reading a saved page changed the actual test-event count")
    return reports, denials


def _p0bc(value, reader, qualification_path):
    require(value.get("version") == "software-feedback-route-qualification-v0.42"
            and value.get("source_unchanged_during_measurement") is True
            and value.get("missing_routes") == [] and value.get("unexpected_routes") == [], "incomplete original route inventory")
    specs = configuration_inventory() + representative_inventory() + pagination_inventory()
    routes = value["program_routes"]
    index = {route["route_id"]: route for route in routes}
    require(len(routes) == len(index) == len(specs) == 32 and set(index) == {spec["route_id"] for spec in specs}, "missing or duplicate original CPU route")
    risks, all_tokens, recovered_count, covered_pages, denied_count = [], [], 0, 0, 0
    for spec in specs:
        route = index[spec["route_id"]]
        require(all(route.get(key) == item for key, item in spec.items())
                and route["operational_route_completed"] is True and route["selected_capacity_passed"] is True
                and route["stopped_reason"] is None
                and (bool(route["checks"]) or spec["kind"] in {"message_4000", "format_rejection"})
                and all(check is True for check in route["checks"].values()), "route identity, functionality or original information/permission checks failed")
        stages = route["stages"]
        required = CORE_REQUIRED_STAGES if spec["kind"] == "core" else REPRESENTATIVE_REQUIRED_STAGES.get(spec["kind"], PAGINATION_REQUIRED_STAGES.get(spec["kind"]))
        require(required <= {stage["stage"] for stage in stages} and len(stages) == route["sdk_program_responses"], "missing required feedback-loop stage or actual SDK response")
        directory = qualification_path.parent / route["route_id"]
        actions = reader.json(reader.existing(directory / "program-actions.json"))
        require(len(actions) == len(stages), "program actions and saved requests differ")
        reports, denials = _route_reports(route, directory, reader, actions)
        denied_count += denials
        presented = {}
        for stage, action in zip(stages, actions):
            require(stage["stage"] == action["stage"] and stage["member_id"] == action["member"]
                    and stage["planned_program_action"] == [action["program_action"], action["arguments"]], "saved request does not bind its actual CPU action/member")
            refs = stage["sources"]
            for ref in refs.values():
                reader.checked(ref)
            original, selected, protected, projection, encoding, protected_encoding = [reader.json(refs[name]) for name in (
                "original-request.json", "selected-request.json", "protected-request.json", "projection.json", "native-encoding.json", "protected-native-encoding.json")]
            length = verify_encoding(selected, encoding, hard=True)
            protected_tokens = verify_encoding(protected, protected_encoding, hard=False)
            _projection(original, selected, protected, projection)
            require(stage["fits"] is True and stage["prompt_tokens"] == length and stage["protected_prompt_tokens"] == protected_tokens
                    and stage["input_ids_sha256"] == encoding["input_ids_sha256"]
                    and stage["protected_input_ids_sha256"] == protected_encoding["input_ids_sha256"], "route stage differs from its saved complete encoding")
            for name in ("feedback_invariants", "protected_feedback_invariants"):
                require(set(stage[name]) == INVARIANT_KEYS and all(check is True for check in stage[name].values()), "untrusted saved information invariant")
            for message in selected["messages"]:
                if message.get("role") != "tool":
                    continue
                result = json.loads(message["content"]).get("result", {})
                if not isinstance(result, dict) or "report_id" not in result or "page" not in result:
                    continue
                report = reports.get(result["report_id"])
                require(report is not None and report["actor_id"] == stage["member_id"]
                        and result == test_result_page(report, result["page"]["cursor"]), "selected page body, actor permission or event/version is untrusted")
                key = (report["report_id"], result["page"]["index"], result["page"]["sha256"])
                presented.setdefault(key, []).append(stage["stage"])
            risks.append(margin_record({"evidence": "P0-B/C", "route_id": route["route_id"], "stage": stage["stage"], "member": stage["member_id"]}, protected_tokens))
            all_tokens.append(length)
        recoveries = route["report_recovery"]
        if route["kind"] == "core":
            require({recovery["label"] for recovery in recoveries} == {"failed", "passed"}, "missing complete failed/passed report recovery")
        if route["kind"] in PAGINATION_COMBINATIONS:
            require(bool(recoveries), "missing pagination combination recovery")
        for recovery in recoveries:
            stored = reader.json(recovery["recovery_source"])
            report = reports[recovery["report_id"]]
            results = stored["page_results_from_actual_tools"]
            require(stored["actor_id"] == report["actor_id"] == recovery["actor_id"]
                    and stored["body"] == report["body"] and stored["visible_result"] == report["visible_result"]
                    and results == [test_result_page(report, page["cursor"]) for page in report["pages"]]
                    and "".join(result["page"]["text"] for result in results) == report["body"]
                    and recovery["exact_recovery"] is True and recovery["run_tests_count_unchanged_by_page_reads"] is True,
                    "complete original allowed report was not exactly recovered by authorized pages")
            coverage = [{"page_index": page["index"], "sha256": page["sha256"],
                "fitting_selected_stages": presented.get((report["report_id"], page["index"], page["sha256"]), [])} for page in report["pages"]]
            require(all(row["fitting_selected_stages"] for row in coverage)
                    and coverage == recovery["subsequent_selected_input_coverage"]
                    and recovery["all_pages_presented_in_subsequent_fitting_requests"] is True,
                    "a recovered page never entered the subsequent fitting selected request")
            recovered_count += 1
            covered_pages += len(coverage)
        budget = reader.json(reader.existing(directory / "team-budget-cpu-fixture.json"))
        require(budget["decisions"] == budget["attempts"] == len(stages), "page/program calls received uncharged opportunities")
    require(len(all_tokens) == 370 and recovered_count == 36 and covered_pages == 211 and denied_count == 2,
            "original finite request/recovery/permission denominators changed")
    return {"routes": 32, "core_routes": 16, "representative_routes": 12, "pagination_routes": 4,
        "operational_routes_completed": 32, "hard_fit_requests": len(all_tokens), "recovered_complete_reports": recovered_count,
        "recovered_pages_presented": covered_pages, "permission_denials_verified": denied_count,
        "max_selected_prompt_tokens": max(all_tokens)}, risks


def build_admission(evidence_refs, *, data_root, source_root=SOURCE):
    source_root, data_root = Path(source_root).resolve(), Path(data_root).resolve()
    require(set(evidence_refs) == EVIDENCE_KEYS, "require original P0-A, P0-B/C and code-control references")
    reader = EvidenceReader()
    a, b, code = [reader.json(evidence_refs[name]) for name in ("archived_context_replay", "complete_feedback_routes", "code_controls")]
    require(a.get("passed") is False and b.get("passed") is False and code.get("passed") is False,
            "the original v042 qualifications must remain unchanged passed=false")
    for value in (a, b, code):
        require(value.get("new_model_calls") == 0 and value.get("new_backward_calls") == 0, "reused qualification is not CPU-only")
    require(code.get("version") == "software-organization-execution-v0.42"
            and code.get("capacity_controls_passed") is False and bool(code.get("checks"))
            and all(check["exit_code"] == 0 for check in code["checks"]), "original necessary code controls did not pass")
    require(code["capacity_controls"] == {key: evidence_refs[key] for key in ("archived_context_replay", "complete_feedback_routes")},
            "code controls reference different capacity evidence")
    for check in code["checks"]:
        reader.checked(check["log"])
    sources = _bindings((a, b, code), reader, source_root)
    native = _native_identity(a["native_measurement_identity"], b["native_measurement_identity"], reader)
    inherited, inherited_evidence = _inherited_bindings(native, reader, source_root)
    require(all(name not in sources or sources[name] == sha for name, sha in inherited.items()),
            "inherited execution source conflicts with old qualification source")
    sources.update(inherited)
    if "source_snapshot_manifest" in b:
        reader.checked(b["source_snapshot_manifest"])
    a_result, a_risks = _p0a(a, reader)
    b_result, b_risks = _p0bc(b, reader, Path(evidence_refs["complete_feedback_routes"]["path"]))
    all_risks = a_risks + b_risks
    deficient = [row for row in all_risks if not row["margin_satisfied"]]
    result = {"version": VERSION, "kind": "layered-reuse-of-original-v042-cpu-evidence", "passed": True,
        "source_root": str(source_root), "data_root": str(data_root), "evidence_refs": copy.deepcopy(evidence_refs),
        "old_qualification_passed": {key: False for key in EVIDENCE_KEYS}, "source_files": sources,
        "admission_implementation": reference(source_root / SELF), "native_measurement_identity": native,
        "inherited_organization_bindings": inherited_evidence,
        "layers": {
            "binding": {"passed": True, "source_file_count": len(sources), "verified_artifact_count": len(reader.verified)},
            "code_controls": {"passed": True, "original_checks": copy.deepcopy(code["checks"])},
            "information_permissions": {"passed": True, **b_result},
            "selected_capacity": {"passed": True, "context_limit": 16384, "reserved_output_tokens": 2048,
                "P0_A": a_result, "P0_BC": b_result},
            "engineering_margin": {"required_for_admission": False, "original_margin_tokens": 1024,
                "protected_limit_for_diagnostic": 13312, "checked_locations": len(all_risks),
                "deficient_locations": deficient, "deficient_location_count": len(deficient),
                "max_protected_prompt_tokens": max(row["protected_prompt_tokens"] for row in all_risks)},
            "model_stage": {"first_block_only": True, "first_block": "block-r1-s0", "root": "catalog",
                "condition_order": ["PT", "SB", "ST", "PB"], "initially_released_slots": 4,
                "remaining_slots": 12, "remaining_require_frozen_first_block_mechanical_gate": True,
                "business_score_message_page_birth_counts_are_not_release_criteria": True}},
        "verified_artifacts": sorted(reader.verified.values(), key=lambda row: row["path"]),
        "new_model_calls": 0, "new_backward_calls": 0, "new_tokenizations": 0, "new_world_routes": 0,
        "model_weights_loaded": False,
        "scope": "New explicitly authorized v043 admission only. Preserve original v042 false qualifications; exact source, information/permission and actual selected hard capacity remain mandatory. Known 1024-token protected-margin deficits permit only the catalog first block, never automatic release of the other twelve or old training queues."}
    result["admission_sha256"] = digest(json_bytes(result))
    return result


def create_admission(data_root, source_root, output):
    source_root, output = Path(source_root).resolve(), Path(output).resolve()
    require(not output.exists(), "refuse to overwrite an existing admission record")
    old_report = json.loads((source_root / "docs/experiments/software-organization-v042.json").read_text())
    reader = EvidenceReader()
    code_ref = old_report["qualification"]
    code = reader.json(code_ref)
    refs = {**code["capacity_controls"], "code_controls": code_ref}
    result = build_admission(refs, data_root=data_root, source_root=source_root)
    atomic_write(output, json_bytes(result))
    return result


def _validate_current_sources(value, reader, source_root):
    """A frozen checkout may have a different root, but must have exact bytes."""
    root = Path(source_root).resolve()
    reader.checked(value["admission_implementation"])
    require(digest((root / SELF).read_bytes()) == value["admission_implementation"]["sha256"],
            "new admission implementation changed after recording")
    for name, sha in value["source_files"].items():
        reader.checked({"path": str(root / name), "sha256": sha})


def validate_admission(path_or_ref, source_root=SOURCE):
    reader = EvidenceReader()
    value = reader.json(path_or_ref if isinstance(path_or_ref, dict) else reference(path_or_ref))
    payload = {key: item for key, item in value.items() if key != "admission_sha256"}
    require(value.get("version") == VERSION and value.get("passed") is True
            and value.get("admission_sha256") == digest(json_bytes(payload)), "new admission record identity or status changed")
    _validate_current_sources(value, reader, source_root)
    for ref in value["verified_artifacts"]:
        reader.checked(ref)
    require(all(value["layers"][name].get("passed") is True for name in
                ("binding", "code_controls", "information_permissions", "selected_capacity"))
            and value["layers"]["engineering_margin"]["required_for_admission"] is False
            and value["layers"]["model_stage"]["first_block_only"] is True
            and value["layers"]["model_stage"]["initially_released_slots"] == 4
            and value["layers"]["model_stage"]["remaining_require_frozen_first_block_mechanical_gate"] is True,
            "mandatory admission layers or limited first-block scope changed")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default=str(SOURCE))
    parser.add_argument("--source-root", default=str(SOURCE))
    parser.add_argument("--output", default=str(SOURCE / "runs/v043-controls/layered-admission.json"))
    args = parser.parse_args()
    result = create_admission(args.data_root, args.source_root, args.output)
    print(json.dumps({"passed": result["passed"], "first_block": result["layers"]["model_stage"]["first_block"],
        "margin_diagnostic_locations": result["layers"]["engineering_margin"]["deficient_location_count"]}))


if __name__ == "__main__":
    main()
