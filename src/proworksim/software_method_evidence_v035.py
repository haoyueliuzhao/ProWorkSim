"""Read-only software work evidence with separate actor-visible input proofs.

World facts establish immutable artifacts and execution. Actual selected request
and resident token bindings establish presentation. Neither layer substitutes
for the other, and no model reasoning, new test or acceptance execution occurs.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from .member_views import member_view
from .storage import digest, json_bytes, read_json
from .team_rollout import optimizer_scope_allows_update, validate_window, work_validity

VERSION = "software-method-evidence-v0.35"



# Only old development records lack the new public contract-symbol field. This
# audit-only fallback names already published interfaces, never test answers.
_DEVELOPMENT_SYMBOLS = {
    "mm-directory-rootgoal-v034": {"models.py": ["RecordSchema"], "consumer.py": ["catalog"]},
    "mm-name-index-rootgoal-v034": {"models.py": ["NameSchema"], "search.py": ["find_matches"],
                                    "exporter.py": ["export_names"]},
}


def _contract_symbols(case):
    value = case.get("contract_symbols", case.get("source_contract", {}).get("contract_symbols"))
    if value is None and case.get("usage") == "model_interface_development":
        value = _DEVELOPMENT_SYMBOLS.get(case.get("case_id"))
    if not isinstance(value, dict) or not value:
        return {}
    if any(path not in case["editable_paths"] or path == "test_member.py"
           or not isinstance(names, list) or not names or len(set(names)) != len(names)
           or any(not isinstance(name, str) or not name.isidentifier() for name in names)
           for path, names in value.items()):
        raise ValueError("Public contract symbols must bind declared production files and names")
    return copy.deepcopy(value)


def _contract_definition_fingerprints(text, symbols):
    """Conservative public-definition change check, not authorship or utility.

    Formatting/comments/docstrings and added unrelated module helpers cannot
    create a partner class. Dynamic aliases and ambiguous definitions are left
    unknown. Whole-file bytes must separately survive the real import chain.
    """
    if not symbols:
        return None
    try:
        tree = ast.parse(text)
        definitions = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in symbols:
                    if node.name in definitions:
                        return None
                    definitions[node.name] = node
            elif any(isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)
                     and item.id in symbols for item in ast.walk(node)):
                return None
        if set(definitions) != set(symbols):
            return None
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    node.body.pop(0)
        return {name: digest(ast.dump(definitions[name], include_attributes=False).encode()) for name in sorted(symbols)}
    except (SyntaxError, TypeError, ValueError, RecursionError):
        return None


def _sha(value):
    return digest(json_bytes(value))


def _ref(value):
    if not isinstance(value, dict):
        return None
    if not all(isinstance(value.get(key), str) for key in ("object_id", "version_id")):
        return None
    return value["object_id"], value["version_id"]


def _file(path):
    path = Path(path)
    return {"path": str(path.resolve()), "file_sha256": digest(path.read_bytes())}


def _json_content(message):
    try:
        value = json.loads(message.get("content", ""))
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _nested_patch_metadata(value, patch):
    if isinstance(value, dict):
        if (value.get("patch_id") == patch["patch_id"] and value.get("author") == patch["author"]
                and value.get("source_reference") == patch["source_reference"]):
            return True
        return any(_nested_patch_metadata(item, patch) for item in value.values())
    if isinstance(value, list):
        return any(_nested_patch_metadata(item, patch) for item in value)
    return False


def _world_ref(event, action=None):
    return {"world_sequence": event["sequence"], "kind": event["kind"],
            "actor_id": event["actor_id"], "operation_id": event["operation_id"],
            "action_id": event["action_id"],
            "experience_sequence": action["sequence"] if action else None,
            "model_call_id": action["payload"].get("model_call_id") if action else None,
            "event_sha256": _sha(event)}


class _Evidence:
    def __init__(self, folder, rollout, assessment):
        self.folder, self.rollout, self.assessment = Path(folder), rollout, assessment
        self.episode = self.folder / "episode"
        self.manifest = read_json(self.episode / "manifest.json")
        if (self.manifest != rollout["manifest"] or self.manifest["status"] != "closed"
                or digest((self.episode / "manifest.json").read_bytes()) != rollout["manifest_sha256"]
                or self.manifest["episode_id"] != rollout["rollout_id"]):
            raise ValueError("Closed original manifest/rollout binding differs")
        validity = rollout["work_validity"]
        checks = [check for part in validity["components"].values() for check in part["checks"]]
        if work_validity(checks, spec_id=validity["spec_id"]) != validity:
            raise ValueError("Complete validity is not its actual component conjunction")
        if rollout["window"]["team_policy_fingerprint"] != _sha(self.manifest["policies"]):
            raise ValueError("Actual team policy differs from the exact window")
        if rollout["reward_eligibility"].get("source_assessment_sha256") != _sha(assessment):
            raise ValueError("Original independent assessment binding changed")
        self.start = read_json(self.episode / "start/control/state.json")
        self.end = read_json(self.episode / "end/control/state.json")
        self.case = self.manifest["scenario"]["variation"]["software_case"]
        projects = [p["software"] for p in self.end["projects"].values() if "software" in p]
        if len(projects) != 1 or projects[0]["case"] != self.case:
            raise ValueError("World source contract differs from the frozen case")
        self.facts = projects[0]
        if list(rollout["members"]) != self.case["active_roles"]:
            raise ValueError("Stable actual members differ from the public case")
        self.events = rollout["events"]
        archived = read_json(self.episode / self.manifest["experience"]["path"])
        interval = self.manifest["experience"]
        if archived["events"][interval["start"]:interval["end"]] != self.events:
            raise ValueError("Rollout omitted or changed original episode events")
        old_events = self.start.get("software_events", [])
        if self.end.get("software_events", [])[:len(old_events)] != old_events:
            raise ValueError("World event history changed")
        self.world = self.end.get("software_events", [])[len(old_events):]
        self.actions = [event for event in self.events if event["kind"] == "tool_call"]
        self.action_by_operation = {}
        self.action_by_tool_id = {}
        for action in self.actions:
            payload = action["payload"]
            response = payload["response"]
            if response.get("ok") is True and response.get("command_committed") is True:
                self.action_by_operation[response["command_id"]] = action
            if payload.get("model_tool_call_id"):
                self.action_by_tool_id[(action["worker_id"], payload["model_tool_call_id"])] = action
        self.world_actions = {}
        for event in self.world:
            operation = event["operation_id"]
            receipt = self.end["operation_commits"].get(operation)
            action = self.action_by_operation.get(operation)
            if (receipt is None or action is None or receipt["bound_actor"] != event["actor_id"]
                    or action["worker_id"] != event["actor_id"]
                    or receipt["public_result"] != action["payload"]["response"]
                    or action["payload"]["response"]["action_id"] != event["action_id"]):
                raise ValueError("World event lacks its original member action and commit receipt")
            self.world_actions[event["sequence"]] = action
        self.bundles, self.bundle_proofs = {}, {}
        self.views = {member: member_view(rollout, member) for member in rollout["members"]}
        self.inputs, self.calls, self.presentations, self.issues = [], [], [], []
        self._actual_inputs()

    def bundle(self, reference):
        key = _ref(reference)
        if key is None:
            raise ValueError("Missing immutable version reference")
        if key not in self.bundles:
            artifact = self.end["artifacts"][key[0]]
            metadata = artifact["versions"][key[1]]
            path = self.episode / "end/control/versions" / artifact["artifact_id"] / key[1] / artifact["filename"]
            raw = path.read_bytes()
            if digest(raw) != metadata["sha256"]:
                raise ValueError("Immutable version bytes changed")
            self.bundles[key] = json.loads(raw)
            self.bundle_proofs[key] = {"source_reference": copy.deepcopy(reference), **_file(path),
                                      "bundle_sha256": _sha(self.bundles[key]),
                                      "files_sha256": _sha(self.bundles[key]["files"])}
        return self.bundles[key]

    def _actual_inputs(self):
        starts = [e for e in self.events if e["kind"] == "model_attempt" and e["payload"].get("stage") == "started"]
        folders = sorted((self.folder / "raw-transport/context-projections").glob("request-*"))
        if len(starts) != len(folders):
            self.issues.append("Actual attempt count differs from durable selected-request archive")
            return
        for start, folder in zip(starts, folders):
            payload, member = start["payload"], start["worker_id"]
            finish = [e for e in self.events if e["kind"] == "model_attempt"
                      and e["payload"].get("stage") == "finished"
                      and e["payload"].get("attempt_id") == payload["attempt_id"]]
            if len(finish) != 1:
                self.issues.append("Missing unique original attempt completion: " + payload["attempt_id"])
                continue
            original = read_json(folder / "original-request.json")
            selected = read_json(folder / "selected-request.json")
            projection = read_json(folder / "projection.json")
            response = read_json(folder / "response.json")
            if (original != payload["request"] or finish[0]["payload"].get("request") != original
                    or response != finish[0]["payload"].get("response")
                    or projection["original_request_sha256"] != _sha(original)
                    or projection["selected_request_sha256"] != _sha(selected)):
                raise ValueError("Actual request, projection or response archive mismatch")
            body = response.get("body", {})
            trace = body.get("token_trace", {})
            if response.get("http_status") != 200 or not trace.get("input_ids"):
                if body.get("generation_started") is False:
                    continue
                self.issues.append("Attempt lacks actual native token evidence: " + payload["attempt_id"])
                continue
            prompt = body.get("prompt_projection", {})
            if not all(prompt.get(key) for key in ("request_sha256", "rendered_prompt_sha256")):
                self.issues.append("Missing native prompt presentation proof: " + payload["attempt_id"])
                continue
            if any(type(token) is not int or token < 0 for token in trace["input_ids"] + trace["output_ids"]):
                raise ValueError("Native input/output token IDs must be actual nonnegative integers")
            matched_view = [d for d in self.views[member]["decisions"] if d["call_id"] == payload["call_id"]]
            if (finish[0]["payload"].get("status") != "success"
                    or projection["input_ids_sha256"] != _sha(trace["input_ids"])
                    or projection["selected_prompt_tokens"] != len(trace["input_ids"])
                    or body["usage"]["prompt_tokens"] != len(trace["input_ids"])
                    or body["usage"]["completion_tokens"] != len(trace["output_ids"])
                    or prompt.get("request_sha256") != _sha(selected)
                    or prompt.get("rendered_prompt_sha256") != projection["rendered_prompt_sha256"]
                    or len(matched_view) != 1 or matched_view[0].get("tokens") != trace
                    or body.get("online_window_id") != self.rollout["window"]["window_id"]):
                raise ValueError("Actual native selected input/usage/member target binding differs")
            preparation_path = folder / "budget-preparation.json"
            if preparation_path.exists():
                preparation = read_json(preparation_path)
                if (preparation["original_request_sha256"] != _sha(original)
                        or preparation["selected_request_sha256"] != _sha(selected)
                        or preparation["input_ids_sha256"] != projection["input_ids_sha256"]
                        or preparation["actor_identity"] != body["actor_identity"]):
                    raise ValueError("Admitted native request identity differs from its generation")
            record = {"call_id": payload["call_id"], "attempt_id": payload["attempt_id"],
                      "member_id": member, "sequence": start["sequence"],
                      "finished_sequence": finish[0]["sequence"], "decision_index": payload["decision_index"],
                      "original_request_sha256": _sha(original), "selected_request_sha256": _sha(selected),
                      "input_ids_sha256": _sha(trace["input_ids"]), "output_ids_sha256": _sha(trace["output_ids"]),
                      "rendered_prompt_sha256": projection["rendered_prompt_sha256"],
                      "input_tokens": len(trace["input_ids"]), "own_output_tokens": len(trace["output_ids"]),
                      "actor_identity": copy.deepcopy(body["actor_identity"]),
                      "selected_request": _file(folder / "selected-request.json"),
                      "response": _file(folder / "response.json"), "projection": _file(folder / "projection.json"),
                      "native_prompt_binding": copy.deepcopy(prompt),
                      "whole_round_indices_removed": projection.get("removed_indices", []),
                      "scope": "Exact archived selected-request -> native preparation/render hash -> actual token IDs -> same member targets. No new tokenization or model call."}
            self.calls.append(record)
            self.inputs.append((record, selected))
            for index, message in enumerate(selected["messages"]):
                if message.get("role") != "tool":
                    continue
                action = self.action_by_tool_id.get((member, message.get("tool_call_id")))
                parsed = _json_content(message)
                if action is None or _sha(parsed) != _sha(action["payload"]["response"]):
                    # Harness workbench reads are separately scoped; do not
                    # turn unbound contents into a WorldCore information edge.
                    continue
                if action["sequence"] >= start["sequence"]:
                    raise ValueError("A tool result cannot precede its actual action")
                self.presentations.append({"member_id": member, "call_id": record["call_id"],
                    "input_sequence": record["sequence"], "message_index": index,
                    "message_sha256": _sha(message), "selected_request_sha256": record["selected_request_sha256"],
                    "action_sequence": action["sequence"], "action": action["payload"]["action"],
                    "action_model_call_id": action["payload"].get("model_call_id"),
                    "tool_call_id": message["tool_call_id"], "public_response_sha256": _sha(parsed),
                    "visible_result": copy.deepcopy(parsed.get("result")), "visible_error": copy.deepcopy(parsed.get("error"))})
        verified = {call["call_id"] for call in self.calls}
        for member, view in self.views.items():
            required = {d["call_id"] for d in view["decisions"] if d.get("actor_trainable") is True}
            if not required <= verified:
                self.issues.append("Not every trusted own target has a verified actual selected input: " + member)

    def visible(self, action, *, before=None):
        return [p for p in self.presentations if p["action_sequence"] == action["sequence"]
                and p["member_id"] == action["worker_id"]
                and (before is None or p["input_sequence"] < before)]

    def world_action(self, event):
        return self.world_actions[event["sequence"]]

    def metadata_seen(self, member, patch, before):
        found = []
        for record, request in self.inputs:
            if record["member_id"] != member or record["sequence"] >= before:
                continue
            for index, message in enumerate(request["messages"]):
                payload = _json_content(message)
                if not payload:
                    continue
                values = []
                if message.get("role") == "user" and isinstance(payload.get("observation"), dict):
                    observation = payload["observation"]
                    values = [observation.get("patches"), observation.get("all_fixed_patches")]
                elif message.get("role") == "tool":
                    action = self.action_by_tool_id.get((member, message.get("tool_call_id")))
                    if action and _sha(payload) == _sha(action["payload"]["response"]):
                        values = [payload.get("result")]
                if any(_nested_patch_metadata(value, patch) for value in values):
                    found.append({"call_id": record["call_id"], "input_sequence": record["sequence"],
                                  "message_index": index, "selected_request_sha256": record["selected_request_sha256"],
                                  "message_sha256": _sha(message)})
        return found

    def delivery_chain(self):
        delivery = self.facts["deliveries"][-1] if self.facts["deliveries"] else None
        empty = {"verified": False, "delivery": copy.deepcopy(delivery), "ancestors": [],
                 "peer_integrations": [], "peer_fixed_content_acquisitions": [],
                 "unresolved_peer_dependencies": [], "retained_own_production_edit_paths": [],
                 "current_test_feedback_seen_before_submit": False}
        if delivery is None:
            return empty
        if self.assessment.get("delivery") != delivery:
            raise ValueError("Independent assessment does not name the latest exact fixed delivery")
        final = self.bundle(delivery["source_reference"])
        if (_sha(final) != delivery["source_sha256"] or _sha(final["files"]) != delivery["files_sha256"]
                or self.assessment.get("source_reference") != delivery["source_reference"]
                or self.assessment.get("files_sha256") != delivery["files_sha256"]):
            raise ValueError("Delivery/assessment immutable bytes differ")
        submissions = [e for e in self.world if e["kind"] == "submit" and e["delivery_id"] == delivery["delivery_id"]]
        if len(submissions) != 1:
            raise ValueError("Delivery lacks one actual submit event")
        submit = submissions[0]
        submit_action = self.world_action(submit)
        actor = delivery["actor_id"]
        mutations = [e for e in self.world if e["kind"] in {"edit", "integrate"}]
        by_reference = {}
        for event in mutations:
            key = _ref(event["source_reference"])
            if key in by_reference:
                raise ValueError("One immutable version has multiple production events")
            by_reference[key] = event
        current, backward, visited = _ref(delivery["source_reference"]), [], set()
        while current in by_reference:
            if current in visited:
                raise ValueError("Version ancestry cycle")
            visited.add(current)
            event = by_reference[current]
            if event["actor_id"] != actor or event["sequence"] >= submit["sequence"]:
                return {**empty, "reason": "Ancestry crosses unsupported actor/version boundary"}
            backward.append(event)
            current = _ref(event["previous_reference"])
        if (current is None or current[0] not in self.start["artifacts"]
                or current[1] not in self.start["artifacts"][current[0]]["versions"]
                or self.start["artifacts"][current[0]].get("owner") != actor):
            return {**empty, "reason": "Delivery ancestry does not terminate at the member's actual initial copy"}
        ancestry = list(reversed(backward))
        initial_ref = {"object_id": current[0], "version_id": current[1]}
        initial = self.bundle(initial_ref)
        contract_symbols = _contract_symbols(self.case)
        production = [p for p in self.case["editable_paths"] if p != "test_member.py"]
        if not contract_symbols:
            return {**empty, "reason": "No frozen public contract symbols identify production changes"}
        verified_calls = {c["call_id"] for c in self.calls}
        if any(self.world_action(e)["payload"].get("model_call_id") not in verified_calls for e in ancestry + [submit]):
            return {**empty, "reason": "Delivery production/submit action lacks actual native member input binding"}
        # Check actual write contents against immutable versions, never comments
        # or claims that a patch was used.
        for event in ancestry:
            prior, after = self.bundle(event["previous_reference"]), self.bundle(event["source_reference"])
            if event["kind"] == "edit":
                path = event["path"]
                action = self.world_action(event)["payload"]
                args = action["arguments"]
                expected = (args["text"] if action["action"] == "write_file" else
                            prior["files"][path].replace(args["old"], args["new"], 1))
                if (digest(prior["files"][path].encode()) != event["before_sha256"]
                        or digest(after["files"][path].encode()) != event["after_sha256"]
                        or after["files"][path] != expected):
                    raise ValueError("Actual edit does not produce its recorded immutable bytes")
        fixed = [e for e in self.world if e["kind"] == "patch_fixed"
                 and e["source_reference"] == delivery["source_reference"]
                 and e["actor_id"] == actor and e["sequence"] < submit["sequence"]]
        tests = [e for e in self.world if e["kind"] == "test"
                 and e["sequence"] == delivery["test_sequence"] and e["actor_id"] == actor
                 and e["source_reference"] == delivery["source_reference"]
                 and e.get("executed") is True and e["sequence"] < submit["sequence"]]
        if not fixed or len(tests) != 1:
            return {**empty, "reason": "No current exact-version fixed patch and actual executed test"}
        test = tests[0]
        test_action = self.world_action(test)
        test_seen = self.visible(test_action, before=submit_action["sequence"])
        test_seen = [p for p in test_seen if p["visible_result"].get("source_reference") == delivery["source_reference"]
                     and p["visible_result"].get("files_sha256") == delivery["files_sha256"]
                     and p["visible_result"].get("executed") is True]
        final_definitions = {path: _contract_definition_fingerprints(final["files"][path], names)
                             for path, names in contract_symbols.items()}
        initial_definitions = {path: _contract_definition_fingerprints(initial["files"][path], names)
                               for path, names in contract_symbols.items()}
        own_edits = sorted({e["path"] for e in ancestry if e["kind"] == "edit"
                            and e["path"] in contract_symbols and final_definitions[e["path"]] is not None
                            and initial_definitions[e["path"]] is not None
                            and final_definitions[e["path"]] != initial_definitions[e["path"]]})
        peers, acquired = [], []
        for index, event in enumerate(ancestry):
            if event["kind"] != "integrate":
                continue
            patch = self.facts["patches"].get(event["patch_id"])
            if patch is None:
                raise ValueError("Integration refers to an unknown fixed patch")
            if patch["author"] == actor:
                continue
            publications = [e for e in self.world if e["kind"] == "patch_fixed"
                            and e["patch_id"] == patch["patch_id"] and e["actor_id"] == patch["author"]
                            and e["source_reference"] == patch["source_reference"] and e["sequence"] < event["sequence"]]
            if len(publications) != 1:
                raise ValueError("Peer integration lacks one earlier actual fixed publication")
            source, baseline = self.bundle(patch["source_reference"]), self.bundle(patch["base_reference"])
            previous = self.bundle(event["previous_reference"])
            descendants = [self.bundle(e["source_reference"]) for e in ancestry[index:]]
            if (event["input_reference"] != patch["source_reference"]
                    or _sha(source) != patch["source_sha256"] or _sha(source["files"]) != patch["files_sha256"]):
                raise ValueError("Integration fixed input identity differs")
            peer_definitions = {path: _contract_definition_fingerprints(source["files"][path], names)
                                for path, names in contract_symbols.items()}
            base_definitions = {path: _contract_definition_fingerprints(baseline["files"][path], names)
                                for path, names in contract_symbols.items()}
            retained = [{"path": path, "public_contract_definition_sha256": _sha(peer_definitions[path]), "peer_file_sha256": digest(source["files"][path].encode()),
                         "final_file_sha256": digest(final["files"][path].encode()),
                         "continuous_identical_descendants": len(descendants), "nontrivial_vs_patch_base": True,
                         "import_changed_recipient_file": True}
                        for path in patch["changed_paths"] if path in contract_symbols
                        and peer_definitions[path] is not None and base_definitions[path] is not None
                        and peer_definitions[path] != base_definitions[path]
                        and source["files"][path] != baseline["files"][path]
                        and source["files"][path] != previous["files"][path]
                        and all(tree["files"][path] == source["files"][path] for tree in descendants)
                        and final["files"][path] == source["files"][path]]
            action = self.world_action(event)
            import_seen = self.visible(action, before=test_action["sequence"])
            import_seen = [p for p in import_seen if p["visible_result"].get("source_reference") == event["source_reference"]
                           and patch["patch_id"] in p["visible_result"].get("included_patch_ids", [])]
            metadata_seen = self.metadata_seen(actor, patch, test_action["sequence"])
            source_presented = []
            for presentation in self.presentations:
                value = presentation.get("visible_result") or {}
                path = value.get("path")
                if (presentation["member_id"] == actor and presentation["input_sequence"] < submit_action["sequence"]
                        and presentation["action"] == "read_file" and path in production
                        and _ref(value.get("source_reference")) in {_ref(patch["source_reference"]), _ref(event["source_reference"])}
                        and value.get("text") == "\n".join(source["files"][path].splitlines())):
                    source_presented.append({"path": path, "call_id": presentation["call_id"],
                                             "message_sha256": presentation["message_sha256"]})
            qualifying = bool(event.get("status") == "merged" and not event.get("conflicts") and retained
                              and import_seen and metadata_seen and test_seen
                              and patch["patch_id"] in final["included_patch_ids"])
            peers.append({"patch_id": patch["patch_id"], "producer": patch["author"], "recipient": actor,
                          "fixed_source_reference": copy.deepcopy(patch["source_reference"]),
                          "integration": _world_ref(event, action), "status": event.get("status"),
                          "conflicts": event.get("conflicts", []), "file_materialized": True,
                          "import_receipt_presented": bool(import_seen), "import_receipt_presentations": import_seen,
                          "fixed_patch_metadata_presented": bool(metadata_seen), "metadata_presentations": metadata_seen,
                          "source_text_presented": bool(source_presented), "source_text_presentations": source_presented,
                          "retained_production_files": retained, "qualifying_fixed_product_consumption": qualifying,
                          "scope": "Materialized file content is a world fact; metadata/receipt/source-text presentation are separate actual-input facts."})
        for event in self.world:
            if event["kind"] not in {"read", "search"} or event["actor_id"] != actor or event["sequence"] >= submit["sequence"]:
                continue
            peer = next((p for p in self.facts["patches"].values() if p["author"] != actor
                         and p["source_reference"] == event.get("source_reference")), None)
            if peer and self.visible(self.world_action(event), before=submit_action["sequence"]):
                acquired.append({"patch_id": peer["patch_id"], "producer": peer["author"],
                                 "read": _world_ref(event, self.world_action(event)), "path": event.get("path"),
                                 "scope": "Actual peer fixed-source presentation, not proof of manual code consumption"})
        peer_ids = {p["patch_id"] for p in peers}
        unresolved = [pid for pid in final["included_patch_ids"]
                      if pid not in self.facts["patches"]
                      or self.facts["patches"][pid]["author"] != actor and pid not in peer_ids]
        return {"verified": True, "delivery": copy.deepcopy(delivery), "submit": _world_ref(submit, submit_action),
                "initial_reference": initial_ref, "production_paths": production, "contract_symbols": contract_symbols,
                "ancestors": [_world_ref(e, self.world_action(e)) | {
                    "source_reference": e["source_reference"], "previous_reference": e["previous_reference"],
                    "path": e.get("path"), "patch_id": e.get("patch_id")} for e in ancestry],
                "current_version_test": _world_ref(test, test_action),
                "current_test_feedback_seen_before_submit": bool(test_seen), "test_feedback_presentations": test_seen,
                "fixed_patch_events": [_world_ref(e, self.world_action(e)) for e in fixed],
                "retained_own_production_edit_paths": own_edits, "peer_integrations": peers,
                "peer_fixed_content_acquisitions": acquired, "unresolved_peer_dependencies": unresolved}


def build_software_evidence(slot_dir, *, rollout=None, assessment=None, expected_window=None):
    """Audit an archived slot or bind a just-exported rollout before entry exists."""
    folder = Path(slot_dir).resolve()
    if rollout is None:
        rollout = read_json(folder / "entry.json")["rollout"]
    if assessment is None:
        assessment = read_json(folder / "assessment.json")
    window = validate_window(rollout["window"])
    if expected_window is not None and window != expected_window:
        raise ValueError("Do not combine different exact xi, Gamma, team policy or collection windows")
    archive = _Evidence(folder, rollout, assessment)
    chain = archive.delivery_chain()
    verified = {c["call_id"] for c in archive.calls}
    members = {}
    for member, view in archive.views.items():
        own = [d for d in view["decisions"] if d.get("actor_trainable") is True]
        # Hash existing actual targets; never reconstruct labels from teammate
        # work, backend facts or edited presentation.
        targets = [{"call_id": d["call_id"], "input_ids_sha256": _sha(d["tokens"]["input_ids"]),
                    "output_ids_sha256": _sha(d["tokens"]["output_ids"]),
                    "behavior_logprobs_sha256": _sha(d["tokens"]["behavior_logprobs"]),
                    "labels_sha256": _sha(d["labels"]), "loss_mask_sha256": _sha(d["loss_mask"])} for d in own]
        members[member] = {"member_id": member, "origin": view["origin"],
                           "own_action_count": view["own_action_count"], "own_action_tokens": view["own_action_tokens"],
                           "complete_actor_trajectory": view["complete_actor_trajectory"],
                           "actual_input_bindings_complete": all(d["call_id"] in verified for d in own),
                           "own_targets_sha256": _sha(targets), "own_target_records": targets,
                           "method_does_not_change_actor_targets": True}
    organization = []
    for event in archive.world:
        if event["kind"] in {"task_created", "task_revised", "claim", "delegate", "task_returned", "work_message",
                              "dependency_declared", "dependency_removed", "patch_fixed", "handoff", "integrate", "submit"}:
            action = archive.world_action(event)
            organization.append({**_world_ref(event, action),
                "facts": {k: copy.deepcopy(v) for k, v in event.items() if k not in {
                    "operation_id", "action_id", "sequence", "kind", "actor_id", "logical_time"}},
                "real_response_presentations": archive.visible(action),
                "on_delivered_version_ancestry": any(a["world_sequence"] == event["sequence"] for a in chain["ancestors"])})
    test_information = []
    for event in archive.world:
        if event["kind"] != "test":
            continue
        action = archive.world_action(event)
        shown = archive.visible(action)
        test_information.append({"world_test": _world_ref(event, action),
            "backend_full_result_sha256": _sha(event), "public_return_sha256": _sha(action["payload"]["response"]),
            "source_reference": event["source_reference"], "executed": event.get("executed"),
            "backend_passed": event.get("passed"), "actual_public_feedback_presentations": shown,
            "backend_full_test_trace_not_promoted_to_actor_input": True,
            "scope": "Only each exact selected public tool response is shown evidence. Full backend values/API traces are not inferred visible from execution or a passed flag."})
    result = {"version": VERSION, "rollout_id": rollout["rollout_id"], "rollout_sha256": _sha(rollout),
              "manifest_sha256": rollout["manifest_sha256"],
              "window": window, "case_binding": {key: copy.deepcopy(archive.case.get(key)) for key in [
                  "case_id", "purpose", "usage", "first_member", "active_roles", "scheduling_protocol", "team_limits", "editable_paths"]},
              "source_contract_sha256": _sha(archive.case["source_contract"]),
              "source_purpose_allows_support": optimizer_scope_allows_update(rollout),
              "original_complete_validity": rollout["work_validity"]["value"],
              "original_assessment": {k: assessment.get(k) for k in ["R", "status", "submitted", "content_correct",
                                         "required_process_satisfied", "process_observation_complete"]},
              "actual_visibility_complete": not archive.issues, "visibility_issues": archive.issues,
              "actual_calls": archive.calls, "members": members,
              "organization_and_fixed_products": organization, "delivery_chain": chain,
              "test_information_boundary": test_information,
              "immutable_version_proofs": list(archive.bundle_proofs.values()),
              "archive_refs": {"manifest": _file(archive.episode / "manifest.json"),
                               "original_start_state": _file(archive.episode / "start/control/state.json"),
                               "original_end_state": _file(archive.episode / "end/control/state.json"),
                               "experience": _file(archive.episode / archive.manifest["experience"]["path"])},
              "model_calls": 0, "gpu_used": False, "new_test_or_acceptance_executions": 0,
              "scope": "Read-only route/visibility evidence. Not an information-understanding, unique-author, causal-value or training-admission claim. Development material remains development."}
    result["evidence_sha256"] = _sha(result)
    return result
