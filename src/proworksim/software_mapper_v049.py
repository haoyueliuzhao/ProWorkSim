"""Frozen whole-file delivery routes over actual v049 native work evidence.

This is a finite observed product relation, not a causal or learning-value label.
Old symbol trackers are never called or rewritten. An unsupported relationship
is unmapped and does not remove its trustworthy original base-training targets.
"""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

from .software_context_v048 import VERSION as PRESENTATION
from .software_method_evidence_v035 import _Evidence as Archive, _ref, _sha, _file, _json_content
from .storage import digest, read_json
from .team_rollout import optimizer_scope_allows_update

MAPPER = "software-work-delivery-mapper-v0.49"
CLASS_ORDER = ("local_lineage_delivery", "evidenced_peer_product_delivery")


def mapping_spec():
    return {"version": MAPPER, "spec_id": MAPPER, "class_order": list(CLASS_ORDER),
        "unit": "Exact complete production files and complete candidate tree; helper functions included, no public-symbol authorship filter.",
        "input": "Original native Gamma1 request and own output tokens. Same-input references remain native; their retained first observation also provides actual patch metadata.",
        "validity": "Original record/permission/basis/complete-delivery conjunction. False or unknown validity is unmapped; trustworthy R0 remains base material.",
        "peer": "Native nonidentity partner candidate_adopted on final ancestry, original fixed publication, actual metadata and adoption receipt before recipient exact-tree test, actual test feedback before final fixed submission. The whole adopted tree remains equal through descendants and final delivery.",
        "local": "Complete trusted same-version tested and fixed delivery, retained own production AST change, and no unexplained partner fixed-source acquisition or included patch.",
        "unmapped": "Unsupported integration, ancestry, dynamic production, unexplained acquired source, unseen tested receipt, incomplete original-input binding or absent own targets never create a supported category.",
        "responsibilities": "Archive real tasks/claim/delegation/dependency/message events without requiring any count or preassigned role.",
        "member_projection": "Same evidenced joint route projects to both original member trajectories with real targets. Original masks and denominators remain; no authorship or success filtering for base training.",
        "scope": "Observed exact product route only; not unique authorship, necessity, semantic understanding, causal credit or Contribution."}


def _production(files, paths):
    values = {}
    for path in paths:
        if path == "test_member.py" or not path.endswith(".py"):
            continue
        text = files.get(path)
        if not isinstance(text, str) or any(line.startswith(("<<<<<<<", "=======", ">>>>>>>")) for line in text.splitlines()):
            return None
        try:
            tree = ast.parse(text)
        except (ValueError, SyntaxError):
            return None
        if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id in {"eval", "exec", "globals", "locals", "__import__"} for node in ast.walk(tree)):
            return None
        values[path] = ast.dump(tree, include_attributes=False)
    return values or None


class Evidence(Archive):
    """Reuse immutable-version/commit validation, replace only the old input reader."""
    def _actual_inputs(self):
        folders = {}
        for folder in sorted((self.folder / "raw-transport").glob("request-*")):
            response_path = folder / "response.json"
            if not response_path.is_file():
                continue
            response = read_json(response_path)
            if response.get("http_status") != 200:
                continue
            identity = response["body"]["id"]
            if identity in folders:
                raise ValueError("Duplicate actual native response identity")
            folders[identity] = folder
        for member, view in self.views.items():
            for decision in view["decisions"]:
                actual = decision.get("actual_response")
                if not actual or not decision.get("tokens"):
                    continue
                folder = folders.get(actual["id"])
                if folder is None:
                    self.issues.append("Missing original selected input: " + decision["call_id"])
                    continue
                original, selected, projection, turn, response = [read_json(folder / name) for name in
                    ("original-request.json", "selected-request.json", "projection.json", "runner-turn.json", "response.json")]
                call_id = decision["call_id"]
                starts = [e for e in self.events if e["kind"] == "model_attempt"
                    and e["payload"].get("stage") == "started" and e["payload"].get("call_id") == call_id]
                if len(starts) != 1:
                    raise ValueError("Actual input needs one original attempt start")
                start = starts[0]
                trace, prompt = actual["token_trace"], actual["prompt_projection"]
                if (original != decision["actual_input"] or response["body"] != actual
                        or turn["member_id"] != member or turn["association"]["call_id"] != call_id
                        or projection["version"] != PRESENTATION or not projection["fits"]
                        or projection["selected_request_sha256"] != _sha(selected)
                        or projection["input_ids_sha256"] != _sha(trace["input_ids"])
                        or projection["selected_prompt_tokens"] != len(trace["input_ids"])
                        or prompt["request_sha256"] != _sha(selected)
                        or prompt["rendered_prompt_sha256"] != projection["rendered_prompt_sha256"]
                        or actual["online_window_id"] != self.rollout["window"]["window_id"]):
                    raise ValueError("Original native Gamma1 input/member/token binding differs")
                record = {"call_id": call_id, "member_id": member, "sequence": start["sequence"],
                    "selected_request_sha256": _sha(selected), "input_ids_sha256": _sha(trace["input_ids"]),
                    "own_output_tokens": len(trace["output_ids"]), "selected_request": _file(folder / "selected-request.json")}
                self.calls.append(record)
                self.inputs.append((record, selected))
                for index, message in enumerate(selected["messages"]):
                    if message.get("role") != "tool":
                        continue
                    action = self.action_by_tool_id.get((member, message.get("tool_call_id")))
                    parsed = _json_content(message)
                    if action is None or parsed != action["payload"]["response"]:
                        continue
                    if action["sequence"] >= start["sequence"]:
                        raise ValueError("Future feedback cannot authorize an earlier action")
                    self.presentations.append({"member_id": member, "call_id": call_id,
                        "input_sequence": start["sequence"], "message_index": index, "message_sha256": _sha(message),
                        "selected_request_sha256": _sha(selected), "action_sequence": action["sequence"],
                        "action": action["payload"]["action"], "tool_call_id": message["tool_call_id"],
                        "visible_result": copy.deepcopy(parsed.get("result"))})
        self.native = {decision["call_id"]: decision["actual_response"] for view in self.views.values()
                       for decision in view["decisions"] if decision.get("actual_response")}
        verified = {call["call_id"] for call in self.calls}
        for event in self.world:
            action = self.world_action(event)
            payload = action["payload"]
            call_id = payload.get("model_call_id")
            if call_id not in verified:
                self.issues.append("World event lacks actual native input: " + str(event["sequence"]))
                continue
            body = self.native[call_id]
            choices = body.get("choices", [])
            tools = choices[0].get("message", {}).get("tool_calls", []) if len(choices) == 1 else []
            if (len(tools) != 1 or tools[0]["id"] != payload["model_tool_call_id"]
                    or tools[0]["function"]["name"] != payload["action"]
                    or json.loads(tools[0]["function"]["arguments"]) != payload["arguments"]):
                raise ValueError("Original native output differs from committed world action")

    def delivery_chain(self):
        empty = {"verified": False, "peer_applications": [], "issues": [], "category": None}
        delivery = (self.facts["deliveries"] or [None])[-1]
        if delivery is None:
            return {**empty, "reason": "no_fixed_delivery"}
        if delivery != self.assessment.get("delivery"):
            raise ValueError("Mapper assessment does not bind latest fixed delivery")
        final = self.bundle(delivery["source_reference"])
        if _sha(final) != delivery["source_sha256"] or _sha(final["files"]) != delivery["files_sha256"]:
            raise ValueError("Fixed delivery files differ")
        submissions = [e for e in self.world if e["kind"] == "submit" and e["delivery_id"] == delivery["delivery_id"]]
        if len(submissions) != 1:
            raise ValueError("Fixed delivery lacks unique original submission")
        submit, actor = submissions[0], delivery["actor_id"]
        submit_action = self.world_action(submit)
        by_reference = {}
        for event in self.world:
            if event["kind"] in {"edit", "integrate", "candidate_adopted"}:
                key = _ref(event["source_reference"])
                if key in by_reference:
                    raise ValueError("Duplicate immutable production version")
                by_reference[key] = event
        current, backward, visited = _ref(delivery["source_reference"]), [], set()
        while current in by_reference:
            if current in visited:
                raise ValueError("Production ancestry cycle")
            visited.add(current)
            event = by_reference[current]
            if event["actor_id"] != actor or event["sequence"] >= submit["sequence"]:
                return {**empty, "reason": "unsupported_member_or_time_ancestry"}
            backward.append(event)
            current = _ref(event["previous_reference"])
        if (not current or current[0] not in self.start["artifacts"]
                or current[1] not in self.start["artifacts"][current[0]]["versions"]
                or self.start["artifacts"][current[0]]["owner"] != actor):
            return {**empty, "reason": "ancestry_not_original_member_copy"}
        ancestry = list(reversed(backward))
        initial = self.bundle({"object_id": current[0], "version_id": current[1]})
        production, initial_production = (_production(b["files"], self.case["editable_paths"]) for b in (final, initial))
        if not production or initial_production is None:
            return {**empty, "reason": "unsupported_production_or_dependency"}
        tests = [e for e in self.world if e["kind"] == "test" and e["actor_id"] == actor
            and e["sequence"] == delivery["test_sequence"] and e["source_reference"] == delivery["source_reference"]
            and e.get("executed") is True and e["sequence"] < submit["sequence"]]
        fixed = [e for e in self.world if e["kind"] == "patch_fixed" and e["actor_id"] == actor
            and e["source_reference"] == delivery["source_reference"] and e["sequence"] < submit["sequence"]]
        if len(tests) != 1 or not fixed:
            return {**empty, "reason": "missing_original_current_version_test_or_fix"}
        test, = tests
        test_action = self.world_action(test)
        if not self.visible(test_action, before=submit_action["sequence"]):
            return {**empty, "reason": "tested_receipt_not_actually_seen_before_submit"}
        own_paths, peers, issues = [], [], []
        for index, event in enumerate(ancestry):
            prior, after = self.bundle(event["previous_reference"]), self.bundle(event["source_reference"])
            if event["kind"] == "edit":
                action = self.world_action(event)["payload"]
                args, path = action["arguments"], event["path"]
                expected = args["text"] if action["action"] == "write_file" else prior["files"][path].replace(args["old"], args["new"], 1)
                if (after["files"][path] != expected or digest(prior["files"][path].encode()) != event["before_sha256"]
                        or digest(after["files"][path].encode()) != event["after_sha256"]):
                    raise ValueError("Original native edit does not explain immutable bytes")
                if path in production and production[path] != initial_production[path] and after["files"][path] == final["files"][path]:
                    own_paths.append(path)
                continue
            patch = self.facts["patches"].get(event.get("patch_id"))
            if patch is None:
                raise ValueError("Production refers to missing fixed patch")
            if event["kind"] != "candidate_adopted":
                issues.append("unsupported_three_way_integration")
                continue
            incoming = self.bundle(patch["source_reference"])
            if (event["input_reference"] != patch["source_reference"] or incoming["files"] != after["files"]
                    or _sha(incoming["files"]) != patch["files_sha256"] or _sha(after["files"]) != event["files_sha256"]
                    or event.get("exact_files_match") is not True or event.get("native_model_action") is not True):
                raise ValueError("Candidate adoption not exact original fixed source")
            if patch["author"] == actor:
                continue
            publications = [e for e in self.world if e["kind"] == "patch_fixed" and e["patch_id"] == patch["patch_id"]
                and e["actor_id"] == patch["author"] and e["source_reference"] == patch["source_reference"]
                and e["sequence"] < event["sequence"]]
            changed = [p for p in production if prior["files"][p] != incoming["files"][p]]
            retained = all(self.bundle(e["source_reference"])["files"] == incoming["files"] for e in ancestry[index:])
            receipt = self.visible(self.world_action(event), before=test_action["sequence"])
            metadata = self.metadata_seen(actor, patch, self.world_action(event)["sequence"])
            qualified = bool(len(publications) == 1 and changed and retained and incoming["files"] == final["files"]
                and receipt and metadata and event["sequence"] < test["sequence"])
            peers.append({"patch_id": patch["patch_id"], "source_member": patch["author"], "recipient": actor,
                "world_sequence": event["sequence"], "files_sha256": patch["files_sha256"],
                "source_reference": patch["source_reference"], "nonidentity_production_paths": changed,
                "complete_tree_retained_to_final": retained, "metadata_presentations": metadata,
                "receipt_presentations": receipt, "qualified": qualified})
            if not qualified:
                issues.append("unexplained_peer_application:" + patch["patch_id"])
        peer_ids = {p["patch_id"] for p in peers}
        acquisitions = []
        for event in self.world:
            if event["kind"] not in {"read", "search"} or event["actor_id"] != actor or event["sequence"] >= submit["sequence"]:
                continue
            for patch in self.facts["patches"].values():
                if patch["author"] != actor and event.get("source_reference") == patch["source_reference"] and self.visible(self.world_action(event), before=submit_action["sequence"]):
                    acquisitions.append(patch["patch_id"])
        for pid in set(final["included_patch_ids"]) | set(acquisitions):
            patch = self.facts["patches"].get(pid)
            if patch is None or patch["author"] != actor and pid not in peer_ids:
                issues.append("unexplained_peer_acquisition_or_inclusion:" + pid)
        category = (CLASS_ORDER[1] if peers and all(p["qualified"] for p in peers)
                    else CLASS_ORDER[0] if not peers and own_paths else None)
        if issues or self.issues:
            category = None
        return {"verified": not issues and not self.issues, "category": category,
            "delivery": delivery, "ancestry_sequences": [e["sequence"] for e in ancestry],
            "current_test_sequence": test["sequence"], "current_test_feedback_seen_before_submit": True,
            "peer_applications": peers, "own_production_paths": sorted(set(own_paths)),
            "peer_fixed_acquisitions": acquisitions, "issues": issues}


def _validate_export_evidence(rollout, evidence):
    """Consume the original exporter seal and exact controller-file references."""
    if (evidence.get("version") != "software-training-export-v0.49"
            or evidence.get("evidence_sha256") != _sha({k: v for k, v in evidence.items() if k != "evidence_sha256"})):
        raise ValueError("Original v049 export evidence seal differs")
    episode = Path(evidence["episode_path"]).resolve()
    folder = episode.parent
    expected = {"manifest": episode / "manifest.json", "start_state": episode / "start/control/state.json",
        "end_state": episode / "end/control/state.json", "assessment": folder / "assessment.json",
        "runtime_result": folder / "slot-result.json"}
    references = evidence.get("source_references", {})
    if (Path(rollout.get("episode_path", "")).resolve() != episode
            or Path(evidence.get("slot_root", "")).resolve() != folder or set(references) != set(expected)):
        raise ValueError("Export evidence must bind this exact episode and complete source reference set")
    for name, path in expected.items():
        ref = references[name]
        if (Path(ref.get("path", "")).resolve() != path or not path.is_file()
                or ref.get("sha256") != digest(path.read_bytes())):
            raise ValueError("Original export source reference changed: " + name)
    assessment = read_json(expected["assessment"])
    if (evidence.get("manifest_sha256") != rollout.get("manifest_sha256")
            or evidence.get("assessment_sha256") != _sha(assessment) or evidence.get("assessment") != assessment
            or evidence.get("assessment_status") != assessment.get("status")
            or evidence.get("case") != rollout["manifest"]["scenario"]["variation"]["software_case"]
            or evidence.get("runtime_binding") != rollout["manifest"]["scenario"]["variation"]["organization_runtime"]):
        raise ValueError("Export payload differs from the original source, runtime or assessment")
    return folder, assessment


def map_software_method(rollout, evidence, *, spec=None):
    frozen = mapping_spec()
    if spec is not None and spec != frozen:
        raise ValueError("Mapper differs from its precollection specification")
    folder, assessment = _validate_export_evidence(rollout, evidence)
    data = Evidence(folder, rollout, assessment)
    initial_projects = [p["software"] for p in data.start["projects"].values() if "software" in p]
    if (len(initial_projects) != 1 or evidence.get("original_events") != data.world
            or evidence.get("initial_tasks") != initial_projects[0]["tasks"]
            or evidence.get("final_tasks") != data.facts["tasks"]
            or evidence.get("patches") != data.facts["patches"]
            or evidence.get("delivery") != (data.facts["deliveries"] or [None])[-1]):
        raise ValueError("Export responsibility/product facts differ from original committed world events")
    chain = data.delivery_chain()
    category = chain.get("category") if rollout["work_validity"]["value"] is True and not data.issues else None
    allowed = optimizer_scope_allows_update(rollout) and rollout["online_scope"].get("method_mapper_spec_sha256") == _sha(frozen)
    projections = {}
    for member, view in data.views.items():
        tokens = sum(len(d["tokens"]["output_ids"]) for d in view["decisions"] if d.get("tokens") and d.get("actor_trainable"))
        complete = view.get("complete_actor_trajectory") is True
        projections[member] = {"member_id": member, "class_id": category,
            "support_eligible": bool(category and allowed and complete and tokens),
            "own_action_count": sum(d.get("actor_trainable") is True for d in view["decisions"]),
            "own_action_tokens": tokens, "complete_actor_trajectory": complete,
            "actual_input_bindings_complete": not data.issues, "base_actor_targets_unchanged": True}
    details = {"rollout_id": rollout["rollout_id"], "rollout_sha256": _sha(rollout), "mapper_spec_sha256": _sha(frozen),
        "delivery_chain": chain, "input_issues": data.issues, "actual_inputs": data.calls,
        "immutable_versions": list(data.bundle_proofs.values()),
        "task_and_responsibility_events": [copy.deepcopy(e) for e in data.world if e["kind"] in
            {"task_created", "task_revised", "claim", "delegate", "task_returned", "dependency_declared", "dependency_removed", "work_message"}]}
    return {"version": MAPPER, "spec_id": MAPPER, "rollout_id": rollout["rollout_id"],
        "status": "mapped" if category else "unmapped", "class_id": category,
        "composition_support_eligible": bool(category and allowed), "member_projections": projections,
        "mapper_spec_sha256": _sha(frozen), "evidence_sha256": _sha(details), "evidence": details,
        "reason": "Observed exact joint delivery route" if category else "Unproven or invalid route; original trustworthy base material retained",
        "causal_or_learning_value_claimed": False}
