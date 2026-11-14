"""Artifact-driven PIPELINE and bounded SPRINT organization protocols.

Only public organization metadata is added. No method starts a model, test,
merge or responsibility transfer on behalf of an agent.
"""
from __future__ import annotations

import copy

M1, M2, M3, M4 = (f"member_{n:03d}" for n in range(1, 5))
DEVELOPERS = (M1, M2)
TEXT = {"type": "string", "minLength": 1, "maxLength": 4000}
IDS = {"type": "array", "items": {"type": "string", "minLength": 1},
       "uniqueItems": True, "maxItems": 64}
PATCH = {"type": "string", "minLength": 1}


def _tool(name, description, properties, required):
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties,
                           "required": required, "additionalProperties": False}}


def tool_definitions(organization_id):
    if organization_id == "PIPELINE":
        return [
            _tool("org_pipeline_design", "001 publishes the design and exact task revisions; this alone advances design to implementation.",
                  {"task_ids": {**IDS, "minItems": 1}, "design": TEXT}, ["task_ids", "design"]),
            _tool("org_pipeline_implementation", "002 hands off its current immutable patch covering every design task revision; no automatic merge or test.",
                  {"patch_id": PATCH, "summary": TEXT}, ["patch_id", "summary"]),
            _tool("org_pipeline_validation", "003 accepts the exact candidate after its own real same-version public test. Tests need to execute, not necessarily pass; explain the evidence honestly.",
                  {"patch_id": PATCH, "conclusion": TEXT}, ["patch_id", "conclusion"]),
            _tool("org_pipeline_return", "Explicitly return an incomplete handoff to design or implementation with a reason. No stage is successful merely because time elapsed.",
                  {"target_stage": {"type": "string", "enum": ["design", "implementation"]},
                   "reason": TEXT}, ["target_stage", "reason"]),
        ]
    if organization_id == "SPRINT":
        return [
            _tool("org_sprint_propose", "003 proposes a goal and ordered existing tasks. Changing an active goal requires a reason and renewed developer agreement; spent opportunities remain spent.",
                  {"goal": TEXT, "task_ids": {**IDS, "minItems": 1}, "reason": TEXT},
                  ["goal", "task_ids"]),
            _tool("org_sprint_plan", "001 or 002 confirms the proposed goal and chooses its own tasks and plan. The other developer cannot be assigned work by this call.",
                  {"proposal_revision": {"type": "integer", "minimum": 1},
                   "task_ids": IDS, "plan": TEXT}, ["proposal_revision", "task_ids", "plan"]),
            _tool("org_sprint_start", "004 starts or resumes only a goal agreed by both developers. This records a planning decision, without assigning tasks or resetting an active cycle allowance.",
                  {"proposal_revision": {"type": "integer", "minimum": 1}}, ["proposal_revision"]),
            _tool("org_sprint_inspect", "001/002 inspect the same immutable candidate. Supply evidence_id to reuse an already published real-test receipt. Omit patch_id only if this cycle has no published developer candidate; this records no success.",
                  {"patch_id": PATCH, "conclusion": TEXT, "evidence_id": PATCH}, ["conclusion"]),
            _tool("org_sprint_close", "004 records the retrospective after both developers inspected the same candidate. It opens next-cycle planning only; no automatic work, test, merge or success.",
                  {"review_ids": {**IDS, "minItems": 2, "maxItems": 2}, "retrospective": TEXT},
                  ["review_ids", "retrospective"]),
        ]
    return []


def initial_state(organization_id):
    if organization_id == "PIPELINE":
        return {"pipeline": {"stage": "design", "design_revision": 0,
            "design": None, "implementation": None, "validation": None}}
    if organization_id == "SPRINT":
        return {"sprint": {"cycle": 1, "phase": "planning", "proposal_revision": 0,
            "proposal": None, "plans": {}, "used_opportunities": 0,
            "total_observed_opportunities": 0, "started_cycles": 0,
            "cycle_start_patch_ids": [], "first_start_patch_ids": None,
            "inspections": {}, "history": [], "amendments": []}}
    return {}


class FlowMixin:
    def _flow_require(self, condition, message):
        if not condition:
            self.org_reject(message, code="organization_flow")

    def _flow_text(self, value):
        self._flow_require(isinstance(value, str) and bool(value.strip()) and len(value) <= 4000,
                           "Use nonblank bounded organization text")

    def _flow_tasks(self, task_ids, *, nonempty=False):
        self._flow_require(isinstance(task_ids, list) and len(task_ids) <= 64
            and all(isinstance(t, str) and t for t in task_ids)
            and len(task_ids) == len(set(task_ids)) and (bool(task_ids) or not nonempty),
            "Use distinct existing task IDs")
        return {task_id: self._task(task_id)["revision"] for task_id in task_ids}

    def _flow_current_revisions(self, revisions):
        return all(self._task(task_id)["revision"] == revision for task_id, revision in revisions.items())

    def _flow_test_receipt(self, actor, patch_id):
        test = self.org_latest_test(actor, patch_id)
        return {key: copy.deepcopy(test[key]) for key in
                ("sequence", "actor_id", "source_reference", "files_sha256", "entry_metadata_sha256", "executed", "passed")
                if key in test}

    def _pipeline_state(self):
        self._flow_require(self.org_kind() == "PIPELINE", "This operation belongs to PIPELINE")
        return self.org_state()["pipeline"]

    def _pipeline_current_design(self, state):
        design = state.get("design")
        self._flow_require(design is not None and self._flow_current_revisions(design["task_revisions"]),
                           "Design task revisions changed; explicitly return to design")
        return design

    def _action_org_pipeline_design(self, actor, project_id, task_ids, design):
        state = self._pipeline_state()
        self._flow_require(actor == M1 and state["stage"] == "design", "Only 001 in design may publish the design handoff")
        self._flow_text(design)
        revisions = self._flow_tasks(task_ids, nonempty=True)
        state["design_revision"] += 1
        state.update(stage="implementation", design={"revision": state["design_revision"],
            "actor_id": actor, "task_revisions": revisions, "text": design}, implementation=None, validation=None)
        self.org_event(actor, "pipeline_design", design=state["design"])
        return copy.deepcopy(state)

    def _action_org_pipeline_implementation(self, actor, project_id, patch_id, summary):
        state = self._pipeline_state()
        self._flow_require(actor == M2 and state["stage"] == "implementation", "Only 002 in implementation may hand off a candidate")
        self._flow_text(summary)
        design = self._pipeline_current_design(state)
        patch = self._patch(patch_id)
        self._flow_require(patch["author"] == actor
            and self.org_current_identity(actor)["source_reference"] == patch["source_reference"],
            "Hand off your current published implementation version")
        bindings = patch.get("task_snapshots", {})
        self._flow_require(all(bindings.get(task_id, {}).get("revision") == revision
                               for task_id, revision in design["task_revisions"].items()),
                           "Fixed implementation must bind every design task revision")
        state.update(stage="verification", implementation={"patch_id": patch_id,
            "identity": self.org_patch_identity(patch_id), "design_revision": design["revision"],
            "task_revisions": copy.deepcopy(design["task_revisions"]), "summary": summary}, validation=None)
        self.org_event(actor, "pipeline_implementation", implementation=state["implementation"])
        return copy.deepcopy(state)

    def _action_org_pipeline_validation(self, actor, project_id, patch_id, conclusion):
        state = self._pipeline_state()
        self._flow_require(actor == M3 and state["stage"] == "verification", "Only 003 in verification may accept the tested candidate")
        self._flow_text(conclusion)
        self._pipeline_current_design(state)
        self._flow_require(state["implementation"]["patch_id"] == patch_id, "Validate the actual implementation handoff")
        receipt = self._flow_test_receipt(actor, patch_id)
        state.update(stage="integration", validation={"patch_id": patch_id,
            "identity": self.org_patch_identity(patch_id), "actor_id": actor,
            "test": receipt, "conclusion": conclusion})
        self.org_event(actor, "pipeline_validation", validation=state["validation"])
        return copy.deepcopy(state)

    def _action_org_pipeline_return(self, actor, project_id, target_stage, reason):
        state = self._pipeline_state()
        allowed = {"implementation": {M2}, "verification": {M3}, "integration": {M1}}
        self._flow_require(actor in allowed.get(state["stage"], set()), "Only the receiving phase may explicitly return a handoff")
        self._flow_require(target_stage in {"design", "implementation"}
            and not (state["stage"] == "implementation" and target_stage == "implementation"),
            "Return to an earlier applicable stage")
        self._flow_text(reason)
        previous_stage = state["stage"]
        state.update(stage=target_stage, implementation=None, validation=None)
        if target_stage == "design":
            state["design"] = None
        self.org_event(actor, "pipeline_return", previous_stage=previous_stage,
                       target_stage=target_stage, reason=reason)
        return copy.deepcopy(state)

    def _sprint_state(self):
        self._flow_require(self.org_kind() == "SPRINT", "This operation belongs to SPRINT")
        return self.org_state()["sprint"]

    def _sprint_proposal(self, state, revision):
        proposal = state.get("proposal")
        self._flow_require(proposal is not None and proposal["revision"] == revision,
                           "Use the current goal proposal revision")
        self._flow_require(self._flow_current_revisions(proposal["task_revisions"]),
                           "Task revisions changed; PO must renew the proposal")
        return proposal

    def _action_org_sprint_propose(self, actor, project_id, goal, task_ids, reason=""):
        state = self._sprint_state()
        self._flow_require(actor == M3 and state["phase"] in {"planning", "active", "amendment"},
                           "Only PO may propose or negotiate the current goal before review")
        self._flow_text(goal)
        revisions = self._flow_tasks(task_ids, nonempty=True)
        changing_active = state["phase"] in {"active", "amendment"}
        if changing_active:
            self._flow_text(reason)
        if state["proposal"] is not None:
            state["amendments"].append({"cycle": state["cycle"],
                "proposal": copy.deepcopy(state["proposal"]), "plans": copy.deepcopy(state["plans"]),
                "used_opportunities": state["used_opportunities"], "reason": reason})
        state["proposal_revision"] += 1
        state.update(phase="amendment" if changing_active else "planning", plans={},
            proposal={"revision": state["proposal_revision"], "cycle": state["cycle"],
                "goal": goal, "ordered_task_ids": list(task_ids), "task_revisions": revisions,
                "actor_id": actor, "reason": reason})
        self.org_event(actor, "sprint_goal_proposed", proposal=state["proposal"],
                       used_opportunities=state["used_opportunities"])
        return copy.deepcopy(state["proposal"])

    def _action_org_sprint_plan(self, actor, project_id, proposal_revision, task_ids, plan):
        state = self._sprint_state()
        self._flow_require(actor in DEVELOPERS and state["phase"] in {"planning", "amendment", "active"},
                           "Each developer chooses its own implementation plan")
        self._flow_text(plan)
        proposal = self._sprint_proposal(state, proposal_revision)
        revisions = self._flow_tasks(task_ids)
        self._flow_require(set(task_ids) <= set(proposal["ordered_task_ids"]), "Select tasks from the PO's ordered proposal")
        other = M2 if actor == M1 else M1
        self._flow_require(not set(task_ids) & set(state["plans"].get(other, {}).get("task_ids", [])),
                           "Developers must explicitly resolve overlapping task selection")
        self._flow_require(all(self._task(task_id)["owner"] in {None, actor} for task_id in task_ids),
                           "A plan cannot take over another member's actual task ownership")
        record = {"actor_id": actor, "proposal_revision": proposal_revision,
                  "task_ids": list(task_ids), "task_revisions": revisions, "plan": plan}
        state["plans"][actor] = record
        self.org_event(actor, "sprint_developer_plan", plan=record)
        return copy.deepcopy(record)

    def _action_org_sprint_start(self, actor, project_id, proposal_revision):
        state = self._sprint_state()
        self._flow_require(actor == M4 and state["phase"] in {"planning", "amendment"},
                           "Only SM may record the completed planning agreement")
        self._sprint_proposal(state, proposal_revision)
        self._flow_require(set(state["plans"]) == set(DEVELOPERS)
            and all(row["proposal_revision"] == proposal_revision for row in state["plans"].values())
            and any(row["task_ids"] for row in state["plans"].values()),
            "Both developers must explicitly agree and select a nonempty joint plan")
        resuming = state["phase"] == "amendment"
        if not resuming:
            state["used_opportunities"] = 0
            state["cycle_start_patch_ids"] = sorted(self._software()["patches"])
            state["inspections"] = {}
            state["started_cycles"] += 1
            if state["first_start_patch_ids"] is None:
                state["first_start_patch_ids"] = list(state["cycle_start_patch_ids"])
        limit = self._software()["case"]["fixed_organization"]["sprint_opportunities"]
        self._flow_require(state["used_opportunities"] < limit, "A negotiated goal cannot extend an expired cycle")
        state["phase"] = "active"
        self.org_event(actor, "sprint_started" if not resuming else "sprint_goal_amended",
                       cycle=state["cycle"], proposal_revision=proposal_revision,
                       plans=state["plans"], used_opportunities=state["used_opportunities"],
                       opportunity_limit=limit)
        return {"cycle": state["cycle"], "phase": state["phase"],
                "used_opportunities": state["used_opportunities"], "opportunity_limit": limit}

    def _sprint_cycle_patches(self, state):
        return {pid for pid, patch in self._software()["patches"].items()
                if pid not in state["cycle_start_patch_ids"] and patch["author"] in DEVELOPERS}

    def _action_org_sprint_inspect(self, actor, project_id, conclusion, patch_id=None, evidence_id=None):
        state = self._sprint_state()
        self._flow_require(actor in DEVELOPERS and state["phase"] == "review",
                           "The two developers inspect actual cycle outcomes after the fixed opportunity window")
        self._flow_text(conclusion)
        candidates = self._sprint_cycle_patches(state)
        test, identity = None, None
        if patch_id is None:
            self._flow_require(not candidates and evidence_id is None,
                               "A no-candidate inspection requires that this cycle published no developer candidate")
        else:
            self._flow_require(patch_id in candidates, "Inspect a developer candidate actually published in this cycle")
            identity = self.org_patch_identity(patch_id)
            if evidence_id is not None:
                earlier = state["inspections"].get(evidence_id)
                self._flow_require(earlier is not None and earlier["cycle"] == state["cycle"]
                    and earlier["patch_id"] == patch_id and earlier["identity"] == identity
                    and earlier.get("test", {}).get("executed") is True,
                    "Reuse only an already published same-candidate real-test inspection")
                test = copy.deepcopy(earlier["test"])
            else:
                test = self._flow_test_receipt(actor, patch_id)
        inspection_id = f"cycle-{state['cycle']}-inspection-{len(state['inspections']) + 1}"
        record = {"inspection_id": inspection_id, "cycle": state["cycle"], "actor_id": actor,
                  "patch_id": patch_id, "identity": identity, "test": test, "conclusion": conclusion,
                  "reused_evidence_id": evidence_id, "no_candidate": patch_id is None}
        state["inspections"][inspection_id] = record
        self.org_event(actor, "sprint_inspection", inspection=record)
        return copy.deepcopy(record)

    def _action_org_sprint_close(self, actor, project_id, review_ids, retrospective):
        state = self._sprint_state()
        self._flow_require(actor == M4 and state["phase"] == "review", "Only SM closes the retrospective after inspection")
        self._flow_text(retrospective)
        self._flow_require(isinstance(review_ids, list) and len(review_ids) == 2
            and len(set(review_ids)) == 2, "Reference both developers' explicit inspections")
        reviews = [state["inspections"].get(key) for key in review_ids]
        self._flow_require(all(row is not None and row["cycle"] == state["cycle"] for row in reviews)
            and {row["actor_id"] for row in reviews} == set(DEVELOPERS)
            and reviews[0]["patch_id"] == reviews[1]["patch_id"]
            and reviews[0]["identity"] == reviews[1]["identity"],
            "Both developers must inspect the same actual candidate or the same no-candidate outcome")
        if reviews[0]["patch_id"] is None:
            self._flow_require(not self._sprint_cycle_patches(state), "A candidate was published after the no-candidate inspection")
        else:
            self._flow_require(any(row["test"] and row["test"].get("executed") is True for row in reviews),
                               "Candidate inspection needs actual public-test evidence")
        closed = {"cycle": state["cycle"], "proposal": copy.deepcopy(state["proposal"]),
                  "plans": copy.deepcopy(state["plans"]), "review_ids": list(review_ids),
                  "inspections": copy.deepcopy(reviews), "retrospective": retrospective,
                  "used_opportunities": state["used_opportunities"], "success_declared": False}
        state["history"].append(closed)
        state.update(cycle=state["cycle"] + 1, phase="planning", proposal=None, plans={},
                     used_opportunities=0, cycle_start_patch_ids=[], inspections={})
        self.org_event(actor, "sprint_closed", closed_cycle=closed,
                       next_cycle=state["cycle"], next_phase="planning")
        return copy.deepcopy(closed)

    def _org_guard_flow(self, actor, tool, arguments):
        kind = self.org_kind()
        if kind == "PIPELINE":
            state = self.org_state()["pipeline"]
            stage = state["stage"]
            if tool == "integrate_patch" and actor in {M1, M3}:
                expected = "integration" if actor == M1 else "verification"
                self._flow_require(stage == expected and state["implementation"] is not None
                    and arguments.get("patch_id") == state["implementation"]["patch_id"],
                    "Explicitly integrate only the candidate handed to this pipeline phase")
                self._pipeline_current_design(state)
            if tool == "fix_patch" and actor == M2:
                self._flow_require(stage == "implementation", "Publish implementation only in the implementation phase")
                self._pipeline_current_design(state)
            if tool == "submit_integration":
                self._flow_require(actor == M1 and stage == "integration" and state["validation"] is not None,
                                   "Pipeline delivery requires design, implementation and validation handoffs")
                self._pipeline_current_design(state)
                self._flow_require(state["validation"]["patch_id"]
                    in self._bundle(actor)[2]["included_patch_ids"],
                    "Explicitly integrate the validated handoff before delivering it")
                self._flow_require(self.org_matches_current(actor, state["validation"]["patch_id"]),
                                   "The final tree differs from the validated candidate; return it for new verification")
        elif kind == "SPRINT":
            state = self.org_state()["sprint"]
            if tool in {"claim_task", "offer_transfer", "accept_transfer", "return_task"}:
                self._flow_require(actor in DEVELOPERS, "PO and SM do not take or assign developer task ownership")
                task_id = arguments.get("task_id")
                if tool == "accept_transfer":
                    offer = self._software()["transfer_offers"].get(arguments.get("offer_id"), {})
                    task_id = offer.get("task_id")
                self._flow_require(state["phase"] in {"planning", "active", "amendment"},
                                   "Complete the inspection before taking further implementation work")
                if tool != "return_task":
                    proposal = state.get("proposal")
                    self._flow_require(proposal is not None and task_id in proposal["ordered_task_ids"],
                                       "Developer ownership must refer to the proposed goal's tasks")
                if tool == "offer_transfer":
                    self._flow_require(arguments.get("to_member") in DEVELOPERS,
                                       "Transfer developer responsibility only to the other developer")
            if tool == "fix_patch":
                self._flow_require(actor in DEVELOPERS and state["phase"] == "active",
                                   "Only an active developer may publish a sprint implementation")
                proposal = self._sprint_proposal(state, state["proposal_revision"])
                selected = {task_id for row in state["plans"].values() for task_id in row["task_ids"]}
                self._flow_require(set(arguments.get("task_ids", [])) <= selected,
                                   "Fixed task bindings must belong to the jointly selected sprint work")
                self._flow_require(bool(proposal["ordered_task_ids"]), "A sprint needs its original agreed work")
            if tool == "submit_integration":
                self._flow_require(actor == M1 and state["started_cycles"] > 0,
                                   "Delivery follows at least one agreed sprint; early delivery remains allowed")
                current = self.org_current_identity(actor)["source_reference"]
                self._flow_require(any(patch["author"] == actor and patch["source_reference"] == current
                    and pid not in (state["first_start_patch_ids"] or [])
                    for pid, patch in self._software()["patches"].items()),
                    "Deliver an actual developer candidate fixed during an agreed sprint")

    def _org_flow_active_members(self):
        if self.org_kind() == "PIPELINE":
            member = {"design": M1, "implementation": M2, "verification": M3,
                      "integration": M1}[self.org_state()["pipeline"]["stage"]]
            return {member}
        if self.org_kind() == "SPRINT":
            return {M1, M2, M3, M4}
        return None

    def _org_consume_opportunity(self):
        """Runtime calls under its state lock, outside a model tool transaction."""
        if self.org_kind() != "SPRINT":
            return
        state = self.org_state()["sprint"]
        state["total_observed_opportunities"] += 1
        # Negotiating a replacement goal is still work in the same started
        # cycle. It must not pause the frozen opportunity window.
        if state["phase"] in {"active", "amendment"}:
            state["used_opportunities"] += 1
            limit = self._software()["case"]["fixed_organization"]["sprint_opportunities"]
            if state["used_opportunities"] >= limit:
                state["phase"] = "review"
