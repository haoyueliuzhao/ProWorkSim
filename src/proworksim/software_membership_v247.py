"""OSA-controlled private SDK sessions on the fair-delivery world. No worker birth tool."""

from copy import deepcopy
from types import SimpleNamespace

from . import software_role_baseline_runtime_v141 as base
from . import software_natural_organization_runtime_v224_2 as native
from . import software_organization_v038 as lifecycle
from .software_fixed_organization_clone_v131 import clone_function
from .software_fair_delivery_v245 import FairWorld
from .software_graph_controller_v228 import PROJECT

POOL = ("member_001", "member_002", "member_003")
INSTRUCTION = (
    "You are a coding worker in a managed team. See dynamic_status for current members, "
    "owners, duties, dependencies and work scope. Use only your own workspace and authorized "
    "public events. Use begin_work before editing; test and publish a version-bound artifact. "
    "Share evidence or a fixed patch with its named recipient. The recipient must inspect and "
    "explicitly adopt it. Multiple code authors require independent review; the delivery owner "
    "integrates, tests, fixes and submits the final tree. The team shares one token budget."
)


def capacity_tools(tools):
    rows = deepcopy(tools)
    for row in rows:
        spec = row.get("function", row)
        for key, field in spec["parameters"].get("properties", {}).items():
            if (
                key in {"recipient", "to_member", "reviewer", "peer"}
                and field.get("enum")
                and set(field["enum"]) <= set(POOL)
            ):
                field["enum"] = list(POOL)
    return rows


class World(FairWorld):
    def _tool_definitions(self, project_id):
        return capacity_tools(super()._tool_definitions(project_id))

    def organization_active_members(self):
        self.state = self.store.load()
        return tuple(m for m in self.live_members() if m not in self.control()["paused"])

    def control(self):
        return self._software()["membership_v247"]

    def _organization_overview(self, actor=None):
        overview = super()._organization_overview(actor)
        overview.update(
            members=self.live_members(),
            member_status={m: v["status"] for m, v in self._software()["registry"].items()},
            assignments=deepcopy(self.control()["roles"]),
        )
        return overview

    def validate_closing_roster(self):
        spec = deepcopy(self._software()["case"]["fixed_organization"])
        if (
            spec["fixed_members"] != self.live_members()
            or spec["delivery_member"] != POOL[0]
            or not set(spec["fixed_members"]) <= set(POOL)
            or len(spec["fixed_members"]) not in (2, 3)
        ):
            raise ValueError("Inconsistent dynamic closing roster")
        return spec

    def freeze_worker_graph(self):
        with self.store.lock():
            self.state = self.store.load()
            self.protocol().setdefault(
                "graph_control", {"versions": [], "duties": {}, "blockers": []}
            )
            self.store.save(self.state)

    def change_roster(self):
        case = self._software()["case"]
        members = self.live_members()
        case["active_roles"] = list(members)
        spec = case["fixed_organization"]
        spec.update(
            fixed_members=list(members),
            member_count=len(members),
            communication_edges=[[a, b] for a in members for b in members if a != b],
        )
        for m in members:
            spec["roles"].setdefault(m, deepcopy(spec["roles"][POOL[0]]))
            case["role_decision_limits"].setdefault(m, case["team_limits"]["max_decisions"])

    def bootstrap_three(self, reason):
        with self.store.lock():
            self.state = self.store.load()
            if self.live_members() != list(POOL[:2]) or self.control()["version"]:
                raise ValueError("Initial state only")
            self.join(reason)
            self.store.save(self.state)

    def join(self, reason):
        self._writes = []
        result = lifecycle.SoftwareCollaborationWorld._action_spawn_member(
            self, POOL[0], PROJECT, reason
        )
        self.state["shares"].append(
            {
                "project_id": PROJECT,
                **result["initial_source_reference"],
                "actor_ids": [result["member_id"]],
                "shared_by": "operator",
                "at": self.state["clock"],
            }
        )
        self.change_roster()
        return result

    def retire(self, member, reason):
        result = lifecycle.SoftwareCollaborationWorld._action_retire_member(
            self, member, PROJECT, reason
        )
        self.change_roster()
        return result


class Runtime(base.OrganizationRuntime):
    def sync_members(self):
        world = self.prepared.world
        world.state = world.store.load()
        registry = world._software()["registry"]
        for member, record in registry.items():
            if record["status"] == "retired":
                self.waiting.pop(member, None)
                self.stopped[member] = "retired"
                self.roles[member]["status"] = "retired"
            elif member not in self.policies:
                owner = self.owner
                profile = owner.membership_profile
                if member not in owner.adapters:
                    adapter = owner.make_member_adapter(member, profile.wire_tools())
                    owner.adapters[member] = adapter
                    owner.member_owners[member] = base.MemberOwner(
                        adapter, window_id=owner.window_id, identity=owner.identity
                    )
                with self.team_budget._lock:
                    if member not in self.team_budget._state["members"]:
                        self.team_budget._state["members"].append(member)
                port, worker = self.member_factory(member, record)
                self.ports[member], self.policies[member] = port, worker
                self.labels.append(member)
                self.roles[member] = {
                    "memory": {},
                    "last_action": None,
                    "last_result": None,
                    "status": "ready",
                    "actions": 0,
                    "opportunities": 0,
                    "identity": None,
                }
                self.policy_identities[member] = {
                    "implementation": type(worker).__qualname__,
                    "config": deepcopy(worker.config),
                }
                self.birth_records[member] = self._birth_record(member, initial=False)
                self.recorder.record(
                    "organization_session_born", self.birth_records[member], worker_id=member
                )
                self.bind_member_review(member, worker)
                worker.conversation.send_message(record["briefing"])
        self.members = tuple(world.live_members())
        self.schedule.members = self.members
        world.test_budget.members = self.members

    def select_next(self):
        self.sync_members()
        world = self.prepared.world
        priority = world.control()["priority"]
        available = (
            set(world.organization_active_members()) - set(self.stopped) - set(self.work_ended)
        )
        if priority and priority[0] in available:
            member = priority[0]
            self.waiting.pop(member, None)
            self._selected = self.schedule.choose({member})
            self.cursor = self.labels.index(member)
            self.organization_blocked = False
            return deepcopy(self._selected)
        return super().select_next()

    def _step(self):
        selected = self._selected or self.select_next()
        if selected is None:
            return super()._step()
        before = self.opportunities
        try:
            return super()._step()
        finally:
            if self.opportunities > before:
                w = self.prepared.world
                with w.store.lock():
                    w.state = w.store.load()
                    q = w.control()["priority"]
                    if q and q[0] == selected["member"]:
                        q.pop(0)
                        w.store.save(w.state)


class Profile:
    runtime_type = Runtime

    def wire_tools(self):
        return capacity_tools(native.member_wire_tools("FREE2", POOL[0]))

    def validate_session(self, world, member, record):
        if (
            member not in POOL
            or record != world._software()["registry"].get(member)
            or record["status"] != "live"
        ):
            raise ValueError("Session requires a current live world identity")

    def worker_config(self, owner, prepared, member, public):
        case = deepcopy(prepared.case)
        case["role_decision_limits"][member] = case["team_limits"]["max_decisions"]
        factory = clone_function(
            base.worker_config,
            {
                **base.worker_config.__globals__,
                "world": SimpleNamespace(
                    member_instruction=lambda c, m: INSTRUCTION + " Your identity is " + m + "."
                ),
            },
        )
        return factory(owner, case, member, public_initial_message=public)


def install(prepared, owner):
    w = prepared.world
    w.__class__ = World
    with w.store.lock():
        w.state = w.store.load()
        sw = w._software()
        if "membership_v247" in sw:
            raise ValueError("Already initialized")
        sw["case"]["member_limits"].update(
            births_enabled=True, max_live_members=3, max_cumulative_births=3
        )
        sw["membership_v247"] = dict(roles={}, paused=[], priority=[], receipts={}, version=0)
        w.store.save(w.state)
    owner.membership_profile = Profile()
    # The observer admits events for the pool; the world registry authorizes actual sessions.
    owner.observation.log.members = POOL
    return w
