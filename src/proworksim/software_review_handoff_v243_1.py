"""Keep an assigned review tied to the current completed work revision, using native permissions."""

import json
from .software_event_orders_v243 import Execution as EventExecution, OrderedWorld
from .storage import atomic_write, json_bytes


def current_target(world, order):
    task = order["task"]
    package = world.dynamic()["work"].get(task)
    if (
        not package
        or package.get("reviewer") != order["actor"]
        or world._task(task)["owner"] != order["recipient"]
    ):
        return dict(status="assignment_changed", patch=None, version=None)
    epoch = world.epoch(task)
    completion = package.get("completion")
    if not completion or not world._completion_current(task):
        return dict(status="awaiting_completed_candidate", epoch=epoch, patch=None, version=None)
    if completion.get("kind") != "code" or completion.get("author") != order["recipient"]:
        return dict(status="not_authored_code_candidate", epoch=epoch, patch=None, version=None)
    patch = world._patch(completion["patch_id"])
    version = completion["identity"]["source_reference"]
    if (
        task not in patch["task_snapshots"]
        or not world._artifact_current(patch)
        or patch["author"] != completion["author"]
        or patch["source_reference"] != version
    ):
        return dict(status="awaiting_completed_candidate", epoch=epoch, patch=None, version=None)
    return dict(status="review_current", epoch=epoch, patch=completion["patch_id"], version=version)


class ReviewWorld(OrderedWorld):
    def _available_recipient(self, actor, recipient):
        try:
            return super()._available_recipient(actor, recipient)
        except ValueError as exc:
            if str(exc) != "Recipient cannot receive new work under the remaining shared budget":
                raise
            self.org_reject(
                "No work capacity remains for this recipient. This message was not delivered.",
                "recipient_budget_unavailable",
                recipient=recipient,
            )

    def _action_dynamic_status(self, actor, project_id):
        result = super()._action_dynamic_status(actor, project_id)
        for order in result.get("execution_orders", {}).values():
            if order.get("dimension") == "D5":
                effective = current_target(self, order)
                order.update(
                    original_artifact=order["artifact"],
                    artifact=effective["patch"],
                    version=effective["version"],
                    review_status=effective["status"],
                )
        return result


class Execution(EventExecution):
    def attach(self, runtime):
        super().attach(runtime)
        runtime.prepared.world.__class__ = ReviewWorld
        self.targets = {}
        self.promoted = set()
        self.events = []
        step = runtime.step

        def with_handoff():
            outcome = step()
            self.after_review_step(outcome)
            return outcome

        runtime.step = with_handoff

    def log(self, event, **data):
        self.events.append(dict(event=event, ordinal=self.runtime.opportunities, **data))
        atomic_write(self.folder / "review-handoff.json", json_bytes(self.events))

    def apply_order(self, node, observer, frozen, choice, key, order):
        active = super().apply_order(node, observer, frozen, choice, key, order)
        if order["dimension"] == "D5":
            self.targets[key] = current_target(self.runtime.prepared.world, order)
            self.log("registered", key=key, target=self.targets[key])
        return active

    def notify(self, members, notice):
        rt = self.runtime
        informed = []
        for actor in dict.fromkeys(members):
            if actor in rt.stopped or actor in rt.work_ended:
                continue
            rt.policies[actor].conversation.send_message(
                "Review handoff: " + json.dumps(notice, ensure_ascii=False)
            )
            informed.append(actor)
        return informed

    def expedite(self, phase, actor):
        credit = (phase, actor)
        if credit not in self.grants:
            return False
        self.grants.remove(credit)
        # The existing scheduler gives an immediate, protected turn to a new duty.
        self.grants.insert(0, ("new_duty", actor))
        return True

    def after_review_step(self, o):
        if not self.targets:
            return
        world = self.runtime.prepared.world
        if world.protocol()["terminal"]:
            return
        response = o.get("response") or {}
        if not response.get("ok"):
            return
        action = o.get("decision") or {}
        args = action.get("arguments") or {}
        tool = action.get("action")
        if tool not in {
            "fix_patch",
            "reopen_work",
            "complete_work",
            "complete_evidence",
            "run_patch_review_tests",
            "org_review_patch",
        }:
            return
        raw = response["result"]
        for key, old in list(self.targets.items()):
            order = world.protocol()["graph_control"]["execution_orders"][key]
            actor, owner = order["actor"], order["recipient"]
            target = current_target(world, order)
            if old != target:
                self.targets[key] = target
                notice = dict(
                    task=order["task"],
                    previous=old,
                    current=target,
                    guidance="Review only the current completed candidate. Earlier findings can be sent as advice; tests and acceptance remain version-specific.",
                )
                recipients = self.notify([actor, owner], notice)
                expedited = target["status"] == "review_current" and self.expedite(
                    "verification", actor
                )
                self.log(
                    "target_changed",
                    key=key,
                    previous=old,
                    target=target,
                    notified=recipients,
                    expedited=expedited,
                    command=response["command_id"],
                )
            if (
                o.get("worker_id") != actor
                or target["status"] != "review_current"
                or args.get("patch_id") != target["patch"]
            ):
                continue
            identity = (key, target["epoch"], target["patch"])
            if (
                tool == "run_patch_review_tests"
                and raw.get("executed")
                and raw.get("source_reference") == target["version"]
                and identity not in self.promoted
            ):
                self.promoted.add(identity)
                early = self.expedite("publish_artifact", actor)
                recipients = self.notify(
                    [actor],
                    dict(
                        task=order["task"],
                        target=target,
                        guidance="Your public test for this version ran. If ready, record accept or request_changes with org_review_patch on this patch. You may investigate further.",
                    ),
                )
                self.log(
                    "review_tested",
                    key=key,
                    target=target,
                    notified=recipients,
                    expedited=early,
                    command=response["command_id"],
                )
            if (
                tool == "org_review_patch"
                and (raw.get("identity") or {}).get("source_reference") == target["version"]
            ):
                notice = dict(
                    task=order["task"],
                    target=target,
                    verdict=raw.get("decision"),
                    event=raw.get("event_sequence"),
                    guidance="The reviewer registered a version-bound verdict. Read the review event before acting.",
                )
                recipients = self.notify([owner], notice)
                self.log(
                    "formal_verdict",
                    key=key,
                    target=target,
                    verdict=raw.get("decision"),
                    notified=recipients,
                    command=response["command_id"],
                )
