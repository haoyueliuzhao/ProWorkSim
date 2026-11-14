"""Measured software prompt selection; retain full raw requests on disk.

Only older complete assistant/tool rounds may be omitted. System and user
messages, the latest complete round, tool schemas and sampling settings remain
byte-for-byte unchanged. No summaries, text cropping, model retries or hidden
world reads are introduced.
"""

import copy
from pathlib import Path

from .storage import atomic_write, digest, json_bytes

VERSION = "software-context-v0.28.1"
CAPACITY_ERROR = "software_context_capacity_exhausted"
BUDGET_PREPARATION_VERSION = "resident-request-budget-v0.31r3"


def project_software_request(request, *, render, tokenizer, context_limit):
    """Select a suffix of complete rounds using the actual actor tokenizer."""
    original = copy.deepcopy(request)
    messages = original["messages"]
    maximum = original["max_tokens"]
    if type(context_limit) is not int or type(maximum) is not int or not 0 < maximum < context_limit:
        raise ValueError("Explicit positive context and output limits are required")
    pairs, claimed = [], set()
    for index, message in enumerate(messages):
        calls = message.get("tool_calls") or []
        if message.get("role") != "assistant" or not calls:
            continue
        if len(calls) != 1 or index + 1 >= len(messages):
            raise ValueError("Expected one complete managed tool round")
        following = messages[index + 1]
        if (following.get("role") != "tool"
                or following.get("tool_call_id") != calls[0]["id"]):
            raise ValueError("Tool result must match its actual assistant call")
        pairs.append((index, index + 1))
        claimed.add(index + 1)
    if any(message.get("role") == "tool" and index not in claimed
           for index, message in enumerate(messages)):
        raise ValueError("Cannot project an orphan tool result")
    removed, measurements = set(), []
    selected = copy.deepcopy(original)
    # The latest tool result is essential feedback. Never silently discard it
    # merely to obtain a model answer; an irreducible overflow is explicit.
    removable = iter(pairs[:-1])
    while True:
        selected["messages"] = [copy.deepcopy(message) for index, message in enumerate(messages)
                                if index not in removed]
        rendered, _, _ = render(selected)
        input_ids = tokenizer(rendered, add_special_tokens=False)["input_ids"]
        prompt_tokens = len(input_ids)
        measurements.append({"removed_indices": sorted(removed), "prompt_tokens": prompt_tokens})
        fits = prompt_tokens + maximum <= context_limit
        if fits:
            break
        pair = next(removable, None)
        if pair is None:
            break
        removed.update(pair)
    selected_indices = [index for index in range(len(messages)) if index not in removed]
    audit = {
        "version": VERSION, "fits": fits, "context_limit": context_limit,
        "reserved_output_tokens": maximum, "original_prompt_tokens": measurements[0]["prompt_tokens"],
        "selected_prompt_tokens": prompt_tokens, "measurements": measurements,
        "original_request_sha256": digest(json_bytes(original)),
        "selected_request_sha256": digest(json_bytes(selected)),
        "selected_indices": selected_indices, "removed_indices": sorted(removed),
        "complete_tool_rounds": [list(pair) for pair in pairs],
        "latest_complete_round_preserved": list(pairs[-1]) if pairs else None,
        "retained_messages_unchanged": all(selected["messages"][out] == messages[index]
                                            for out, index in enumerate(selected_indices)),
        "rendered_prompt_sha256": digest(rendered.encode()),
        "input_ids_sha256": digest(json_bytes(input_ids)),
        "scope": "Oldest complete tool rounds only; all system/user messages and the newest round remain exact. No text shortening, summaries, sampling changes or retries.",
    }
    return selected, audit


def validate_budget_preparation(request, prepared):
    """Check the sealed transport measurement before the accountant trusts it."""
    if not isinstance(prepared, dict):
        raise ValueError("Resident budget preparation must be an object")
    payload = {key: value for key, value in prepared.items() if key != "preparation_sha256"}
    if (prepared.get("version") != BUDGET_PREPARATION_VERSION
            or prepared.get("preparation_sha256") != digest(json_bytes(payload))
            or prepared.get("original_request_sha256") != digest(json_bytes(request))
            or prepared.get("reserved_output_tokens") != request.get("max_tokens")
            or type(prepared.get("prompt_tokens")) is not int or prepared["prompt_tokens"] <= 0
            or type(prepared.get("reserved_output_tokens")) is not int or prepared["reserved_output_tokens"] <= 0
            or type(prepared.get("context_limit")) is not int
            or prepared.get("fits") is not (prepared["prompt_tokens"] + prepared["reserved_output_tokens"] <= prepared["context_limit"])):
        raise ValueError("Resident budget preparation/request checksum or measured bounds differ")
    return prepared


class SoftwareContextTransport:
    """Preflight before the resident sampler; durable original/selected inputs."""

    def __init__(self, owner, directory):
        self.owner, self.directory = owner, Path(directory)
        self.counter = 0
        self._prepared = None

    def prepare_for_budget(self, request):
        """Measure once without sampling, writing artifacts or consuming a call."""
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

    def discard_prepared_request(self, request):
        """A rejected allowance releases its preparation for another role/turn."""
        pending, self._prepared = self._prepared, None
        if pending is not None:
            validate_budget_preparation(request, pending["measurement"])

    def _consume_prepared(self, request):
        pending, self._prepared = self._prepared, None
        if pending is None:
            return None
        measurement = validate_budget_preparation(request, pending["measurement"])
        if (pending["request"] != request
                or measurement["selected_request_sha256"] != digest(json_bytes(pending["selected"]))
                or measurement["actor_identity"] != self.owner.freeze_identity()
                or measurement["window_id"] != self.owner.window_id
                or measurement["recipe_sha256"] != digest(json_bytes(self.owner.recipe))
                or measurement["rendered_prompt_sha256"] != pending["projection"]["rendered_prompt_sha256"]
                or measurement["input_ids_sha256"] != pending["projection"]["input_ids_sha256"]):
            raise ValueError("Resident prepared request, projection, actor identity, window or recipe changed before generation")
        return pending

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
        # The resident response and its actual token trace are not rewritten.
        atomic_write(folder / "response.json", json_bytes(response))
        if pending is not None and response.get("http_status") == 200:
            body = response.get("body", {})
            if (digest(json_bytes(body.get("token_trace", {}).get("input_ids"))) != projection["input_ids_sha256"]
                    or body.get("actor_identity") != pending["measurement"]["actor_identity"]):
                raise ValueError("Actual resident generation did not use its admitted tokenized prompt and actor")
        return response
