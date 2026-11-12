"""v042 keeps the v041 selected-input rules and measures protected capacity.

The new world presents exact report pages. This module neither changes page
content nor adds fields to the static deduplication allowlist. P_protected is a
separate native encoding after all removable old complete tool rounds are gone;
it is not an information-theoretic minimum or a different actual input policy.
"""
import copy

from . import software_context_v041 as previous
from .software_context_v028 import BUDGET_PREPARATION_VERSION, CAPACITY_ERROR, SoftwareContextTransport as PriorTransport
from .storage import atomic_write, digest, json_bytes

VERSION = "software-context-v0.42"
PROTECTED_MARGIN_TOKENS = 1024
STATIC_FIELDS = previous.STATIC_FIELDS
deduplicate_static_snapshots = previous.deduplicate_static_snapshots


def protected_software_request(request):
    """Return the exact protected request and its original-message indices."""
    deduplicated, deduplication = deduplicate_static_snapshots(request)
    messages = deduplicated["messages"]
    pairs, claimed = [], set()
    for index, message in enumerate(messages):
        calls = message.get("tool_calls") or []
        if message.get("role") != "assistant" or not calls:
            continue
        if len(calls) != 1 or index + 1 >= len(messages):
            raise ValueError("Expected one complete managed tool round")
        following = messages[index + 1]
        if following.get("role") != "tool" or following.get("tool_call_id") != calls[0]["id"]:
            raise ValueError("Tool result must match its actual assistant call")
        pairs.append((index, index + 1))
        claimed.add(index + 1)
    if any(message.get("role") == "tool" and index not in claimed for index, message in enumerate(messages)):
        raise ValueError("Cannot project an orphan tool result")
    removed = {index for pair in pairs[:-1] for index in pair}
    indices = [index for index in range(len(messages)) if index not in removed]
    protected = copy.deepcopy(deduplicated)
    protected["messages"] = [copy.deepcopy(messages[index]) for index in indices]
    return protected, {"version": VERSION, "deduplication": deduplication, "selected_indices": indices,
        "removed_indices": sorted(removed), "complete_tool_rounds": [list(pair) for pair in pairs],
        "latest_complete_round_preserved": list(pairs[-1]) if pairs else None,
        "request_sha256": digest(json_bytes(protected)),
        "scope": "Same v041 static deduplication, then remove every permitted older complete tool round. All system/user and latest complete assistant/tool feedback remain."}


def project_software_request(request, *, render, tokenizer, context_limit):
    selected, inherited = previous.project_software_request(request, render=render, tokenizer=tokenizer,
                                                           context_limit=context_limit)
    protected, evidence = protected_software_request(request)
    rendered, _, _ = render(protected)
    ids = tokenizer(rendered, add_special_tokens=False)["input_ids"]
    headroom = context_limit - request["max_tokens"] - len(ids)
    return selected, {**inherited, "version": VERSION, "inherited_context_version": previous.VERSION,
        "protected_projection": evidence, "protected_prompt_tokens": len(ids),
        "protected_request_sha256": digest(json_bytes(protected)), "protected_input_ids_sha256": digest(json_bytes(ids)),
        "protected_rendered_prompt_sha256": digest(rendered.encode()),
        "protected_selected_indices": evidence["selected_indices"], "protected_headroom_tokens": headroom,
        "protected_margin_tokens": PROTECTED_MARGIN_TOKENS,
        "protected_headroom_after_margin": headroom - PROTECTED_MARGIN_TOKENS,
        "scope": "Actual selected rules are unchanged v041. P_protected separately encodes the complete request with all removable old tool rounds removed; 1024-token engineering margin is a CPU qualification criterion, not extra context or output allowance."}


class SoftwareContextTransport(PriorTransport):
    """Same resident sampling/accounting, with both exact context measurements."""

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
