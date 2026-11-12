"""v034 Gamma: exact duplicate contracts only, then inherited capacity selection.

This changes model presentation, hence may change behavior. It is not a summary,
planner or memory system. All allocation methods must use this same interface.
"""
import copy
import json

from .software_context_v028 import (
    BUDGET_PREPARATION_VERSION,
    CAPACITY_ERROR,
    SoftwareContextTransport as PriorTransport,
    project_software_request as capacity_project,
)
from .storage import atomic_write, digest, json_bytes

VERSION = "software-context-v0.34"


def observation_messages(request):
    """Recognize only SDK user JSON envelopes with an observation object."""
    for index, message in enumerate(request["messages"]):
        if message.get("role") != "user" or not isinstance(message.get("content"), str):
            continue
        try:
            payload = json.loads(message["content"])
        except (ValueError, TypeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("observation"), dict):
            yield index, payload


def deduplicate_contracts(request):
    """Remove exact duplicate values; preserve latest complete contract and state.

    Distinct historical contracts remain. Tool results and assistant text are
    never rewritten, including a read_file result containing the contract.
    """
    selected = copy.deepcopy(request)
    observations = list(observation_messages(selected))
    removed = []
    latest = observations[-1] if observations else None
    canonical = latest[1]["observation"].get("contract") if latest else None
    canonical_path = f"/messages/{latest[0]}/content/observation/contract" if latest else None
    for index, payload in observations:
        observation = payload["observation"]
        contract = observation.get("contract")
        goal = observation.get("root_goal")
        changed = False
        if (isinstance(contract, str) and contract and isinstance(goal, dict)
                and goal.get("description") == contract):
            removed.append({"path": f"/messages/{index}/content/observation/root_goal/description",
                            "retained_equal_path": (canonical_path if contract == canonical else
                                f"/messages/{index}/content/observation/contract"),
                            "value_sha256": digest(contract.encode()), "characters": len(contract),
                            "reason": "root description equals full observation contract exactly"})
            del goal["description"]
            changed = True
        if (latest and index != latest[0] and isinstance(contract, str) and contract
                and contract == canonical):
            removed.append({"path": f"/messages/{index}/content/observation/contract",
                            "retained_equal_path": canonical_path,
                            "value_sha256": digest(contract.encode()), "characters": len(contract),
                            "reason": "historical contract equals latest full contract exactly"})
            del observation["contract"]
            changed = True
        if changed:
            selected["messages"][index]["content"] = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    return selected, {"version": VERSION, "removed_values": removed,
                      "latest_contract_path": canonical_path,
                      "complete_tools_unchanged": selected.get("tools") == request.get("tools"),
                      "non_user_messages_unchanged": all(
                          out == before for out, before in zip(selected["messages"], request["messages"])
                          if before.get("role") != "user"),
                      "original_request_sha256": digest(json_bytes(request)),
                      "deduplicated_request_sha256": digest(json_bytes(selected))}


def project_software_request(request, *, render, tokenizer, context_limit):
    """Apply exact deduplication before the unchanged complete-round selector."""
    deduplicated, evidence = deduplicate_contracts(request)
    selected, capacity = capacity_project(deduplicated, render=render, tokenizer=tokenizer,
                                         context_limit=context_limit)
    rendered, _, _ = render(request)
    original_tokens = len(tokenizer(rendered, add_special_tokens=False)["input_ids"])
    audit = {**capacity, "version": VERSION, "deduplication": evidence,
             "inherited_capacity_projection": capacity,
             "original_request_sha256": digest(json_bytes(request)),
             "original_prompt_tokens": original_tokens,
             "deduplicated_prompt_tokens_before_capacity": capacity["original_prompt_tokens"],
             "retained_messages_unchanged": all(
                 message == request["messages"][index]
                 for message, index in zip(selected["messages"], capacity["selected_indices"])),
             "scope": "New Gamma; only exact duplicate observation contracts/root descriptions removed before inherited whole-round capacity selection. Full original request archived; complete tools, current state and latest feedback retained. No behavioral invariance claim."}
    return selected, audit


class SoftwareContextTransport(PriorTransport):
    """Same native owner, preparation seals and accounting; new projection only."""

    def prepare_for_budget(self, request):
        if self._prepared is not None:
            raise ValueError("A resident request already awaits budget admission or discard")
        selected, projection = project_software_request(
            request, render=self.owner.prepare_request, tokenizer=self.owner.tokenizer,
            context_limit=self.owner.recipe["max_length"])
        prepared = {
            "version": BUDGET_PREPARATION_VERSION,
            "original_request_sha256": projection["original_request_sha256"],
            "selected_request_sha256": projection["selected_request_sha256"],
            "rendered_prompt_sha256": projection["rendered_prompt_sha256"],
            "input_ids_sha256": projection["input_ids_sha256"],
            "prompt_tokens": projection["selected_prompt_tokens"],
            "reserved_output_tokens": projection["reserved_output_tokens"],
            "context_limit": projection["context_limit"], "fits": projection["fits"],
            "actor_identity": self.owner.freeze_identity(), "window_id": self.owner.window_id,
            "recipe_sha256": digest(json_bytes(self.owner.recipe)),
        }
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
            selected, projection = project_software_request(
                request, render=self.owner.prepare_request, tokenizer=self.owner.tokenizer,
                context_limit=self.owner.recipe["max_length"])
        else:
            selected, projection = pending["selected"], pending["projection"]
            atomic_write(folder / "budget-preparation.json", json_bytes(pending["measurement"]))
        atomic_write(folder / "selected-request.json", json_bytes(selected))
        atomic_write(folder / "projection.json", json_bytes(projection))
        if not projection["fits"]:
            body = {"error": {"code": CAPACITY_ERROR,
                              "message": "Current observation and newest complete tool round exceed the declared context capacity",
                              "prompt_tokens": projection["selected_prompt_tokens"],
                              "requested_output": projection["reserved_output_tokens"],
                              "context_limit": projection["context_limit"]},
                    "generation_started": False, "transport_kind": VERSION,
                    "context_projection": projection}
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
