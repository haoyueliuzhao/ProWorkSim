"""A reply to NEED is correspondence; allow one subsequent independent verification."""

from .software_handoff_disposition_v232_5 import DecisionWorld, DispositionExecution

VERIFICATION_TOOLS = {
    "read_file",
    "search_file",
    "search_repository",
    "run_tests",
    "run_patch_review_tests",
}


class ReplyAwareWorld(DecisionWorld):
    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        tid = getattr(self, "decision_task", None)
        duty = (self.protocol().get("graph_control") or {}).get("duties", {}).get(tid)
        pending = bool(
            duty
            and duty["owner"] == actor
            and duty["status"] == "pending"
            and duty.get("awaiting_evidence")
        )
        if (
            pending
            and duty.get("need_reply_read")
            and tool not in VERIFICATION_TOOLS
            and tool != "send_message"
        ):
            self.org_reject(
                "The addressed reply has been read. Verify via one own source read, search or public test, or report a blocker.",
                "independent_check_due",
            )
        result = super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)
        if (
            pending
            and tool == "read_work_event"
            and not duty.get("need_reply_read")
            and result.get("kind") == "work_message"
            and result.get("actor_id") == duty["recipient"]
            and result.get("recipient") == actor
            and result.get("task_id") == tid
            and result.get("sequence", 0) > duty["evidence_request"]["sequence"]
        ):
            duty["need_reply_read"] = result["sequence"]
            duty["awaiting_evidence"] = True
            return {
                **result,
                "diagnosis_followup": "This message belongs to the sender. You may still perform one independent file read, search or public test. Cite your own new event in DIAG, or report a concrete BLOCK.",
            }
        return result


class EvidenceFollowupExecution(DispositionExecution):
    def attach(self, runtime):
        super().attach(runtime)
        runtime.prepared.world.__class__ = ReplyAwareWorld
