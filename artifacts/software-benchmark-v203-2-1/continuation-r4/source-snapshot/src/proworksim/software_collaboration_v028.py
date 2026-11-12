"""Bounded software negotiation on the existing v0.27 file/patch world.

The original world, source, tools and acceptance remain reusable. New messages
carry actor content only; neither messages nor responsibility transfers import
file bytes. Runtime availability is a controller projection, not actor-editable
business state, and is separately archived by the v0.28 scheduler.
"""

import copy

from . import software_collaboration_v027 as previous
from .scenarios import initial_business_state
from .storage import atomic_write, digest, json_bytes
from .tool_outcomes import ToolRejection
from .work_interface import _schema_errors
from .world_core import WorldCore

VERSION = "software-collaboration-v0.28"
INTERFACE_REVISION = "software-collaboration-v0.28.1"
DIFF_PAGE_CHARS = 4000
DIFF_MAX_PAGE_CHARS = 6000
SCHEDULER = "round_robin_event_wakeup-v0.28"
PROJECT = previous.PROJECT
MEMBERS = previous.MEMBERS
CASE_IDS = previous.CASE_IDS
EDITABLE = previous.EDITABLE
_REFERENCE = {"type": "object", "properties": {
    "object_id": previous._PATH, "version_id": previous._PATH},
    "required": ["object_id", "version_id"], "additionalProperties": False}

TOOLS = copy.deepcopy(previous.TOOLS)
for _definition in TOOLS:
    if "message" in _definition["parameters"]["properties"]:
        _definition["parameters"]["properties"]["message"] = {"type": "string", "maxLength": 4000}
    if _definition["name"] == "delegate_task":
        _definition["description"] = (
            "Transfer your task to the other available member and notify them. "
            "The recipient may return it to the unassigned board using return_task. "
            "Finished or exhausted members cannot receive responsibility.")
    if _definition["name"] == "diff_workspace":
        _definition["description"] = (
            "Read an exact page of unified diff against the frozen baseline. "
            "Offsets count Unicode characters; default page is 4000, maximum 6000. "
            "Continue with next_offset and the returned source_reference to pin the same version. "
            "Your historical workspace versions and published fixed versions remain readable.")
        _definition["parameters"]["properties"] = {
            "offset": {"type": "integer", "minimum": 0},
            "max_chars": {"type": "integer", "minimum": 1, "maximum": DIFF_MAX_PAGE_CHARS},
            "source_reference": copy.deepcopy(_REFERENCE),
        }
TOOLS += [
    previous._tool("send_message", "Send a work message before or after edits. Does not claim, import, adopt or merge anything. Optional reference must already be publicly fixed.",
                   {"recipient": previous._MEMBER, "task_id": previous._PATH,
                    "body": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "fixed_reference": {"type": "object", "properties": {
                        "object_id": previous._PATH, "version_id": previous._PATH},
                        "required": ["object_id", "version_id"], "additionalProperties": False}},
                   ["recipient", "task_id", "body"]),
    previous._tool("return_task", "Decline or relinquish your current task to the unassigned board; notify the other member without assigning it to them.",
                   {"task_id": previous._PATH, "reason": {"type": "string", "minLength": 1, "maxLength": 2000}}),
    previous._tool("read_work_event", "Read one exact published patch event or addressed message/notification by its public sequence. Restores full text omitted from the bounded latest observation.",
                   {"sequence": {"type": "integer", "minimum": 1}}),
]


def case_spec(case_id=CASE_IDS[0], *, first_member=MEMBERS[0], role_decision_limits=None):
    if first_member not in MEMBERS:
        raise ValueError("The first opportunity must belong to one stable member")
    limits = dict.fromkeys(MEMBERS, 48) if role_decision_limits is None else copy.deepcopy(role_decision_limits)
    if (not isinstance(limits, dict) or set(limits) != set(MEMBERS)
            or any(type(value) is not int or not 1 <= value <= 128 for value in limits.values())):
        raise ValueError("Freeze a finite decision limit from 1 to 128 for each member")
    case = previous.case_spec(case_id)
    case.update(version=VERSION, first_member=first_member, role_decision_limits=limits,
                scheduling_protocol=SCHEDULER,
                responsibility_scope="Autonomous claiming and transfer of two predefined tasks; no autonomous task decomposition")
    return case


def validate_case(case):
    if not isinstance(case, dict) or case != case_spec(
            case["case_id"], first_member=case["first_member"],
            role_decision_limits=case["role_decision_limits"]):
        raise ValueError("Case differs from the frozen v0.28 development declaration")
    return case


class SoftwareCollaborationWorld(previous.SoftwareCollaborationWorld):
    def member_availability(self):
        callback = getattr(self, "runtime_availability", None)
        if callback is not None:
            return copy.deepcopy(callback())
        limits = self._software()["case"]["role_decision_limits"]
        return {member: {"status": "ready", "remaining_decisions": limits[member],
                         "can_receive_work": True} for member in MEMBERS}

    def _tool_definitions(self, project_id):
        return copy.deepcopy(TOOLS) if project_id == PROJECT else super()._tool_definitions(project_id)

    def _tool_project_action(self, actor, project_id, tool, arguments, interface_profile=None):
        if project_id != PROJECT or actor not in MEMBERS:
            raise ValueError("Only the two bound software members may use this interface")
        specs = {entry["name"]: entry for entry in TOOLS}
        if tool not in specs:
            raise ToolRejection("Not in the software interface", code="tool_not_enabled", category="capability_gap")
        errors = _schema_errors(specs[tool]["parameters"], arguments)
        # The legacy schema helper predates maxLength. Enforce the new public
        # message limits here instead of merely advertising them to the model.
        for name, schema in specs[tool]["parameters"].get("properties", {}).items():
            if (isinstance(arguments.get(name), str) and "maxLength" in schema
                    and len(arguments[name]) > schema["maxLength"]):
                errors.append(name + " exceeds the declared text limit")
        if errors:
            raise ToolRejection("; ".join(errors), code="public_argument_schema", category="policy_error")
        return WorldCore._tool_project_action(self, actor, project_id, tool, arguments, interface_profile)

    def _available_recipient(self, actor, recipient):
        if recipient not in MEMBERS or recipient == actor:
            raise ValueError("Choose the other stable member")
        if not self.member_availability()[recipient]["can_receive_work"]:
            raise ValueError("Recipient has ended or exhausted its budget and cannot receive new work")

    def _action_diff_workspace(self, actor, project_id, offset=0, max_chars=DIFF_PAGE_CHARS,
                               source_reference=None):
        # The legacy schema subset does not enforce numeric maxima. Check the
        # complete page contract here, including direct internal invocations.
        if type(offset) is not int or offset < 0:
            raise ValueError("Diff offset must be a nonnegative character index")
        if type(max_chars) is not int or not 1 <= max_chars <= DIFF_MAX_PAGE_CHARS:
            raise ValueError("Diff page must contain from 1 to 6000 characters")
        if offset and source_reference is None:
            raise ValueError("Continue with the preceding page's source_reference, or restart at offset 0")
        if source_reference is not None:
            public = [patch["source_reference"] for patch in self._software()["patches"].values()]
            public += [delivery["source_reference"] for delivery in self._software()["deliveries"]]
            if (source_reference["object_id"] != self._resolve(PROJECT, actor)
                    and source_reference not in public):
                raise ValueError("Choose your workspace version or an already published fixed version")
        # _bundle/_object still enforce project and exact-version read grants;
        # sharing one patch must never expose later private versions of it.
        artifact, version, bundle = self._bundle(actor, reference=source_reference)
        base_artifact, base_version, baseline = self._bundle(actor, baseline=True)
        full_diff = previous._diff(baseline["files"], bundle["files"])
        if offset > len(full_diff):
            raise ValueError("Diff offset exceeds total_chars for this fixed source version")
        end = min(offset + max_chars, len(full_diff))
        return {"interface_revision": INTERFACE_REVISION,
                "source_reference": previous._reference(artifact, version),
                "base_reference": previous._reference(base_artifact, base_version),
                "diff": full_diff[offset:end], "diff_sha256": digest(full_diff.encode()),
                "total_chars": len(full_diff), "offset": offset,
                "next_offset": end if end < len(full_diff) else None,
                "has_more": end < len(full_diff), "offset_unit": "unicode_characters"}

    def _action_send_message(self, actor, project_id, recipient, task_id, body, fixed_reference=None):
        self._available_recipient(actor, recipient)
        self._task(task_id)
        if not body.strip():
            raise ValueError("Work message body must not be blank")
        if fixed_reference is not None:
            references = [patch["source_reference"] for patch in self._software()["patches"].values()]
            references += [delivery["source_reference"] for delivery in self._software()["deliveries"]]
            if fixed_reference not in references:
                raise ValueError("Message reference must identify an already published fixed patch or delivery")
        event = self._event(actor, "work_message", recipient=recipient, task_id=task_id,
                            body=body, fixed_reference=fixed_reference)
        return {"message_sequence": event["sequence"], "recipient": recipient,
                "task_id": task_id, "world_file_effect": False}

    def _action_delegate_task(self, actor, project_id, task_id, to_member):
        task = self._task(task_id, actor)
        self._available_recipient(actor, to_member)
        task["owner"] = to_member
        self._event(actor, "delegate", task_id=task_id, previous_owner=actor,
                    owner=to_member, recipient=to_member,
                    notification="Responsibility transferred; return_task may decline to the unassigned board")
        return copy.deepcopy(task)

    def _action_return_task(self, actor, project_id, task_id, reason):
        task = self._task(task_id, actor)
        if not reason.strip():
            raise ValueError("Explain the return of responsibility")
        task["owner"] = None
        recipient = next(member for member in MEMBERS if member != actor)
        self._event(actor, "task_returned", task_id=task_id, previous_owner=actor,
                    owner=None, recipient=recipient, reason=reason)
        return copy.deepcopy(task)

    def _action_handoff_patch(self, actor, project_id, patch_id, to_member, message):
        self._available_recipient(actor, to_member)
        return super()._action_handoff_patch(actor, project_id, patch_id, to_member, message)

    def _action_read_work_event(self, actor, project_id, sequence):
        events = [event for event in self.state["software_events"] if event["sequence"] == sequence]
        if not events or not (events[0]["kind"] == "patch_fixed" or (
                events[0]["kind"] in {"work_message", "delegate", "task_returned", "handoff"}
                and actor in {events[0]["actor_id"], events[0].get("recipient")})):
            raise ValueError("Choose a public patch or your own addressed work event")
        return copy.deepcopy(events[0])


class SoftwareCollaborationPort(previous.SoftwareCollaborationPort):
    def __init__(self, session, role, **kwargs):
        super().__init__(session, role, **kwargs)
        self.profile = VERSION + ":" + role

    def observe(self):
        observation = super().observe()
        world = self._session._world
        with world.store.lock():
            world.state = world.store.load()
            messages = [copy.deepcopy(event) for event in world.state["software_events"]
                        if event["kind"] in {"work_message", "delegate", "task_returned"}
                        and event.get("recipient") == self.role]
            handoffs = observation["handoffs"]
            patches = observation["patches"]
            observation.update(
                interface_revision=INTERFACE_REVISION,
                member_availability=world.member_availability(),
                messages=messages[-4:], handoffs=handoffs[-4:], patches=patches[-6:],
                deliveries=observation["deliveries"][-2:],
                older_message_sequences=[event["sequence"] for event in messages[:-4]],
                older_handoff_sequences=[event["sequence"] for event in handoffs[:-4]],
                all_fixed_patches=[{"patch_id": event["patch_id"], "sequence": event["sequence"]}
                                   for event in world.state["software_events"] if event["kind"] == "patch_fixed"],
                observation_projection="Latest 4 messages/handoffs, 6 patch summaries and 2 deliveries. Text previews are explicitly truncated; read_work_event(sequence) restores exact original text. All events/versions remain archived.",
                scheduling={"protocol": SCHEDULER, "first_member": world._software()["case"]["first_member"],
                            "wait": "Suspend until a new addressed message/responsibility or partner fixed patch arrives; remaining budget is never reset",
                            "done": "End your own work permanently; the other member retains remaining opportunities",
                            "blocked": "If no member is runnable and no event can arrive, record terminal blocked work"})
            for rows in (observation["messages"], observation["handoffs"], observation["patches"], observation["deliveries"]):
                for row in rows:
                    for key in ("body", "message", "reason"):
                        if isinstance(row.get(key), str) and len(row[key]) > 500:
                            row[key] = row[key][:500]
                            row[key + "_truncated"] = True
        return observation


def build_software_collaboration_case(case, root):
    case = case_spec(case) if isinstance(case, str) else validate_case(copy.deepcopy(case))
    # Reuse pinned assets and deterministic installation, without changing v0.27.
    prepared = previous.build_software_collaboration_case(case["case_id"], root)
    prepared.deployment.world = SoftwareCollaborationWorld(prepared.world.store.root)
    world = prepared.world
    with world.store.lock():
        world.state = world.store.load()
        world._software()["case"] = copy.deepcopy(case)
        world.store.save(world.state)
    prepared.case = copy.deepcopy(case)
    prepared.reward_spec.update(version=VERSION)
    prepared.scenario["boundary"]["max_opportunities"] = sum(case["role_decision_limits"].values()) + len(MEMBERS)
    for role in prepared.scenario["roles"]:
        role["config"]["task"] = (
            "Collaborate on the public software requirements. Choose among the predefined tasks; "
            "both stable members have the same tools and may implement, integrate or test. "
            "send_message permits negotiation before edits. claim_task is atomic; delegate_task notifies "
            "an available partner, who may return_task. staff_wait suspends until new addressed work "
            "or a partner patch; staff_done permanently ends only your own opportunities. "
            "Publish and test an exact integrated version before submit_integration. "
            "A partner fixed patch is visible but importing it always requires integrate_patch.")
    prepared.prefix.update(version=VERSION,
                           prepared_business_state_sha256=digest(json_bytes(initial_business_state(world))))
    prepared.port_factory = SoftwareCollaborationPort
    atomic_write(world.store.root.parent / "preparation.json", json_bytes(prepared.prefix))
    return prepared


def software_collaboration_facts(prepared_or_state):
    facts = previous.software_collaboration_facts(prepared_or_state)
    facts["version"] = VERSION
    return facts


def assess_software_collaboration(prepared, *, run_root):
    result = previous.assess_software_collaboration(prepared, run_root=run_root)
    result["version"] = VERSION
    return result
