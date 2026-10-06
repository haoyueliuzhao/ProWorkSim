"""Small P2 freeze/report controls; no repeated model or controller qualification."""
import copy
import os
from pathlib import Path

import pytest

from proworksim.software_collaboration_v035 import case_spec
from proworksim.software_mapper_v035 import mapping_spec
from proworksim.software_runtime_v035 import window_spec
from proworksim.software_training_v035 import source_training_admission
from scripts import software_support_v035 as runner
from scripts.run_ne_v021 import write


@pytest.fixture
def plan():
    rows = runner.inventories()
    return {"version": runner.VERSION, "candidate_id": runner.CANDIDATE,
        "inventories": rows, "cases": {r['case_id']:case_spec(r['case_id'],first_member='member_a')
                                      for group in rows.values() for r in group},
        "mapper_specification":mapping_spec(), "policy":copy.deepcopy(runner.POLICY),
        "support_window_id":runner.SUPPORT_WINDOW,"frozen_sampling_slots":16,
        "future_panels_frozen_before_support":True,"future_panels_executable_during_P2":False,
        "limits":copy.deepcopy(runner.LIMITS),"gpu_preference":runner.GPU_ORDER,
        "team_limits":runner.TEAM_LIMITS,"generation_limits":runner.GENERATION_LIMITS,
        "optimizer_updates_during_P2":0,"fresh_technical_quiz_calls":0,"repeat_near_16k_stress":False,
        "automatic_retries":False,"automatic_successors":[],"automatic_unfrozen_P3":False,
        "total_gpu_seconds":None,"worker_gpu_seconds":None,"queue_deadline_at":None,"wall_deadline_at":None,
        "historical_results_reclassified":False,"historical_gpu_costs_included_as_new":False,
        "source":{"code_commit":"explicit-cpu-fixture","code_dirty":False},
        "parent":{"common_actor_identity":{"fixture":"common3"}},"scope":"Explicit CPU fixture"}


def test_exact_sixteen_and_distinct_future_panels_are_frozen_before_collection(plan):
    assert runner.validate_plan(plan,check_files=False) is plan
    rows=plan['inventories']
    assert {key:len(v) for key,v in rows.items()}=={'support':16,'development':4,'confirmation':4}
    assert [r['sampling_seed'] for r in rows['support']]==list(range(202610060801,202610060817))
    assert len({(r['case_id'],r['first_member']) for r in rows['support']})==1
    for name,seeds in (('development',runner.DEVELOPMENT_SEEDS),('confirmation',runner.CONFIRMATION_SEEDS)):
        assert [r['sampling_seed'] for r in rows[name]]==[seeds[0],seeds[0],seeds[1],seeds[1]]
        assert rows[name][0]['case_id']==rows[name][2]['case_id']
        assert rows[name][1]['case_id']==rows[name][3]['case_id']
    for change in ({'frozen_sampling_slots':8},{'automatic_unfrozen_P3':True},
                   {'future_panels_executable_during_P2':True},{'optimizer_updates_during_P2':1}):
        with pytest.raises(ValueError,match='sixteen-slot'):
            runner.validate_plan({**plan,**change},check_files=False)


def test_runtime_and_exporter_cannot_relabel_source_purposes(plan):
    for name,usage,mode in (('support','policy_training','current_policy_collection'),
                           ('development','contribution_development','frozen_development'),
                           ('confirmation','independent_confirmation','frozen_evaluation')):
        rows=plan['inventories'][name]
        spec=window_spec('cpu-'+name,rows,usage)
        assert spec['mode']==mode and spec['budget']['max_slots']==len(rows)
        case=case_spec(rows[0]['case_id'])
        gamma={'source_usage':usage,'collection_mode':mode,'optimizer_update_allowed':usage=='policy_training',
               'mapper_specification':mapping_spec()}
        scope=source_training_admission(case,gamma)
        assert scope['optimizer_update_allowed'] is (name=='support')
        if name!='support':
            with pytest.raises(ValueError):
                window_spec('bad',rows,'policy_training')
            with pytest.raises(ValueError):
                source_training_admission(case,{**gamma,'optimizer_update_allowed':True})
    mixed=copy.deepcopy(plan['inventories']['support'])
    mixed[-1]['first_member']='member_b'
    with pytest.raises(ValueError,match='exact root'):
        window_spec('mixed',mixed,'policy_training')


def test_missing_or_interrupted_slots_keep_sixteen_positions_without_fake_rewards(plan):
    decl={'slots':[{'slot_id':r['slot_id'],'active_members':['member_a','member_b']}
                   for r in plan['inventories']['support']]}
    first=decl['slots'][0]['slot_id']
    entry={'slot_id':first,'active_members':['member_a','member_b'],'rollout':{'fixture':True},'reward':{'reward':0}}
    entries,records=runner.retained_inventory([entry],[{'slot_id':first,'status':'closed'}],decl,
                                            [{'slot_id':first,'status':'execution_unknown'}])
    assert len(entries)==len(records)==16
    assert entries[0] is entry and records[0]['status']=='execution_unknown'
    assert all(e['rollout'] is None and e['reward'] is None for e in entries[1:])
    assert all(r['status']=='not_started' for r in records[1:])


def test_pending_or_failed_report_never_executes_P3_or_fills_unknown(tmp_path,plan):
    write(tmp_path/'plan.json',plan)
    for status in ('not_started','stopped'):
        write(tmp_path/'supervisor.json',{'status':'waiting' if status=='not_started' else 'interrupted',
            'started_at':0,'states':{runner.CANDIDATE:{'status':status,'attempted':False}},'running_gpu_seconds':0})
        result=runner.report(tmp_path,tmp_path/'published')
        assert len(result['rows'])==16 and result['known_results']==0
        assert all(row['R'] is None for row in result['rows'])
        assert all(row['training_eligible'] is None for row in result['rows'])
        assert not result['next_stage']['automatic_execution'] and not result['next_stage']['P3_started']
        assert result['cost']['historical_costs_added'] is False
        assert result['next_stage']['status']==('collecting_fixed_inventory' if status=='not_started' else 'technical_unknown_no_support_freeze')
    assert runner.REPORT_PATHS==['docs/experiments/software-support-v035.md','docs/experiments/software-support-v035.json']


def test_complete_report_preserves_training_purpose_and_requires_known_usage(tmp_path, plan):
    write(tmp_path / "plan.json", plan)
    write(tmp_path / "supervisor.json", {"status": "complete", "started_at": 0,
        "states": {runner.CANDIDATE: {"status": "complete", "attempted": False}}})
    actual = tmp_path / runner.CANDIDATE / "actual"
    rows = [{**row, "status": "closed", "record_validity": True, "R": 0,
        "complete_delivery": False, "submitted": False, "training_eligible": True,
        "mapping_status": "unmapped", "method_class": None,
        "team_budget": {"model": {"decisions": 2, "attempts": 2, "charged_tokens": 20, "held_tokens": 0},
                        "tests": {"used": 0}}} for row in plan["inventories"]["support"]]
    write(actual / "collection/progress.json", rows)
    write(actual / "report.json", {"status": "complete", "common_restored_exactly": True,
        "execution_binding_passed": True, "source_before": plan["source"], "source_after": plan["source"],
        "initial_actor_steps": 3, "initial_critic_steps": 3, "actor_steps": 3, "critic_steps": 3,
        "final_actor_identity": plan["parent"]["common_actor_identity"],
        "new_actor_optimizer_steps": 0, "new_critic_optimizer_steps": 0})
    write(actual / "training-material-binding.json", {key: None for key in (
        "original_slot_count", "admitted_decisions", "admitted_input_tokens", "admitted_own_output_tokens",
        "maximum_actual_sequence_tokens", "sum_actual_sequence_tokens", "by_member", "exclusion_counts", "normalization")})
    write(actual / "support-gate.json", {"status": "no_configurable_support"})
    result = runner.results(plan, tmp_path)
    assert result["known_results"] == 16 and result["sampling_usage"]["known_usage_slots"] == 16
    assert result["worker_trusted_and_common_restored"] is True
    assert all(row["training_eligible"] is True for row in result["rows"])
    assert result["next_stage"]["status"] == "finite_window_no_configurable_support"
    rows[-1]["team_budget"]["model"]["charged_tokens"] = None
    write(actual / "collection/progress.json", rows)
    result = runner.results(plan, tmp_path)
    assert result["known_results"] == 16 and result["sampling_usage"]["known_usage_slots"] == 15
    assert result["worker_trusted_and_common_restored"] is False
    assert result["next_stage"]["status"] == "technical_unknown_no_support_freeze"


def test_actual_collector_exporter_binds_source_purpose_mapper_and_own_tokens(tmp_path, plan):
    pytest.importorskip("openhands.sdk")
    from proworksim.software_context_v034 import SoftwareContextTransport
    from proworksim.software_runtime_v035 import collect_software_window
    from proworksim.storage import read_json
    from proworksim.team_rollout import optimizer_scope_allows_update
    from test_software_v033 import ScriptedCPUOwner

    root = Path(os.environ.get("PROWORKSIM_V035_RUNNER_CONTROL", str(tmp_path)))
    proofs = []
    for name, usage in (("support", "policy_training"), ("development", "contribution_development"),
                        ("confirmation", "independent_confirmation")):
        folder = root / ("collector-" + name)
        owner = ScriptedCPUOwner(folder / "unused-old-projection")
        owner.window_id = "explicit-v035-scripted-cpu-" + name
        owner.facade.transport = SoftwareContextTransport(owner, folder / "slot-0/raw-transport/context-projections")
        entries = collect_software_window(owner.facade,
            window_spec(owner.window_id, plan["inventories"][name][:1], usage), folder)
        assert len(entries) == 1 and len(owner.requests) == 2
        entry = entries[0]
        assert entry["reward"]["eligible"] is True and entry["reward"]["reward"] == 0
        assert entry["training_eligible"] is (name == "support")
        assert optimizer_scope_allows_update(entry["rollout"]) is (name == "support")
        assert entry["mapping"]["status"] == "unmapped"
        assert entry["rollout"]["work_validity"]["components"]["record"]["value"] is True
        evidence = read_json(folder / "slot-0/software-evidence.json")
        assert evidence["binding_matches_views"] is True
        assert all(view["own_action_tokens"] == 1 for view in evidence["member_views"].values())
        responses = [event["payload"]["response"] for event in entry["rollout"]["events"]
                     if event["kind"] == "model_response"]
        assert len(responses) == 2 and all(row["token_trace"]["output_ids"] == [7] for row in responses)
        progress = read_json(folder / "progress.json")
        assert len(progress) == 1 and progress[0]["status"] == "closed"
        assert progress[0]["mapping_status"] == "unmapped"
        assert read_json(folder / "summary.json")["optimizer_updates_executed_during_collection"] == 0
        guard = read_json(folder / "slot-0/evaluation-guard.json")
        assert guard["learning_unchanged"] is guard["rng_restored_exactly"] is True
        proofs.append({"source_purpose": usage, "synthetic_responses": 2, "own_output_tokens": 2,
                       "R": 0, "mapping_status": "unmapped", "record_validity": True,
                       "source_training_admission": name == "support", "optimizer_updates": 0})
    write(root / "collector-proof.json", {"passed": True, "target_model_calls": 0,
        "scripted_cpu_responses": 6, "gpu_used": False, "optimizer_updates": 0, "windows": proofs,
        "scope": "Real SDK/archive/exporter/Mapper glue with explicit synthetic staff_done responses. No model is constructed or sampled; no solution program, current-policy support or trainable real-model material is claimed."})
