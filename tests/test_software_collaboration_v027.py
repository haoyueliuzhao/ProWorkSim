"""CPU interface witnesses and adverse controls, never model support."""

from concurrent.futures import ThreadPoolExecutor
import copy
import json
import sys

import pytest

from proworksim.software_collaboration_v027 import (
    CASE_IDS, MEMBERS, PROJECT, SoftwareCollaborationPort, SoftwareCollaborationWorld,
    assess_software_collaboration, build_software_collaboration_case,
    software_collaboration_facts,
)
from proworksim.software_sandbox import run_isolated
from proworksim.experience import capture_port
from proworksim.staff_runtime import StaffRuntime
from proworksim.templates.software_maintenance import ASSETS

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Frozen execution boundary requires Linux")
PATCHES = json.loads((ASSETS / "private/reference-patch.json").read_text())


def setup_case(tmp_path, case_id=CASE_IDS[0]):
    prepared = build_software_collaboration_case(case_id, tmp_path / "case")
    ports = [SoftwareCollaborationPort(prepared.world.session(member, PROJECT), member) for member in MEMBERS]
    return prepared, *ports


def call(port, action, **kwargs):
    value = port.call(action, **kwargs)
    assert value["ok"], value
    return value["result"]


def apply(port, *patches):
    for patch in patches:
        call(port, "replace_file", **patch)


def published(port, task_ids):
    return call(port, "fix_patch", task_ids=task_ids, message="CPU development witness")["patch_id"]


def test_atomic_claim_transfer_and_immutable_original_attribution(tmp_path):
    prepared, a, b = setup_case(tmp_path)
    world_root = prepared.world.store.root

    def claim(member):
        world = SoftwareCollaborationWorld(world_root)
        return member, world.session(member, PROJECT).call("claim_task", task_id="string_api", request_key="atomic")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, MEMBERS))
    assert sum(result["ok"] for _, result in results) == 1
    winner = next(member for member, result in results if result["ok"])
    other = next(member for member in MEMBERS if member != winner)
    owner = a if winner == MEMBERS[0] else b
    earlier = copy.deepcopy(software_collaboration_facts(prepared)["events"])
    call(owner, "delegate_task", task_id="string_api", to_member=other)
    facts = software_collaboration_facts(prepared.world.store.load())
    assert facts["events"][:len(earlier)] == earlier
    assert earlier[-1]["actor_id"] == winner
    assert facts["tasks"]["string_api"]["owner"] == other
    # Same command replay cannot reclaim or create a new claim after transfer.
    repeated = SoftwareCollaborationWorld(world_root).session(winner, PROJECT).call(
        "claim_task", task_id="string_api", request_key="atomic")
    assert repeated["ok"]
    assert software_collaboration_facts(prepared)["tasks"]["string_api"]["owner"] == other
    for event in facts["events"]:
        receipt = prepared.world.store.load()["operation_commits"][event["operation_id"]]
        assert receipt["public_result"]["action_id"] == event["action_id"]


def test_workspaces_are_private_and_generic_mutation_cannot_escape(tmp_path):
    prepared, a, b = setup_case(tmp_path)
    apply(a, PATCHES[1])
    assert "strip_whitespace" not in call(b, "read_file", path="consumer.py", start_line=1, max_lines=30)["text"]
    private = a.observe()["workspace_reference"]
    with pytest.raises(ValueError, match="not shared"):
        prepared.world._object(MEMBERS[1], PROJECT, object_id=private["object_id"], version_id=private["version_id"])
    assert not b.call("write_object", object_id=private["object_id"], data={})["ok"]
    for path in ("../../.env", "/etc/passwd", "private/casefold-acceptance.json", "test_visible.py"):
        assert not a.call("write_file", path=path, text="pass")["ok"]
    assert not a.call("run_tests", command="echo passed")["ok"]
    with pytest.raises(ValueError, match="identity"):
        SoftwareCollaborationPort(prepared.world.session(MEMBERS[0], PROJECT), MEMBERS[1])


def test_real_api_dependency_and_fixed_delivery_survives_later_edits(tmp_path):
    prepared, a, b = setup_case(tmp_path)
    call(a, "claim_task", task_id="string_api")
    call(b, "claim_task", task_id="inventory_consumer")
    call(b, "declare_dependency", task_id="inventory_consumer", depends_on="string_api")
    assert not a.call("declare_dependency", task_id="string_api", depends_on="inventory_consumer")["ok"]
    apply(b, PATCHES[1])
    assert not b.call("fix_patch", task_ids=["inventory_consumer"], message="missing upstream")["ok"]
    consumer_only = call(b, "run_tests")
    assert consumer_only["executed"] and consumer_only["returncode"] != 0
    assert "strip_whitespace" in consumer_only["output"]
    apply(a, PATCHES[0])
    upstream = published(a, ["string_api"])
    call(a, "handoff_patch", patch_id=upstream, to_member=MEMBERS[1], message="Library API implementation")
    merged = call(b, "integrate_patch", patch_id=upstream)
    assert merged["status"] == "merged" and not merged["conflicts"]
    published(b, ["inventory_consumer"])
    tests = call(b, "run_tests")
    assert tests["driver_completed"] and tests["returncode"] == 0
    submitted = call(b, "submit_integration", message="Integrated API and consumer")
    apply(b, {"path": "consumer.py", "old": "strip_whitespace=True", "new": "strip_whitespace=False"})
    assert not b.call("submit_integration", message="Stale test cannot cover this edit")["ok"]
    judgment = assess_software_collaboration(prepared, run_root=tmp_path / "acceptance")
    assert judgment["R"] == 1 and judgment["delivery"]["source_reference"] == submitted["source_reference"]
    assert judgment["independent_acceptance"]["passed_case_count"] == 29
    assert judgment["training_eligible"] is False
    facts = software_collaboration_facts(prepared)
    assert next(event for event in facts["events"] if event["kind"] == "integrate")["input_reference"] == facts["patches"][upstream]["source_reference"]
    assert facts["deliveries"][-1]["test_sequence"] == next(
        event["sequence"] for event in facts["events"] if event["kind"] == "test" and event["source_reference"] == submitted["source_reference"])


def _casefold_only():
    source = PATCHES[0]["new"]
    return source.replace("strip_whitespace", "casefold").replace("Remove leading and trailing whitespace", "Casefold Unicode text").replace("text.strip()", "text.casefold()")


def _combined():
    return (PATCHES[0]["new"].replace("strip_whitespace: bool = False, **kwargs", "strip_whitespace: bool = False, casefold: bool = False, **kwargs")
            .replace("self.strip_whitespace = strip_whitespace", "self.strip_whitespace = strip_whitespace\n        self.casefold = casefold")
            .replace("return text.strip() if self.strip_whitespace else text", "text = text.strip() if self.strip_whitespace else text\n            return text.casefold() if self.casefold else text")
            .replace("    :param kwargs:", "    :param casefold: Casefold Unicode text when loading. Defaults to False.\n    :param kwargs:"))


def test_independent_features_do_not_imply_merged_success_and_conflicts_need_repair(tmp_path):
    prepared, a, b = setup_case(tmp_path, CASE_IDS[1])
    call(a, "claim_task", task_id="whitespace")
    call(b, "claim_task", task_id="casefold")
    apply(a, *PATCHES)
    apply(b, {**PATCHES[0], "new": _casefold_only()})
    pa, pb = published(a, ["whitespace"]), published(b, ["casefold"])
    # Separate feature controls really run; neither is the full combined gate.
    for member, code in ((MEMBERS[0], "assert fields.String(strip_whitespace=True).deserialize(' X ') == 'X'"),
                         (MEMBERS[1], "assert fields.String(casefold=True).deserialize(' Straße ') == ' strasse '")):
        _, _, bundle = prepared.world._bundle(member)
        result = run_isolated(bundle["files"], "from marshmallow import fields\n" + code, run_root=tmp_path / member)
        assert result["executed"] and result["driver_completed"] and result["returncode"] == 0
    merge = call(a, "integrate_patch", patch_id=pb)
    assert merge["status"] == "conflict_markers_written"
    assert merge["conflicts"] == ["src/marshmallow/fields.py"]
    assert not a.call("integrate_patch", patch_id=pb)["ok"]
    published(a, ["whitespace"])
    assert call(a, "run_tests")["returncode"] != 0
    call(a, "submit_integration", message="Known broken integration control")
    assert assess_software_collaboration(prepared, run_root=tmp_path / "broken")["R"] == 0
    # Controller witness supplies the joint implementation explicitly; the world
    # never chooses this code or resolves a merge on behalf of the members.
    _, _, original = prepared.world._bundle(MEMBERS[0], baseline=True)
    fixed = original["files"]["src/marshmallow/fields.py"].replace(PATCHES[0]["old"], _combined())
    call(a, "write_file", path="src/marshmallow/fields.py", text=fixed)
    published(a, ["whitespace"])
    assert call(a, "run_tests")["returncode"] == 0
    call(a, "submit_integration", message="Both features with resolved integration")
    result = assess_software_collaboration(prepared, run_root=tmp_path / "combined")
    assert result["R"] == 1
    assert result["independent_acceptance"]["passed_case_count"] == 37
    events = software_collaboration_facts(prepared)["events"]
    merge_event = next(event for event in events if event["kind"] == "integrate")
    assert any(event["kind"] == "edit" and event["sequence"] > merge_event["sequence"] for event in events)
    assert pa != pb and result["delivery"]["included_patch_ids"] == [pb]


def test_false_visible_test_success_has_no_parent_acceptance_authority(tmp_path):
    prepared, a, _ = setup_case(tmp_path)
    call(a, "claim_task", task_id="string_api")
    payload = ("import abc\nimport unittest as _ut\nfrom types import SimpleNamespace as _NS\n"
               "_ut.main = lambda *a, **k: _NS(result=_NS(wasSuccessful=lambda: True))\n")
    call(a, "replace_file", path="src/marshmallow/fields.py", old="import abc\n", new=payload)
    published(a, ["string_api"])
    report = call(a, "run_tests")
    assert report["executed"] and report["driver_completed"] and report["returncode"] == 0
    call(a, "submit_integration", message="Forged unittest success control")
    result = assess_software_collaboration(prepared, run_root=tmp_path / "independent")
    assert result["R"] == 0
    assert result["independent_acceptance"]["expected_values_sent_to_worker"] is False


def test_member_test_cannot_access_partner_files_or_host(tmp_path):
    prepared, a, b = setup_case(tmp_path)
    apply(a, *PATCHES)
    apply(b, PATCHES[1])
    canary = tmp_path / "host-secret"
    canary.write_text("host only")
    artifact, version, _ = prepared.world._bundle(MEMBERS[1])
    other_path = str(prepared.world.store.version_path(artifact, version).resolve())
    code = f'''import socket, subprocess
for operation in (lambda: open({str(canary)!r}).read(), lambda: open({other_path!r}).read(),
                  lambda: open('consumer.py', 'w'), lambda: socket.socket(),
                  lambda: subprocess.run(['/bin/true'])):
    try:
        operation()
    except PermissionError:
        pass
    else:
        raise AssertionError('isolation failed')
'''
    call(a, "write_file", path="test_member.py", text=code)
    result = call(a, "run_tests")
    assert result["driver_completed"] and result["returncode"] == 0
    assert canary.read_text() == "host only"


def test_existing_runtime_and_raw_capture_keep_stable_member_binding(tmp_path):
    prepared, a, b = setup_case(tmp_path)

    class ClaimPolicy:
        def __init__(self, task_id):
            self.task_id = task_id

        def decide(self, context):
            assert context["observation"]["actor_id"] == context["worker_id"]
            return {"kind": "act", "action": "claim_task", "arguments": {"task_id": self.task_id}, "memory": {}}

    captures = {member: [] for member in MEMBERS}
    runtime = StaffRuntime({member: capture_port(port, captures[member]) for member, port in zip(MEMBERS, (a, b), strict=True)},
                           {MEMBERS[0]: ClaimPolicy("string_api"), MEMBERS[1]: ClaimPolicy("inventory_consumer")})
    for _ in MEMBERS:
        assert runtime.step()["status"] == "running"
    facts = software_collaboration_facts(prepared)
    assert [event["actor_id"] for event in facts["events"]] == list(MEMBERS)
    for member in MEMBERS:
        assert runtime.roles[member]["identity"]["actor_id"] == member
        assert captures[member]
