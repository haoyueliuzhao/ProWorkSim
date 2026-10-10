"""v044 Gamma: explicit ordinary feedback lifecycle before unchanged v042 context.

Nested context-stage indices refer to the feedback-projected request. Top-level
selected/removed indices map to the transport's unchanged original request.
"""
from __future__ import annotations

import copy

from . import software_context_v042 as previous
from .software_context_v028 import BUDGET_PREPARATION_VERSION, CAPACITY_ERROR, SoftwareContextTransport as PriorTransport
from .software_feedback_v044 import OrdinaryFeedbackLedger, project_format_feedback
from .storage import atomic_write, digest, json_bytes

VERSION = "software-context-v0.44"
PROTECTED_MARGIN_TOKENS = previous.PROTECTED_MARGIN_TOKENS
STATIC_FIELDS = previous.STATIC_FIELDS
deduplicate_static_snapshots = previous.deduplicate_static_snapshots


def protected_software_request(request, *, ledger=None, member_id=None):
    formatted, feedback = project_format_feedback(request, ledger=ledger, member_id=member_id)
    protected, inherited = previous.protected_software_request(formatted)
    indices = [feedback["selected_indices"][i] for i in inherited["selected_indices"]]
    return protected, {"version": VERSION, "format_feedback_projection": feedback,
        "context_stage_projection": inherited, "selected_indices": indices,
        "removed_indices": [i for i in range(len(request["messages"])) if i not in indices],
        "request_sha256": digest(json_bytes(protected)),
        "index_scope": "Top-level indices: original transport request. Nested context_stage_projection: feedback-projected request.",
        "scope": "Registered ordinary feedback Gamma then unchanged v042 protected/static rules. Latest tool/page and unresolved feedback retained."}


def project_software_request(request, *, render, tokenizer, context_limit, ledger=None, member_id=None):
    formatted, feedback = project_format_feedback(request, ledger=ledger, member_id=member_id)
    selected, inherited = previous.project_software_request(formatted, render=render,
        tokenizer=tokenizer, context_limit=context_limit)
    mapping = feedback["selected_indices"]
    indices = [mapping[i] for i in inherited["selected_indices"]]
    protected_indices = [mapping[i] for i in inherited["protected_selected_indices"]]
    original_rendered, _, _ = render(request)
    return selected, {**inherited, "version": VERSION, "inherited_context_version": previous.VERSION,
        "format_feedback_projection": feedback, "context_stage_projection": inherited,
        "original_request_sha256": digest(json_bytes(request)),
        "original_prompt_tokens": len(tokenizer(original_rendered, add_special_tokens=False)["input_ids"]),
        "format_projected_prompt_tokens_before_context": inherited["original_prompt_tokens"],
        "selected_indices": indices,
        "removed_indices": [i for i in range(len(request["messages"])) if i not in indices],
        "protected_selected_indices": protected_indices,
        "retained_messages_unchanged": all(message == request["messages"][i] for message, i in zip(selected["messages"], indices)),
        "protected_projection": {"version": VERSION, "format_feedback_projection": feedback,
            "context_stage_projection": inherited["protected_projection"],
            "selected_indices": protected_indices,
            "removed_indices": [i for i in range(len(request["messages"])) if i not in protected_indices],
            "request_sha256": inherited["protected_request_sha256"]},
        "index_scope": "Top-level selected/removed/protected indices: original transport request. deduplication, measurements and nested context_stage_projection: feedback-projected request.",
        "scope": "New v044 feedback Gamma; unchanged v042 static, complete-round, paging, schema, initial information and budgets. 1024 margin remains diagnostic only."}


class SoftwareContextTransport(PriorTransport):
    def __init__(self, owner, directory, *, evidence_kind="actual_generation_settled"):
        super().__init__(owner, directory)
        self.feedback_ledger = OrdinaryFeedbackLedger(evidence_kind=evidence_kind)
        self._turn = None
        self._generation_bindings = {}

    def bind_turn(self, member_id, association):
        if self._turn is not None or association.get("worker_id") != member_id:
            raise ValueError("Feedback context transport needs one member-scoped runner turn")
        self._turn = {"member_id": member_id, "association": copy.deepcopy(association)}

    def unbind_turn(self, member_id, association):
        if self._turn != {"member_id": member_id, "association": association}:
            raise ValueError("Feedback context runner scope changed inside one generation")
        self._turn = None

    def _project(self, request):
        if self._turn is None:
            raise ValueError("v044 actual context preparation requires its bound runner turn")
        return project_software_request(request, render=self.owner.prepare_request,
            tokenizer=self.owner.tokenizer, context_limit=self.owner.recipe["max_length"],
            ledger=self.feedback_ledger, member_id=self._turn["member_id"])

    def prepare_for_budget(self, request):
        if self._prepared is not None:
            raise ValueError("A resident request already awaits budget admission or discard")
        selected, projection = self._project(request)
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
                          "projection": projection, "measurement": copy.deepcopy(prepared),
                          "runner_turn": copy.deepcopy(self._turn)}
        return copy.deepcopy(prepared)

    def complete(self, request, **kwargs):
        pending = self._consume_prepared(request)
        if self._turn is None or (pending is not None and pending["runner_turn"] != self._turn):
            raise ValueError("Actual generation does not match its prepared member/call scope")
        self.counter += 1
        folder = self.directory / f"request-{self.counter:05d}"
        folder.mkdir(parents=True, exist_ok=False)
        atomic_write(folder / "original-request.json", json_bytes(request))
        if pending is None:
            selected, projection = self._project(request)
        else:
            selected, projection = pending["selected"], pending["projection"]
            atomic_write(folder / "budget-preparation.json", json_bytes(pending["measurement"]))
        atomic_write(folder / "selected-request.json", json_bytes(selected))
        atomic_write(folder / "projection.json", json_bytes(projection))
        atomic_write(folder / "feedback-lifecycle-before.json", json_bytes(self.feedback_ledger.snapshot()))
        atomic_write(folder / "runner-turn.json", json_bytes(self._turn))
        if not projection["fits"]:
            body = {"error": {"code": CAPACITY_ERROR,
                "message": "Current protected request exceeds the declared context capacity",
                "prompt_tokens": projection["selected_prompt_tokens"], "requested_output": projection["reserved_output_tokens"],
                "context_limit": projection["context_limit"]}, "generation_started": False,
                "transport_kind": VERSION, "context_projection": projection}
            response = {"http_status": 400, "body": body, "raw_body": json_bytes(body).decode(),
                        "response_headers": {"x-transport": VERSION}, "response_redactions": []}
        else:
            response = self.owner.transport.complete(selected, **kwargs)
        atomic_write(folder / "response.json", json_bytes(response))
        if response.get("http_status") == 200:
            body = response.get("body", {})
            if (digest(json_bytes(body.get("token_trace", {}).get("input_ids"))) != projection["input_ids_sha256"]
                    or (pending is not None and body.get("actor_identity") != pending["measurement"]["actor_identity"])):
                raise ValueError("Actual resident generation did not use its admitted tokenized prompt and actor")
            def ref(name):
                path = folder / name
                data = path.read_bytes()
                return {"path": str(path.resolve()), "sha256": digest(data), "bytes": len(data)}
            self._generation_bindings[self._turn["association"]["call_id"]] = {
                "selected_request": copy.deepcopy(selected),
                "selected_input_ids_sha256": projection["input_ids_sha256"],
                "selected_request_ref": ref("selected-request.json"), "response_ref": ref("response.json"),
                "response_body_sha256": digest(json_bytes(body))}
        return response

    def generation_binding(self, call_id, response):
        binding = self._generation_bindings.pop(call_id, None)
        if binding is None or binding.pop("response_body_sha256") != digest(json_bytes(response["body"])):
            raise ValueError("Settled generation lacks its original selected/response binding")
        return binding
