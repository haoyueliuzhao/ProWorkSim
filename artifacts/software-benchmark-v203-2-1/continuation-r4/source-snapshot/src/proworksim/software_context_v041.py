"""v041 Gamma: exact member-local static snapshot deduplication.

The latest complete static values remain in the selected input. Dynamic state,
original assistant/tool messages and true format feedback are never rewritten.
After deduplication the unchanged v028 whole-round capacity selector applies.
This is a new presentation condition, not a behavioral invariance claim.
"""
import copy
import json

from .software_context_v028 import (
    BUDGET_PREPARATION_VERSION, CAPACITY_ERROR,
    SoftwareContextTransport as PriorTransport, project_software_request as capacity_project,
)
from .software_context_v034 import observation_messages
from .storage import atomic_write, digest, json_bytes

VERSION = "software-context-v0.41"
POLICY_SNAPSHOT_FIELDS = ("action_error_policy", "acceptance_contract", "scheduling", "member_limits",
    "shared_resource_limits", "isolation", "observation_projection", "initial_diagnostic_provenance", "editable_paths")
STATIC_FIELDS = ("role_task", "observation.initial_diagnostics", "observation.contract", "observation.root_goal.description",
                 *("observation." + field for field in POLICY_SNAPSHOT_FIELDS))
MEMBER_SCOPE_FIELDS = ("world_id", "instance_id", "branch_id", "project_id", "actor_id", "interface_revision")


def _member_identity(observation):
    """Absent/ambiguous provenance is kept, never guessed from equal text."""
    if any(not isinstance(observation.get(key), str) or not observation[key] for key in MEMBER_SCOPE_FIELDS):
        return None
    return {key: observation[key] for key in MEMBER_SCOPE_FIELDS}


def _root_identity(observation):
    goal = observation.get("root_goal")
    contract = observation.get("contract")
    if (not isinstance(goal, dict) or not isinstance(goal.get("task_id"), str) or not goal["task_id"]
            or not isinstance(contract, str) or not contract):
        return None
    return {"root_goal_id": goal["task_id"], "contract_sha256": digest(contract.encode())}


def _diagnostic_identity(value):
    if not isinstance(value, list) or not value:
        return None
    identities = []
    for report in value:
        if not isinstance(report, dict):
            return None
        reference = report.get("initial_source_reference")
        if (report.get("initial_report") is not True or report.get("origin") != "environment_initial_diagnostic"
                or not isinstance(report.get("diagnostic_id"), str) or not report["diagnostic_id"]
                or not isinstance(report.get("files_sha256"), str) or not report["files_sha256"]
                or not isinstance(reference, dict) or set(reference) != {"object_id", "version_id"}
                or any(not isinstance(reference[key], str) or not reference[key] for key in reference)
                or report.get("source_reference") != reference):
            return None
        identities.append({"diagnostic_id": report["diagnostic_id"], "origin": report["origin"],
            "initial_source_reference": copy.deepcopy(reference), "files_sha256": report["files_sha256"]})
    return identities


def _exact(left, right):
    # JSON bytes are intentionally stricter than Python equality (True != 1,
    # and differently ordered object encodings are conservatively retained).
    return json_bytes(left) == json_bytes(right)


def deduplicate_static_snapshots(request):
    """Remove only declared fields with a complete equal witness still retained."""
    selected = copy.deepcopy(request)
    observations = list(observation_messages(selected))
    latest_by_member = {}
    for index, payload in observations:
        identity = _member_identity(payload["observation"])
        if identity is not None:
            latest_by_member[json_bytes(identity)] = (index, copy.deepcopy(payload))
    removed = []

    def remove(index, field, value, kept_index, kept_field, member, evidence, reason):
        removed.append({"path": f"/messages/{index}/content/{field}",
            "retained_equal_path": f"/messages/{kept_index}/content/{kept_field}",
            "value_sha256": digest(json_bytes(value)),
            "characters": len(value) if isinstance(value, str) else len(json.dumps(value, ensure_ascii=False, allow_nan=False)),
            "member_identity": copy.deepcopy(member), "evidence_identity": copy.deepcopy(evidence), "reason": reason})

    for index, payload in observations:
        observation = payload["observation"]
        member = _member_identity(observation)
        latest = latest_by_member.get(json_bytes(member)) if member is not None else None
        root = _root_identity(observation)
        canonical_root = _root_identity(latest[1]["observation"]) if latest else None
        same_root = root is not None and _exact(root, canonical_root)
        changed = False
        contract, goal = observation.get("contract"), observation.get("root_goal")
        # Original within-observation contract alias removal remains exact; it
        # never crosses a member boundary even when provenance is incomplete.
        if isinstance(contract, str) and contract and isinstance(goal, dict) and goal.get("description") == contract:
            kept = latest[0] if same_root else index
            remove(index, "observation/root_goal/description", contract, kept, "observation/contract",
                   member, root, "Root description equals this member's complete retained contract exactly")
            del goal["description"]
            changed = True
        if latest and index != latest[0]:
            current = latest[1]
            diagnostics = observation.get("initial_diagnostics")
            identity = _diagnostic_identity(diagnostics)
            current_diagnostics = current["observation"].get("initial_diagnostics")
            same_diagnostics = identity is not None and _exact(identity, _diagnostic_identity(current_diagnostics))
            if same_root:
                for field in POLICY_SNAPSHOT_FIELDS:
                    if field not in observation or field not in current["observation"]:
                        continue
                    if field == "initial_diagnostic_provenance" and not same_diagnostics:
                        continue
                    value = observation[field]
                    if _exact(value, current["observation"][field]):
                        remove(index, "observation/" + field, value, latest[0], "observation/" + field, member,
                            {"root": root, "initial_evidence": identity if field == "initial_diagnostic_provenance" else None},
                            "Declared immutable policy snapshot for the same member/root/interface equals its latest complete value exactly")
                        del observation[field]
                        changed = True
            if same_root and _exact(contract, current["observation"].get("contract")):
                remove(index, "observation/contract", contract, latest[0], "observation/contract", member, root,
                       "Historical contract equals the latest complete contract for the same member and root")
                del observation["contract"]
                changed = True
            task = payload.get("role_task")
            if same_root and isinstance(task, str) and task and _exact(task, current.get("role_task")):
                remove(index, "role_task", task, latest[0], "role_task", member, root,
                       "Same member/root instruction snapshot equals its latest complete value exactly")
                del payload["role_task"]
                changed = True
            if same_diagnostics and _exact(diagnostics, current_diagnostics):
                remove(index, "observation/initial_diagnostics", diagnostics, latest[0], "observation/initial_diagnostics",
                       member, identity, "Same initial evidence identities/versions and exact values remain complete in the latest observation")
                del observation["initial_diagnostics"]
                changed = True
        if changed:
            selected["messages"][index]["content"] = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return selected, {"version": VERSION, "declared_static_fields": list(STATIC_FIELDS), "removed_values": removed,
        "latest_observation_indices": [value[0] for value in latest_by_member.values()],
        "complete_tools_unchanged": selected.get("tools") == request.get("tools"),
        "non_user_messages_unchanged": all(out == before for out, before in zip(selected["messages"], request["messages"])
                                           if before.get("role") != "user"),
        "original_request_sha256": digest(json_bytes(request)),
        "deduplicated_request_sha256": digest(json_bytes(selected)),
        "scope": "Same member, same semantic static field, same evidence identity/version and exact JSON value only. No hidden facts, summaries, tool-result edits or cross-member memory."}


def project_software_request(request, *, render, tokenizer, context_limit):
    deduplicated, evidence = deduplicate_static_snapshots(request)
    selected, capacity = capacity_project(deduplicated, render=render, tokenizer=tokenizer, context_limit=context_limit)
    rendered, _, _ = render(request)
    audit = {**capacity, "version": VERSION, "deduplication": evidence, "inherited_capacity_projection": capacity,
        "original_request_sha256": digest(json_bytes(request)),
        "original_prompt_tokens": len(tokenizer(rendered, add_special_tokens=False)["input_ids"]),
        "deduplicated_prompt_tokens_before_capacity": capacity["original_prompt_tokens"],
        "retained_messages_unchanged": all(message == request["messages"][index]
            for message, index in zip(selected["messages"], capacity["selected_indices"])),
        "scope": "New Gamma v041. Latest complete static evidence/instructions, current dynamic state and newest complete visible tool round retained. Only exact declared static duplicates then inherited older complete rounds may be removed. No behavioral invariance claim."}
    return selected, audit


class SoftwareContextTransport(PriorTransport):
    """Unchanged resident seals/accounting, with the explicit new projection."""

    def prepare_for_budget(self, request):
        if self._prepared is not None:
            raise ValueError("A resident request already awaits budget admission or discard")
        selected, projection = project_software_request(request, render=self.owner.prepare_request,
            tokenizer=self.owner.tokenizer, context_limit=self.owner.recipe["max_length"])
        prepared = {"version": BUDGET_PREPARATION_VERSION,
            "original_request_sha256": projection["original_request_sha256"],
            "selected_request_sha256": projection["selected_request_sha256"],
            "rendered_prompt_sha256": projection["rendered_prompt_sha256"],
            "input_ids_sha256": projection["input_ids_sha256"], "prompt_tokens": projection["selected_prompt_tokens"],
            "reserved_output_tokens": projection["reserved_output_tokens"], "context_limit": projection["context_limit"],
            "fits": projection["fits"], "actor_identity": self.owner.freeze_identity(), "window_id": self.owner.window_id,
            "recipe_sha256": digest(json_bytes(self.owner.recipe))}
        prepared["preparation_sha256"] = digest(json_bytes(prepared))
        self._prepared = {"request": copy.deepcopy(request), "selected": selected,
                          "projection": projection, "measurement": copy.deepcopy(prepared)}
        return copy.deepcopy(prepared)

    def complete(self, request, **kwargs):
        pending = self._consume_prepared(request)
        self.counter += 1
        folder = self.directory / f"request-{self.counter:05d}"
        folder.mkdir(parents=True, exist_ok=False)
        atomic_write(folder / "original-request.json", json_bytes(request))
        if pending is None:
            selected, projection = project_software_request(request, render=self.owner.prepare_request,
                tokenizer=self.owner.tokenizer, context_limit=self.owner.recipe["max_length"])
        else:
            selected, projection = pending["selected"], pending["projection"]
            atomic_write(folder / "budget-preparation.json", json_bytes(pending["measurement"]))
        atomic_write(folder / "selected-request.json", json_bytes(selected))
        atomic_write(folder / "projection.json", json_bytes(projection))
        if not projection["fits"]:
            body = {"error": {"code": CAPACITY_ERROR,
                "message": "Current observation and newest complete tool round exceed the declared context capacity",
                "prompt_tokens": projection["selected_prompt_tokens"], "requested_output": projection["reserved_output_tokens"],
                "context_limit": projection["context_limit"]}, "generation_started": False,
                "transport_kind": VERSION, "context_projection": projection}
            response = {"http_status": 400, "body": body, "raw_body": json_bytes(body).decode(),
                        "response_headers": {"x-transport": VERSION}, "response_redactions": []}
        else:
            response = self.owner.transport.complete(selected, **kwargs)
        atomic_write(folder / "response.json", json_bytes(response))
        if pending is not None and response.get("http_status") == 200:
            body = response.get("body", {})
            if (digest(json_bytes(body.get("token_trace", {}).get("input_ids"))) != projection["input_ids_sha256"]
                    or body.get("actor_identity") != pending["measurement"]["actor_identity"]):
                raise ValueError("Actual resident generation did not use its admitted tokenized prompt and actor")
        return response
