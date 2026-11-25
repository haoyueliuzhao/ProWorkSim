"""The v240.4 OSA with shared, opportunity-bounded organization activation."""

import json
from .software_handoff_evidence_v232_6 import EvidenceFollowupExecution
from .software_graph_execution_v230 import CALL_BOUND
from . import software_commitment_prompt_v240_4 as prompt
from . import software_three_graph_v240 as contract


def envelope(kind):
    # The diagnosis harness already guarantees sender, receiver and fallback turns.
    n = {
        "new_work": 1,
        "handoff_and_disposition": 3,
        "implementation": 1,
        "verification": 1,
        "fix_and_submit": 2,
    }
    if kind == "diagnosis":
        n["handoff_and_disposition"] += 2
    return {k: v * CALL_BOUND for k, v in n.items()}


class Execution(EvidenceFollowupExecution):
    def decide(self, node, observer, frozen, arm):
        row = self.record
        available = self.runtime.team_budget.snapshot()["available_tokens"]
        if (
            frozen["graph"] != row["graph"]
            or frozen["options"] != row["options"]
            or observer != row["observer"]
            or available != row["available_tokens"]
        ):
            raise ValueError("Organization decision does not match the restored boundary")
        if arm == "KEEP":
            return super().decide(node, observer, frozen, arm)
        payload = dict(
            team_slot_id=self.trace.branch,
            request_id=self.trace.branch + ":osa",
            member_id=observer,
            usage_id="agent",
            wire=prompt.request(row),
        )
        # Send the same decision wire as the admitted prompt experiment, bypassing only the worker context formatter.
        client = self.osa.backend
        upper = client("/tokenize", payload)["prompt_tokens"] + payload["wire"]["max_tokens"]
        if upper > available:
            raise ValueError("OSA request exceeds remaining team allocation")
        body = client("/chat/completions", payload)
        usage = body["usage"]["total_tokens"]
        self.native_limit -= usage
        self.runtime.team_budget.native_allocation = self.native_limit
        keep = dict(
            option="K",
            evidence=[next(iter(frozen["evidence"]))],
            reason="Retain the incumbent graph",
        )
        info = dict(
            source="live_v240.4",
            osa_tokens=usage,
            response=body["id"],
            proposal=None,
            validator="accepted",
            first_action=None,
        )
        try:
            proposal = contract.parse(row, body)
            compiled = contract.compile_decision(row, proposal)
            ids = {v["command_id"]: k for k, v in frozen["evidence"].items()}
            commands = dict(zip(row["evidence"], row["provenance"]["commands"]))
            choice = dict(
                option=compiled["patch"]["option"],
                evidence=[ids[commands[k]] for k in proposal["basis"]],
                reason=proposal["reason"][:1200],
            )
            kind = frozen["options"][choice["option"]]["op"]
            reserve = envelope(kind) if kind != "keep" else {}
            info.update(
                proposal=proposal,
                requested=compiled["disposition"],
                graph_patch=compiled["patch"],
                expected_graph=contract.base.apply_patch(row, compiled["patch"]),
                obligations=compiled["effective"],
                resources={
                    "osa_actual": usage,
                    "remaining": available - usage,
                    "work_reserve": reserve,
                },
            )
            if sum(reserve.values()) > available - usage:
                raise ValueError(
                    "Incomplete protected work/handoff/implementation/verification/delivery envelope"
                )
        except (ValueError, KeyError, TypeError) as e:
            info.update(validator="rejected", error=str(e))
            return self.activate(node, observer, frozen, keep), info
        except Exception as e:
            from jsonschema import ValidationError

            if not isinstance(e, ValidationError):
                raise
            info.update(validator="rejected", error=e.message[:300])
            return self.activate(node, observer, frozen, keep), info
        active = self.activate(node, observer, frozen, choice)
        if active.get("activated") is False:
            info.update(validator="rejected", activation_rejection=active)
            return self.activate(node, observer, frozen, keep), info
        binding = contract.dispatch(row, compiled, active["after"])
        if active.get("changed"):
            task = frozen["options"][choice["option"]]["task"]
            work = active["after"]["work"][task]
            # Keep the native new-duty, verification, delivery and diagnosis receipt grants.
            # Reserve an implementation turn and a distinct final-fix turn as well.
            self.grants.insert(-2, ("implementation", work["owner"]))
            self.grants.insert(-1, ("fix_current_tree", self.runtime.fixed_spec["delivery_member"]))
            if kind != "diagnosis":
                self.grants[1:1] = [
                    ("publish_artifact", frozen["options"][choice["option"]]["assignee"]),
                    ("inspect_handoff", work["owner"]),
                    ("record_disposition", work["owner"]),
                ]
        self.runtime.policies[binding["actor"]].conversation.send_message(
            "Current organization plan: "
            + json.dumps(binding)
            + ". Outstanding obligations: "
            + json.dumps(compiled["effective"])
            + ". Reassess when "
            + proposal["reconsider_after"]
        )
        info.update(first_action=binding, planned_grants=list(self.grants))
        return active, info
