"""Actual CPU witnesses for the six independent harness-development situations."""
import argparse
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.online_collection import run_fragment
from proworksim.retail_rewards import assess_retail_reward
from proworksim.staff_runtime import StaffRuntime
from proworksim.storage import json_bytes
from proworksim.templates.retail_harness import build_harness_case, registry
from proworksim.work_interface import WorkInterface
from scripts.retail_work_experiment_v015 import PublicWitnessPolicy


def run_case(case_id, output, *, communication="proactive", control=None, variant="v14"):
    output = Path(output)
    prepared = build_harness_case(case_id, output)
    captures, ports, policies = {}, {}, {}
    for role in prepared.active_roles:
        ports[role] = capture_port(WorkInterface(prepared.world.session(role, "TEAM"), role, variant=variant), captures.setdefault(role, []))
        policies[role] = PublicWitnessPolicy(role=role, task=prepared.case["task"],
                                           limit=prepared.case["role_decision_limits"][role],
                                           communication=communication, control=control)
    runtime = StaffRuntime(ports, policies, recorder=ExperienceRecorder())
    episode = output / "episode"
    begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), work_ids=["TEAM::build"],
                  scenario=prepared.scenario, policies=runtime.policy_identities)
    boundary = run_fragment(prepared, runtime)
    finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
    reward = assess_retail_reward(episode, prepared.reward_spec)
    decisions = {role: runtime.roles[role]["memory"].get("decisions", 0) for role in runtime.labels}
    waits = {role: sum(event["kind"] == "policy_decision" and event.get("worker_id") == role
                      and event["payload"]["decision"]["kind"] == "wait" for event in runtime.recorder.events)
             for role in runtime.labels}
    report = {"case_id": case_id, "communication": communication, "control": control,
              "origin": "cpu_public_rule_witness_not_model", "source": code_identity(), "reward": reward,
              "boundary": boundary, "decisions_including_wait_done": decisions, "waits": waits,
              "role_limits": prepared.case["role_decision_limits"], "current_episode_excludes_prefix": True}
    (output / "capture.json").write_bytes(json_bytes(captures))
    (output / "runtime.json").write_bytes(json_bytes(runtime.snapshot()))
    (output / "reward.json").write_bytes(json_bytes(reward))
    (output / "report.json").write_bytes(json_bytes(report))
    return report



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cases = []
    for case in registry()['situations']:
        row = run_case(case['case_id'], args.output / case['case_id'])
        cases.append({'case_id': case['case_id'], 'reward': row['reward']['reward'],
                      'completed': row['reward']['completed'],
                      'decisions': row['decisions_including_wait_done'],
                      'passed': row['reward']['reward'] == 1})
    controls = []
    for case_id, control, expected in [
        ('uci-harness-f0-implement', 'wrong_sql', 0.2),
        ('uci-harness-f3-review', 'bad_approval', 0.25),
        ('uci-harness-f3-review', 'wrong_location', 0.25),
    ]:
        row = run_case(case_id, args.output / (case_id + '-' + control), control=control)
        controls.append({'case_id': case_id, 'control': control, 'reward': row['reward']['reward'],
                         'expected': expected, 'passed': row['reward']['reward'] == expected})
    report = {'version': 'retail-harness-feasibility-v0.16', 'model_execution': False,
              'cases': cases, 'negative_controls': controls,
              'passed': all(row['passed'] for row in cases + controls),
              'scope': 'CPU public-rule witnesses in six new development worlds. No model, training, independent-source or locked evaluation claim.'}
    (args.output / 'report.json').write_bytes(json_bytes(report))
    print({'passed': report['passed'], 'cases': len(cases), 'controls': len(controls)})


if __name__ == '__main__':
    main()
