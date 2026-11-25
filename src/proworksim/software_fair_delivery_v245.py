"""Task-level delivery contract for two-worker organization comparisons."""

from copy import deepcopy

from .software_graph_controller_v228 import ControlledWorld
from .software_review_handoff_v243_1 import Execution as PreviousExecution, ReviewWorld

NOTICE = (
    "Current delivery contract v245 (supersedes historical per-package review instructions). "
    "Complete each owned code/documentation package with authored, versioned work and a passing "
    "public check; complete test/diagnostic work with scoped, source-bound evidence via "
    "complete_evidence, without creating a code patch for it. Independent review is optional "
    "for ordinary single-author contributions. When both members author code across packages, "
    "obtain independent acceptance of each author's contribution. An owner in either arm may "
    "fill a required vacant reviewer via assign_verification. Inspect delivery_readiness. "
    "Adopt partner work, resolve conflicts, test and fix the final version, then explicitly submit."
)


class FairWorld(ReviewWorld):
    def _review_needed(self, tid):
        work = self.dynamic()["work"]
        authors = {a for p in work.values() if not p["children"] for a in p["authors"]}
        return bool(work[tid]["authors"] and len(authors) > 1)

    def _action_work_readiness(self, actor, project_id, task_id):
        status = super()._action_work_readiness(actor, project_id, task_id)
        # Assignment and independent acceptance are checked at delivery when applicable.
        status["gaps"] = [
            g
            for g in status["gaps"]
            if g["kind"] not in {"independent_reviewer_missing_or_invalid", "collaboration_missing"}
        ]
        status["ready"] = not status["gaps"]
        return status

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if tool == "assign_verification" and self.protocol().get("graph_control"):
            # Only a required, vacant role may pass the frozen graph maintenance boundary.
            # The native dispatch below still enforces schema, identity, scheduling and lifecycle.
            tid = arguments.get("task_id")
            package = self.dynamic()["work"].get(tid)
            if (
                package
                and not package["children"]
                and package["reviewer"] is None
                and self._review_needed(tid)
            ):
                return super(ControlledWorld, self)._tool_project_action(
                    actor, project_id, tool, arguments, interface_profile
                )
        return super()._tool_project_action(actor, project_id, tool, arguments, interface_profile)

    def _action_assign_verification(self, actor, project_id, task_id, reviewer, reason):
        w = self._owned_leaf(actor, task_id, allow_complete=True)
        if reviewer not in self.live_members() or reviewer == actor or reviewer in w["authors"]:
            self.org_reject("Select a non-author member", "dynamic_self_review")
        w["reviewer"] = reviewer
        edges = self.dynamic()["collaboration"]
        for edge in ([task_id, actor, reviewer], [task_id, reviewer, actor]):
            if edge not in edges:
                edges.append(edge)
        e = self._event_dynamic(
            actor, "verification_assigned", task_id=task_id, reviewer=reviewer, reason=reason
        )
        return dict(event_sequence=e["sequence"], reviewer=reviewer, automatic_review=False)

    def _action_complete_work(self, actor, project_id, task_id, patch_id):
        package = self._owned_leaf(actor, task_id)
        patch = self._patch(patch_id)
        identity = self.org_current_identity(actor)
        if (
            patch["author"] != actor
            or task_id not in patch["task_snapshots"]
            or not self._artifact_current(patch)
            or identity != self.org_patch_identity(patch_id)
        ):
            self.org_reject(
                "Publish the current authored work-bound version", "dynamic_completion_version"
            )
        test = self._fresh_test(actor, identity, [task_id], must_pass=True)
        task = self._task(task_id)
        completion = dict(
            kind="code",
            patch_id=patch_id,
            author=actor,
            identity=identity,
            work_epoch=self.epoch(task_id),
            task_revision=task["revision"],
            test_sequence=test["sequence"],
            dependency_epochs={k: self.epoch(k) for k in task["depends_on"]},
        )
        package["completion"] = completion
        event = self._event_dynamic(
            actor,
            "work_locally_completed",
            task_id=task_id,
            completion=completion,
            official_success_known=False,
        )
        return dict(event_sequence=event["sequence"], **deepcopy(completion), official_score=None)

    def _contribution_present(self, completion, member):
        patch = self._patch(completion["patch_id"])
        _, _, current = self._bundle(member)
        _, _, source = self._bundle(completion["author"], patch_id=patch["patch_id"])
        return all(
            current[k].get(path) == source[k].get(path)
            for path in patch["changed_paths"]
            for k in ("files", "entry_metadata")
        )

    def _completion_current(self, tid):
        if not super()._completion_current(tid):
            return False
        c = self.dynamic()["work"][tid]["completion"]
        if c.get("kind") != "code" or self.org_current_identity(c["author"]) == c["identity"]:
            return True
        return self._contribution_present(c, c["author"])

    def _action_delivery_checklist(self, actor, project_id):
        result = super()._action_delivery_checklist(actor, project_id)
        for p in result["packages"]:
            c = p["completion"]
            if not self._review_needed(p["task_id"]):
                p["missing"] = [
                    g
                    for g in p["missing"]
                    if g not in {"assign_verification", "independent_current_review"}
                ]
            if (
                c
                and c.get("kind") == "code"
                and c["author"] != actor
                and "integrate_partner_patch" not in p["missing"]
                and not self._contribution_present(c, actor)
            ):
                if "reopen_stale_completion" not in p["missing"]:
                    p["missing"].append("reopen_stale_completion")
            p["independent_review_required"] = self._review_needed(p["task_id"])
        result.update(
            version="v245-fair-delivery",
            package_chain_ready=all(not p["missing"] for p in result["packages"]),
        )
        return result

    def _action_delivery_readiness(self, actor, project_id):
        result = super()._action_delivery_readiness(actor, project_id)
        for pkg in result["package_chain"]["packages"]:
            if "assign_verification" in pkg["missing"]:
                result["next_actions"].insert(
                    0,
                    dict(
                        actor=pkg["owner"],
                        task_id=pkg["task_id"],
                        tool="assign_verification",
                        note="The owner may fill the required independent role under either organization policy.",
                    ),
                )
        result["delivery_contract"] = NOTICE
        return result

    def _closing_steps(self, actor):
        value = super()._closing_steps(actor)
        value.update(
            requires_independent_review=any(self._review_needed(k) for k in self.dynamic()["work"]),
            verification_scope="task-level; independent acceptance for multi-author contributions",
            delivery_contract=NOTICE,
        )
        return value

    def _organization_overview(self, actor):
        v = super()._organization_overview(actor)
        v["independent_review_required"] = any(
            self._review_needed(t) for t in self.dynamic()["work"]
        )
        v["verification_scope"] = "task-level, contribution-specific"
        v["dynamic_contract"] = NOTICE
        return v


class Execution(PreviousExecution):
    def attach(self, runtime):
        super().attach(runtime)
        runtime.prepared.world.__class__ = FairWorld
        for member in runtime.labels:
            runtime.policies[member].conversation.send_message(NOTICE)
