"""Frozen finite development episodes; model failures are retained, never repaired."""

import argparse
import concurrent.futures
import copy
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.episode import begin_episode, finish_episode, assess_historical_episode
from proworksim.rewards import episode_reward
from proworksim.runtime import load_env
from proworksim.scenarios import build_scenario, bind_runtime, ScenarioController, run_scenario
from proworksim.storage import atomic_write, digest, json_bytes


def now():
    return datetime.now(timezone.utc).isoformat()


def resources():
    try:
        result = subprocess.run([
            'nvidia-smi', '--query-gpu=index,name,memory.used,memory.free,utilization.gpu',
            '--format=csv,noheader'], capture_output=True, text=True, timeout=10)
        return {'utc': now(), 'gpu': result.stdout, 'exit_code': result.returncode}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'utc': now(), 'unavailable': type(error).__name__}


def run_case(row, protocol, destination):
    folder = destination / row['episode_name']
    folder.mkdir()
    before = code_identity()
    started = now()
    backend = protocol['backends'][row['backend']]
    base = Path(row['scenario_file'])
    spec = json.loads(base.read_text())
    spec['boundary']['max_opportunities'] = protocol['max_environment_opportunities']
    roles = [r for r in spec['roles'] if r['role_id'] in row['target_roles']]
    if len(roles) != len(row['target_roles']):
        raise ValueError('Declared target roles absent from scenario')
    for role in roles:
        role['policy'] = 'model'
        role['config'] = copy.deepcopy(backend)
        role['config']['task'] = protocol['tasks'].get(role['role_id'], protocol['default_task'])
    atomic_write(folder / 'scenario.json', json_bytes(spec))
    record = {'episode_name': row['episode_name'], 'backend': row['backend'],
              'scenario': row['scenario'], 'repeat': row['repeat'],
              'target_roles': row['target_roles'], 'source_before': before, 'started_at': started,
              'resource_before': resources(), 'scenario_sha256': digest(json_bytes(spec)),
              'script_sha256': digest(Path(__file__).read_bytes())}
    runtime = None
    deployment = None
    captured = {}
    try:
        deployment = build_scenario(spec, folder / 'world')
        record['deployment_status'] = deployment.status
        if deployment.status != 'ready':
            record.update(status='unbuildable', diagnostics=deployment.diagnostics)
            return record
        runtime = bind_runtime(deployment, captured=captured)
        for label in row['target_roles']:
            runtime.policies[label].bind_audit_dir(folder / 'model-calls' / label)
        controller = ScenarioController(deployment, recorder=runtime.recorder)
        for entry in deployment.deployment_log:
            runtime.recorder.record('deployment_action', entry)
        if spec['start']['kind'] == 'executed_prefix' and not deployment.prefix['prefix_executed']:
            deployment.prepare_start(runtime, controller)
            atomic_write(folder / 'prefix.json', json_bytes(deployment.prefix))
            if deployment.status != 'ready':
                record.update(status='unbuildable', diagnostics=deployment.diagnostics)
                atomic_write(folder / 'interrupted-checkpoint.json', json_bytes(runtime.snapshot()))
                return record
        binding = {(r['actor'], r['project']) for r in roles}
        nodes = sorted({w['node_id'] for w in deployment.world.state['work_items'].values()
                        if (w['owner_role'], w['project_id']) in binding})
        assessment_spec = {'process_requirements': []}
        reward_spec = {'version': 'reward-spec-v0.11', 'reward_id': 'development-content-adoption-v011',
                       'objectives': [], 'process_requirements': []}
        for index, node in enumerate(nodes):
            item = next(w for w in deployment.world.state['work_items'].values() if w['node_id'] == node)
            aliases = sorted({source['alias'] for check in item['deliverable_contract'].get('content_checks', [])
                              for source in check.get('sources', [])})
            reward_spec['objectives'].append({'kind': 'content', 'work_node': node, 'weight': 1})
            if aliases:
                key = 'source-adoption-' + str(index)
                assessment_spec['process_requirements'].append({
                    'requirement_id': key, 'kind': 'required_source_adoption',
                    'work_node': node, 'aliases': aliases})
                reward_spec['process_requirements'].append(key)
        atomic_write(folder / 'assessment-spec.json', json_bytes(assessment_spec))
        atomic_write(folder / 'reward-spec.json', json_bytes(reward_spec))
        begin_episode(deployment.world, folder / 'episode', experience=runtime.recorder.snapshot(),
                      work_ids=[], work_nodes=nodes,
                      scenario={'spec': spec, 'sha256': record['scenario_sha256']},
                      policies=runtime.policy_identities)
        result = run_scenario(deployment, runtime, controller)
        boundary = {k: v for k, v in result.items()
                    if k not in {'worker_checkpoint', 'experience', 'controller', 'outcomes', 'prefix'}}
        manifest = finish_episode(deployment.world, folder / 'episode',
                                  experience=runtime.recorder.snapshot(), termination=boundary)
        atomic_write(folder / 'run.json', json_bytes(result))
        atomic_write(folder / 'public-capture.json', json_bytes(captured))
        assessment = assess_historical_episode(folder / 'episode', **assessment_spec)
        reward = episode_reward(assessment, reward_spec)
        atomic_write(folder / 'reward.json', json_bytes(reward))
        atomic_write(folder / 'assessment.json', json_bytes(assessment))
        recorder_events = runtime.recorder.events
        matches = {}
        for label, actual in captured.items():
            retained = [{'kind': e['kind'], 'payload': copy.deepcopy(e['payload'])}
                        for e in recorder_events if e.get('worker_id') == label
                        and e['kind'] in {'public_tools', 'public_observation', 'tool_call'}]
            # Model linkage is runtime metadata; the raw boundary captured no
            # such labels. Remove only these declared association fields.
            for event in retained:
                if event['kind'] == 'tool_call':
                    for key in ('model_call_id', 'model_tool_call_id', 'decision_id', 'opportunity_id'):
                        event['payload'].pop(key, None)
            matches[label] = actual == retained
        record.update(status=result['status'], boundary=boundary,
                      episode_id=manifest['episode_id'], fixed_deliveries=manifest['fixed_deliveries'],
                      public_capture_matches=matches,
                      reward=reward,
                      assessment_execution=assessment.get('assessment_execution'),
                      institutional_progress=assessment.get('institutional_progress'),
                      content_quality=assessment.get('content_quality'),
                      incompleteness=assessment.get('incompleteness'),
                      runtime_problems=assessment.get('runtime_problems'),
                      model_meters={label: runtime.roles[label]['memory'].get('meter', {})
                                    for label in row['target_roles']},
                      model_role_statuses={label: runtime.roles[label]['status'] for label in row['target_roles']},
                      tool_refusals=[e for e in recorder_events if e['kind'] == 'tool_call'
                                     and not e['payload'].get('response', {}).get('ok', False)],
                      model_boundaries=[e for e in recorder_events if e['kind'] == 'model_boundary_error'])
    except Exception as error:
        record.update(status='experiment_error', error={'type': type(error).__name__, 'message': str(error)})
        if runtime:
            atomic_write(folder / 'interrupted-checkpoint.json', json_bytes(runtime.snapshot()))
        # Open manifests/facts remain open, not backfilled as closed episodes.
    finally:
        atomic_write(folder / 'public-capture.json', json_bytes(captured))
        record.update(source_after=code_identity(), ended_at=now(), resource_after=resources())
        atomic_write(folder / 'record.json', json_bytes(record))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--env-file', default='.env')
    args = parser.parse_args()
    load_env(args.env_file)
    protocol_path = Path(args.protocol)
    protocol = json.loads(protocol_path.read_text())
    destination = Path(args.output)
    destination.mkdir(parents=True, exist_ok=False)
    atomic_write(destination / 'protocol.json', json_bytes(protocol))
    rows = protocol['episodes']
    if not rows or len({r['episode_name'] for r in rows}) != len(rows):
        raise ValueError('Explicit distinct episode inventory required')
    before = code_identity()
    report = {'protocol_sha256': digest(protocol_path.read_bytes()), 'source_before': before,
              'started_at': now(), 'resource_before': resources(), 'planned': len(rows), 'cases': [],
              'scope': protocol['scope']}
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_case, row, protocol, destination): row for row in rows}
        for future in concurrent.futures.as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {**row, 'status': 'experiment_error',
                          'error': {'type': type(error).__name__, 'message': str(error)}}
            report['cases'].append(result)
            atomic_write(destination / 'progress.json', json_bytes(report))
            print(json.dumps({k: result.get(k) for k in ('episode_name', 'status', 'model_meters')},
                             ensure_ascii=False), flush=True)
    report.update(source_after=code_identity(), ended_at=now(), elapsed_seconds=time.monotonic()-started,
                  resource_after=resources())
    report['status_counts'] = {status: sum(r['status'] == status for r in report['cases'])
                               for status in sorted({r['status'] for r in report['cases']})}
    atomic_write(destination / 'report.json', json_bytes(report))
    print(json.dumps({'finished': len(rows), 'status_counts': report['status_counts']}), flush=True)


if __name__ == '__main__':
    main()
