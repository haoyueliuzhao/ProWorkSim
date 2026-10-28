"""CPU-only behavioral controls on the fixed organizations' real managed world.

Tiny public source and programmed public-test replies are synthetic. These
checks neither sample a model nor execute the benchmark, Docker or a GPU.
"""
import copy
import itertools
from types import SimpleNamespace

import pytest

from proworksim import software_fixed_organization_world_v065 as world
from proworksim import software_fixed_organization_runtime_v065 as runtime_module
from proworksim import software_benchmark_managed_v064 as managed
from proworksim.harness_port import HarnessPort
from proworksim.repository_sources_v054 import capture_repository, tree_manifest
from proworksim.software_benchmark_candidates_v054 import read_episode_candidates
from proworksim.software_organization_runtime_v047 import DispatchDeadline
from proworksim.team_budget_v033 import V033PolicyBoundaryError


MEMBERS = tuple(f"member_{index:03d}" for index in range(1, 5))
GROUPS = ("CHIEF", "SOP", "DIALOGUE", "REVIEW", "PEER", "COUNCIL")


def prepare(tmp_path, organization="PEER", *, max_decisions=512):
    source = tmp_path / "public"
    source.mkdir()
    (source / "sample.py").write_text("value = 0\n")
    manifest = capture_repository(source, tmp_path / "snapshot", task_id="fixture__fixed-065",
        problem_statement="Synthetic public source: change value from 0 to 1.",
        source_identity={"instance_id": "fixture__fixed-065", "repo": "fixture/fixed",
                         "base_commit": "a" * 40, "dataset_revision": "b" * 40})
    tests = []

    def public_test(**payload):
        tests.append(copy.deepcopy(payload))
        tree = tree_manifest(payload["files"], payload["entry_metadata"])["tree_sha256"]
        return {"passed": False, "execution": {"executed": True, "input_tree_sha256": tree},
                "groups": {"programmed": {"status": "failed", "executed": True, "passed": False,
                                          "tests": [{"test_id": "programmed-public", "passed": False}]}}}

    deadline = DispatchDeadline(soft_seconds=21600, hard_seconds=23400)
    prepared = runtime_module.prepare_case(manifest, tmp_path / "prepared",
        organization_id=organization, max_total_tokens=5_000_000,
        public_test_callback=public_test, deadline=deadline, max_decisions=max_decisions)
    ports = {member: HarnessPort(world.SoftwareCollaborationPort(
        prepared.world.session(member, world.PROJECT), member), member, project_id=world.PROJECT,
        public_sink=lambda *_: None, world_sink=lambda *_: None, harness_sink=lambda *_: None)
        for member in prepared.case["active_roles"]}
    counter = itertools.count()

    def call(member, tool, **arguments):
        return ports[member].call(tool, request_key=f"programmed-{next(counter)}",
                                  association={}, **arguments)

    for port in ports.values():
        port.tools()
    return prepared, ports, call, tests, deadline


def accepted(call, member, tool, **arguments):
    response = call(member, tool, **arguments)
    assert response["ok"], response
    return response.get("result", response)


def bundle(prepared, member):
    prepared.world.state = prepared.world.store.load()
    return prepared.world._bundle(member)[2]


@pytest.mark.parametrize("organization", GROUPS)
def test_fixed_members_and_equal_basic_coding_capabilities(tmp_path, organization):
    prepared, ports, call, tests, _ = prepare(tmp_path, organization)
    members = tuple(prepared.case["active_roles"])
    state = prepared.world.store.load()
    facts = prepared.world._software()
    assert tuple(facts["registry"]) == members
    assert set(state["actors"]) == {*members, "operator"}
    assert prepared.case["active_roles"] == list(members)
    assert prepared.case["team_limits"]["max_total_tokens"] == 5_000_000
    assert {a["owner"] for a in state["artifacts"].values()} == {*members, "operator"}
    for member, port in ports.items():
        observed = port.observe()["fixed_organization"]
        assert set(observed["role_directory"]) == set(members)
        assert observed["members"] == list(members)
        for definition in port.tools():
            for name in ("recipient", "to_member"):
                prop = definition["parameters"].get("properties", {}).get(name)
                if prop is not None:
                    assert prop["enum"] == list(members)
        names = {tool["name"] for tool in port.tools()}
        assert {"write_file", "create_file", "delete_file", "rename_file", "search_repository",
                "run_tests", "fix_patch", "integrate_patch", "send_message", "offer_transfer"} <= names
        assert not {"spawn_member", "retire_member", "delegate_task", "bash", "terminal"} & names
        assert not call(member, "spawn_member", briefing="No fifth real participant")["ok"]
        assert not call(member, "retire_member", reason="Do not mutate fixed roster")["ok"]
        assert bundle(prepared, member)["files"]["sample.py"] == "value = 0\n"
    assert list(prepared.world._software()["registry"]) == list(members)
    assert all(row["status"] == "live" for row in prepared.world._software()["registry"].values())
    assert tests == []


def test_direct_topology_is_enforced_by_world_not_only_tool_description(tmp_path):
    prepared, _, call, _, _ = prepare(tmp_path, "CHIEF")
    response = call(MEMBERS[1], "send_message", recipient=MEMBERS[2], task_id="root_goal", body="illegal peer shortcut")
    assert not response["ok"]
    accepted(call, MEMBERS[1], "send_message", recipient=MEMBERS[0], task_id="root_goal", body="actual addressed message")
    for member in (MEMBERS[0], MEMBERS[1]):
        assert not call(member, "send_message", recipient="member_005", task_id="root_goal", body="missing member")["ok"]
    assert not call(MEMBERS[1], "send_message", recipient=MEMBERS[0], task_id="root_goal",
                    body="I claim to be the chief", actor_id=MEMBERS[0])["ok"]
    # Bypass of the public wrapper still enters the same guarded WorldCore.
    assert not prepared.world.session(MEMBERS[1], world.PROJECT).call(
        "send_message", recipient=MEMBERS[2], task_id="root_goal", body="direct Session shortcut")["ok"]
    assert tuple(prepared.world._software()["registry"]) == MEMBERS


def test_private_versions_and_workbench_history_are_not_shared(tmp_path):
    prepared, ports, call, _, _ = prepare(tmp_path)
    accepted(call, MEMBERS[0], "work_note", key="private", text="MEMBER_ONE_PRIVATE_NOTE")
    accepted(call, MEMBERS[0], "write_file", path="sample.py", text="MEMBER_ONE_PRIVATE_CODE\n")
    assert "MEMBER_ONE_PRIVATE_NOTE" in str(ports[MEMBERS[0]].observe())
    for member in MEMBERS[1:]:
        observation = ports[member].observe()
        assert "MEMBER_ONE_PRIVATE_NOTE" not in str(observation)
        assert "MEMBER_ONE_PRIVATE_CODE" not in str(observation)
        assert bundle(prepared, member)["files"]["sample.py"] == "value = 0\n"
        assert not accepted(call, member, "work_history_search", query="MEMBER_ONE_PRIVATE", limit=5)["matches"]
        assert not call(member, "read_alias", alias=MEMBERS[0])["ok"]


def test_task_offer_accept_remains_required_and_addressed(tmp_path):
    prepared, _, call, _, _ = prepare(tmp_path, "CHIEF")
    accepted(call, MEMBERS[1], "create_task", task_id="investigate", description="Member-created work")
    accepted(call, MEMBERS[1], "claim_task", task_id="investigate")
    accepted(call, MEMBERS[1], "send_message", recipient=MEMBERS[0], task_id="investigate", body="Please take responsibility")
    assert prepared.world._software()["tasks"]["investigate"]["owner"] == MEMBERS[1]
    assert not call(MEMBERS[1], "offer_transfer", task_id="investigate", to_member=MEMBERS[2], reason="illegal edge")["ok"]
    offer = accepted(call, MEMBERS[1], "offer_transfer", task_id="investigate", to_member=MEMBERS[0], reason="explicit offer")
    assert prepared.world._software()["tasks"]["investigate"]["owner"] == MEMBERS[1]
    assert not call(MEMBERS[2], "accept_transfer", offer_id=offer["offer_id"])["ok"]
    accepted(call, MEMBERS[0], "accept_transfer", offer_id=offer["offer_id"])
    assert prepared.world._software()["tasks"]["investigate"]["owner"] == MEMBERS[0]


def test_published_fixed_tree_keeps_harness_visibility_and_explicit_integration(tmp_path):
    prepared, ports, call, _, _ = prepare(tmp_path, "CHIEF")
    accepted(call, MEMBERS[1], "write_file", path="sample.py", text="published_value = 1\n")
    patch = accepted(call, MEMBERS[1], "fix_patch", task_ids=[], message="fixed immutable revision")
    accepted(call, MEMBERS[1], "write_file", path="sample.py", text="UNPUBLISHED_VALUE = 2\n")
    for member in (MEMBERS[0], MEMBERS[2]):
        published = accepted(call, member, "read_file", path="sample.py", patch_id=patch["patch_id"])
        assert "published_value = 1" in published["text"]
        assert "UNPUBLISHED_VALUE" not in str(published)
        assert bundle(prepared, member)["files"]["sample.py"] == "value = 0\n"
    assert not call(MEMBERS[1], "handoff_patch", patch_id=patch["patch_id"], to_member=MEMBERS[2], message="illegal edge")["ok"]
    accepted(call, MEMBERS[1], "handoff_patch", patch_id=patch["patch_id"], to_member=MEMBERS[0], message="explicit handoff")
    assert bundle(prepared, MEMBERS[0])["files"]["sample.py"] == "value = 0\n"
    accepted(call, MEMBERS[0], "integrate_patch", patch_id=patch["patch_id"])
    assert bundle(prepared, MEMBERS[0])["files"]["sample.py"] == "published_value = 1\n"
    assert "UNPUBLISHED_VALUE" not in str(ports[MEMBERS[0]].observe())
    # The existing public fixed-artifact channel is common to all groups.
    # Direct edge restrictions are not a new total information-flow ACL.
    accepted(call, MEMBERS[2], "integrate_patch", patch_id=patch["patch_id"])
    assert bundle(prepared, MEMBERS[2])["files"]["sample.py"] == "published_value = 1\n"


def test_each_public_test_binds_the_actual_member_and_version(tmp_path):
    prepared, _, call, tests, _ = prepare(tmp_path)
    for index, member in enumerate(MEMBERS[:2], 1):
        accepted(call, member, "write_file", path="sample.py", text=f"value = {index}\n")
        accepted(call, member, "run_tests")
    assert [row["files"]["sample.py"] for row in tests] == ["value = 1\n", "value = 2\n"]
    assert tests[0]["request"]["source_reference"] != tests[1]["request"]["source_reference"]
    assert prepared.world.test_budget.snapshot()["used"] == 2
    reports = prepared.world._software()["test_reports"]
    assert len(reports) == 2


@pytest.mark.parametrize("organization", ["DIALOGUE", "SOP"])
def test_smaller_rosters_preserve_private_history_public_fixed_versions_and_no_ghosts(tmp_path, organization):
    prepared, ports, call, _, _ = prepare(tmp_path, organization)
    members = tuple(prepared.case["active_roles"])
    accepted(call, members[0], "work_note", key="private", text="SMALL_TEAM_PRIVATE_NOTE")
    accepted(call, members[1], "write_file", path="sample.py", text="public_fixed = 1\n")
    assert bundle(prepared, members[0])["files"]["sample.py"] == "value = 0\n"
    published = accepted(call, members[1], "fix_patch", task_ids=[], message="actual published version")
    accepted(call, members[1], "write_file", path="sample.py", text="PRIVATE_LATER_VALUE = 99\n")
    for member in members:
        assert set(ports[member].observe()["fixed_organization"]["role_directory"]) == set(members)
        if member != members[0]:
            assert "SMALL_TEAM_PRIVATE_NOTE" not in str(ports[member].observe())
        assert "public_fixed = 1" in accepted(call, member, "read_file", path="sample.py",
                                               patch_id=published["patch_id"])["text"]
    accepted(call, members[0], "integrate_patch", patch_id=published["patch_id"])
    assert bundle(prepared, members[0])["files"]["sample.py"] == "public_fixed = 1\n"
    ghost = f"member_{len(members)+1:03d}"
    assert not call(members[0], "send_message", recipient=ghost, task_id="root_goal", body="No extra member")["ok"]
    with pytest.raises(ValueError):
        world.SoftwareCollaborationPort(prepared.world.session(ghost, world.PROJECT), ghost)
    assert tuple(prepared.world._software()["registry"]) == members


@pytest.mark.parametrize("organization", ["DIALOGUE", "COUNCIL", "PEER"])
def test_unique_delivery_member_and_last_legal_version_without_best_of_members(tmp_path, organization):
    prepared, _, call, tests, _ = prepare(tmp_path, organization)
    accepted(call, MEMBERS[0], "write_file", path="sample.py", text="value = 1\n")
    accepted(call, MEMBERS[0], "run_tests")
    accepted(call, MEMBERS[0], "fix_patch", task_ids=[], message="tested delivery version")
    accepted(call, MEMBERS[0], "submit_integration", message="one explicit legal submission")
    accepted(call, MEMBERS[0], "write_file", path="sample.py", text="value = 2\n")
    assert not call(MEMBERS[0], "submit_integration", message="stale evidence")["ok"]
    accepted(call, MEMBERS[1], "write_file", path="sample.py", text="value = 99\n")
    accepted(call, MEMBERS[1], "run_tests")
    accepted(call, MEMBERS[1], "fix_patch", task_ids=[], message="other member own version")
    assert not call(MEMBERS[1], "submit_integration", message="not the frozen delivery outlet")["ok"]
    before = copy.deepcopy(prepared.world._software())
    with pytest.raises(ValueError):
        runtime_module.lock_fixed_candidates(prepared, tmp_path / "too-early", sdk_closed=False)
    locked = runtime_module.lock_fixed_candidates(prepared, tmp_path / "closed", sdk_closed=True)
    candidates = read_episode_candidates(locked)
    assert candidates["terminal_code"]["files"]["sample.py"] == "value = 2\n"
    assert candidates["last_legal_delivery"]["files"]["sample.py"] == "value = 1\n"
    assert prepared.world._software()["case"] == before["case"]
    assert prepared.world._software()["registry"] == before["registry"]
    assert len(tests) == 2
    assert not call(MEMBERS[0], "write_file", path="sample.py", text="after closing")["ok"]


@pytest.mark.parametrize("member_count", [2, 3, 4])
def test_real_shared_budget_is_one_team_pool_including_failed_and_private_actions(member_count):
    members = MEMBERS[:member_count]
    # These counters are explicitly synthetic. The real budget object, rather
    # than four per-member copies, must deny the fifth aggregate request.
    budget = managed.ManagedTeamBudget(members=members, team_id="fixed-org-cpu-budget",
        max_decisions=8, max_attempts=8, max_total_tokens=80, require_exact_resident=False)
    for index in range(4):
        member = members[index % len(members)]
        call_id = f"decision-{index}"
        budget.consume_decision(member, call_id)
        budget.reserve(member, call_id, {"token_reservation": 20})
        budget.begin_attempt(member, call_id)
        budget.settle(member, call_id, {"id": f"programmed-{index}",
            "usage": {"prompt_tokens": 15, "completion_tokens": 5, "total_tokens": 20}})
    snapshot = budget.snapshot()
    assert snapshot["charged_tokens"] == 80 and snapshot["available_tokens"] == 0
    assert snapshot["attempts"] == snapshot["decisions"] == 4
    budget.consume_decision(MEMBERS[0], "fifth")
    with pytest.raises(V033PolicyBoundaryError):
        budget.reserve(MEMBERS[0], "fifth", {"token_reservation": 1})
    with pytest.raises(ValueError):
        budget.register_member("member_005")


@pytest.mark.parametrize("organization", ["DIALOGUE", "COUNCIL", "PEER"])
def test_runtime_assembly_uses_configured_private_sessions_and_one_bound_budget(tmp_path, organization):
    prepared, _, _, tests, deadline = prepare(tmp_path, organization)
    members = tuple(prepared.case["active_roles"])
    instances = []

    class InertWorker:
        def __init__(self, member, tools, config, **kwargs):
            self.member, self.config, self.kwargs = member, copy.deepcopy(config), kwargs
            instances.append(self)

        def step(self, *_args, **_kwargs):
            pytest.fail("Runtime construction cannot dispatch a model")

    adapter = SimpleNamespace(limits={"context_limit": 131072}, maximum_input_tokens=98304,
        maximum_output_tokens=32768, model="cpu-programmed-model", thinking=True,
        fixture_only=True, external_resources_enabled=False)
    owner = managed.ProjectOwner(adapter, window_id="cpu-fixed-org", identity={"policy_version": "programmed-cpu-only"})
    before = copy.deepcopy(prepared.world.store.load())
    runtime, _, _ = runtime_module.build_runtime(owner, prepared, tmp_path / "runtime", deadline=deadline,
        public_initial_message=prepared.case["root_goal"], worker_factory=InertWorker, offline_fixture=True)
    assert [worker.member for worker in instances] == list(members)
    assert len({id(worker.kwargs["team_budget"]) for worker in instances}) == 1
    assert runtime.team_budget.snapshot()["limits"]["max_total_tokens"] == 5_000_000
    assert len({str(worker.kwargs["directory"]) for worker in instances}) == len(members)
    assert len({id(runtime.ports[member]) for member in members}) == len(members)
    assert all(worker.kwargs["context_selection"] == "full_history" for worker in instances)
    assert all(worker.config["max_context_tokens"] == 131072 for worker in instances)
    assert all(worker.config["max_output_tokens"] == 32768 for worker in instances)
    assert all(worker.config["budget"]["max_total_tokens"] == 5_000_000 for worker in instances)
    assert before == prepared.world.store.load() and tests == []


def test_runtime_defaults_do_not_authorize_real_model_or_resource_dispatch(tmp_path):
    prepared, _, _, _, deadline = prepare(tmp_path)
    adapter = SimpleNamespace(limits={"context_limit": 131072}, maximum_input_tokens=98304,
        maximum_output_tokens=32768, model="inert", thinking=True)
    owner = managed.ProjectOwner(adapter, window_id="no-dispatch", identity={"policy_version": "not-a-model"})
    with pytest.raises(PermissionError, match="implementation-only"):
        runtime_module.build_runtime(owner, prepared, tmp_path / "default-denied", deadline=deadline,
            public_initial_message=prepared.case["root_goal"])
    with pytest.raises(PermissionError, match="implementation-only"):
        runtime_module.build_runtime(owner, prepared, tmp_path / "unmarked-adapter-denied", deadline=deadline,
            public_initial_message=prepared.case["root_goal"], offline_fixture=True)
    assert not (tmp_path / "default-denied").exists()
    assert not (tmp_path / "unmarked-adapter-denied").exists()


def test_existing_forbidden_controller_operation_retains_process_violation(tmp_path):
    prepared, _, _, _, _ = prepare(tmp_path)
    response = prepared.world.session(MEMBERS[0], world.PROJECT).call("controller_add_neutral_member")
    assert response["ok"] is False
    assert response["error"]["rejection"]["context"]["process_violation"] is True


def test_closed_candidates_remain_closed_after_reconstructing_the_world(tmp_path):
    prepared, _, _, _, _ = prepare(tmp_path)
    runtime_module.lock_fixed_candidates(prepared, tmp_path / "closed", sdk_closed=True)
    restored = world.SoftwareCollaborationWorld(tmp_path / "prepared/world")
    response = restored.session(MEMBERS[0], world.PROJECT).call(
        "write_file", path="sample.py", text="cannot revise the locked candidate\n")
    assert response["ok"] is False
    assert response["error"]["rejection"]["code"] == "fixed_candidates_closed"


def test_fixed_schedule_waits_without_synthetic_work_and_reopens_same_identity():
    from proworksim.software_fixed_organization_v065 import get_organization
    spec = get_organization("DIALOGUE")
    members = tuple(spec["fixed_members"])
    schedule = runtime_module.FixedPhaseSchedule(spec)
    emitted = []
    for _ in range(10):
        selected = schedule.choose(members)
        emitted.append(selected["member"])
        schedule.consume(selected)
    assert emitted[:8] == [MEMBERS[0], MEMBERS[1]] * 4
    assert emitted[8:] == [members[1], members[0]]
    before = schedule.snapshot()
    assert schedule.choose([]) is None
    assert schedule.snapshot()["executed_opportunities"] == before["executed_opportunities"]
    assert schedule.snapshot()["world_actions_created_by_scheduler"] == 0
    selected = schedule.choose([members[1]])
    assert selected["member"] == members[1]
    schedule.consume(selected)
    with pytest.raises(ValueError):
        schedule.consume(selected)
    with pytest.raises(ValueError):
        schedule.choose(["member_005"])
    with pytest.raises(ValueError):
        schedule.choose(["member_003"])


def inert_runtime(prepared, folder, deadline):
    class InertWorker:
        def __init__(self, member, _tools, config, **_kwargs):
            self.member, self.config, self._done, self.wakes = member, config, None, []

        def step(self, *_args, **_kwargs):
            pytest.fail("An inactive or expired fixture cannot dispatch")

        def wake_current_work(self, event_sequences):
            assert self._done and event_sequences
            self._done = None
            self.wakes.append(list(event_sequences))

    adapter = SimpleNamespace(limits={"context_limit": 131072}, maximum_input_tokens=98304,
        maximum_output_tokens=32768, model="inert-cpu-only", thinking=True,
        fixture_only=True, external_resources_enabled=False)
    owner = managed.ProjectOwner(adapter, window_id="inert-events", identity={"policy_version": "cpu-only"})
    return runtime_module.build_runtime(owner, prepared, folder, deadline=deadline,
        public_initial_message=prepared.case["root_goal"], worker_factory=InertWorker,
        offline_fixture=True)[0]


def test_only_real_visible_partner_event_wakes_same_session_without_budget_reset(tmp_path):
    prepared, _, _, _, deadline = prepare(tmp_path)
    runtime = inert_runtime(prepared, tmp_path / "runtime", deadline)
    member, sender, other = MEMBERS[:3]
    worker = runtime.policies[member]
    worker._done = "scripted current work ended"
    baseline_budget = runtime.team_budget.snapshot()
    runtime_module.base._sleep(runtime, member, "completed", {"reason": "programmed boundary"})
    runtime_module.base._wake_reachable(runtime)
    assert member in runtime.waiting and worker.wakes == []
    prepared.world.scheduled_member = sender
    try:
        response = prepared.world.session(sender, world.PROJECT).call(
            "write_file", path="sample.py", text="private other-member change\n")
        assert response["ok"]
        response = prepared.world.session(sender, world.PROJECT).call(
            "send_message", recipient=other, task_id="root_goal", body="addressed elsewhere")
        assert response["ok"]
        runtime_module.base._wake_reachable(runtime)
        assert member in runtime.waiting and worker.wakes == []
        response = prepared.world.session(sender, world.PROJECT).call(
            "send_message", recipient=member, task_id="root_goal", body="actual reachable work")
        assert response["ok"]
    finally:
        prepared.world.scheduled_member = None
    runtime_module.base._wake_reachable(runtime)
    assert member not in runtime.waiting and member not in runtime.work_ended
    assert runtime.policies[member] is worker and len(worker.wakes) == 1
    assert runtime.team_budget.snapshot() == baseline_budget
    assert tuple(prepared.world._software()["registry"]) == MEMBERS
    assert runtime.opportunities == runtime.actions == 0


def test_soft_and_hard_deadlines_prevent_new_work_without_consuming_calls(tmp_path):
    from proworksim.software_organization_runtime_v047 import HardDeadlineReached
    prepared, _, _, tests, deadline = prepare(tmp_path)
    runtime = inert_runtime(prepared, tmp_path / "runtime", deadline)
    deadline.clock = lambda: deadline.soft_at
    boundary = runtime_module.run_fragment(prepared, runtime)
    assert boundary["closure_reason"] == "administrative_soft_deadline"
    assert boundary["opportunities"] == 0
    assert runtime.team_budget.snapshot()["decisions"] == 0
    assert tests == []
    deadline.clock = lambda: deadline.hard_at
    with pytest.raises(HardDeadlineReached):
        runtime_module.run_fragment(prepared, runtime)
    assert runtime.team_budget.snapshot()["attempts"] == 0


def test_public_role_directory_and_closed_runtime_prevent_any_later_sampling(tmp_path):
    from proworksim.software_fixed_organization_v065 import get_organization
    prepared, ports, _, _, deadline = prepare(tmp_path, "CHIEF")
    expected_roles = get_organization("CHIEF")["roles"]
    for port in ports.values():
        directory = port.observe()["fixed_organization"]["role_directory"]
        assert set(directory) == set(MEMBERS)
        assert all(directory[member] == {"member_id": member, **expected_roles[member]} for member in MEMBERS)
    runtime = inert_runtime(prepared, tmp_path / "runtime", deadline)
    before = runtime.team_budget.snapshot()
    runtime_module.lock_fixed_candidates(prepared, tmp_path / "closed", sdk_closed=True)
    with pytest.raises(ValueError, match="unique candidate lock"):
        runtime.step()
    assert runtime.opportunities == 0 and runtime.team_budget.snapshot() == before
