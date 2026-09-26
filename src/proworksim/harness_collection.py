"""Fixed-weight native/SDK development collection; original v15 runs unchanged."""
import copy
import time
from pathlib import Path

from .audit import code_identity
from .episode import begin_episode, finish_episode
from .experience import ExperienceRecorder, capture_port
from .harness_port import HarnessPort
from .harness_runtime import SDKStaffRuntime
from .information_mapper import information_graph, map_joint_method
from .model_policy import ModelPolicy
from .online_collection import _config, run_fragment, MAPPER
from .online_support import declare_window, expected_window, export_online_rollout, diagnose_window
from .staff_runtime import StaffRuntime
from .storage import atomic_write, digest, json_bytes
from .templates.retail_harness import build_harness_case, case_spec
from .work_interface import WorkInterface

VERSION = 'harness-collection-v0.16'


def _runtime(owner, prepared, folder, harness):
    recorder = ExperienceRecorder()
    captured, policies, ports, interfaces = {}, {}, {}, {}
    holder = {}
    for role in prepared.scenario['roles']:
        label = role['role_id']
        interface = WorkInterface(prepared.world.session(role['actor'], role['project']), label,
            audit_dir=folder/'public-projections'/label, variant='v14', presentation='compact_v14')
        interfaces[label] = interface
        base = capture_port(interface, captured.setdefault(label, []))
        config = _config(owner, label, role['config']['task'], prepared.case['role_decision_limits'])
        if harness == 'native_v15':
            ports[label] = base
            policies[label] = ModelPolicy(config, transport=owner.transport, audit_dir=folder/'model-calls'/label)
        elif harness == 'openhands_v16':
            from .harness_sdk import HarnessWorker
            config['context_policy'] = 'full_history'  # SDK event history; explicit request projection is separate.
            ports[label] = HarnessPort(base, label, project_id=role['project'],
                public_sink=lambda kind, value, label=label: recorder.record(kind, value, worker_id=label),
                world_sink=lambda payload, association, label=label: holder['runtime'].record_world_call(label, payload, association),
                harness_sink=lambda payload, association, label=label: holder['runtime'].record_harness_call(label, payload, association))
            policies[label] = HarnessWorker(label, ports[label].tools(), config,
                transport=owner.transport,
                execute=lambda name, arguments, association, label=label: holder['runtime'].execute(label, name, arguments, association),
                event_sink=lambda kind, value, label=label: recorder.record(kind, value, worker_id=label),
                directory=folder/'sdk-conversations'/label)
        else:
            raise ValueError('Unknown frozen harness condition')
        role.update(policy='model', config=copy.deepcopy(policies[label].config))
    runtime = SDKStaffRuntime(ports, policies, recorder=recorder) if harness == 'openhands_v16' else StaffRuntime(ports, policies, recorder=recorder)
    holder['runtime'] = runtime
    # Initial SDK metadata construction is outside actor work. No world tool or
    # model call is allowed during this construction; SDK keeps its own init log.
    if any(e['kind'] in {'model_call', 'tool_call'} for e in recorder.events):
        raise ValueError('Harness initialization must not sample or act')
    recorder.events.clear()
    for rows in captured.values():
        rows.clear()
    return runtime, captured, interfaces


def collect_window(owner, window_spec, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    atomic_write(output/'window-spec.json', json_bytes(window_spec))
    harness = window_spec['harness']
    if not window_spec.get('slots'):
        raise ValueError('Predeclare the finite collection slots')
    identity = owner.freeze_identity()
    prepared_rows, specs = [], []
    for index, row in enumerate(window_spec['slots']):
        case = case_spec(row['case_id'])
        # Public compatibility instructions/limits are frozen in H0, never
        # applied as hidden help to H1 or copied into the old study.
        if row.get('role_decision_limits') and row['role_decision_limits'] != case['role_decision_limits']:
            raise ValueError('Case responsibility budgets remain frozen in the independent catalog')
        folder = output/f'slot-{index}'
        prepared = build_harness_case(case, folder)
        if row.get('public_task_override'):
            for role in prepared.scenario['roles']:
                role['config']['task'] = row['public_task_override']
        runtime, captured, interfaces = _runtime(owner, prepared, folder, harness)
        scenario = copy.deepcopy(prepared.scenario)
        scenario['variation']['harness'] = {'version': VERSION, 'condition': harness,
            'stage': window_spec['stage'], 'purpose': row.get('purpose', 'development_work'),
            'interface': 'v14', 'presentation': 'compact_v14',
            'profile_bindings': {k: v.profile for k, v in interfaces.items()}}
        scenario['variation']['online_collection'] = {'interface': 'work-interface-v0.14', 'presentation': 'compact_v14',
            'role_profile_binding': {k: v.profile for k, v in interfaces.items()},
            'external_tick_per_sweep': 1, 'harness': harness}
        initial = {'case': prepared.case, 'reward_spec': prepared.reward_spec,
                   'initial_business_sha256': prepared.prefix['prepared_business_state_sha256']}
        specs.append({'slot_id': row['slot_id'], 'xi_id': case['case_id'],
                      'xi_fingerprint': digest(json_bytes(initial)), 'active_members': list(prepared.active_roles),
                      'policies': runtime.policy_identities, 'mapping_spec_id': MAPPER})
        atomic_write(folder/'model-scenario.json', json_bytes(scenario))
        prepared_rows.append((row, prepared, folder, runtime, captured, scenario))
    declaration = declare_window(window_spec['window_id'], actor_identity=identity,
        gamma_identity={'collection_version': VERSION, 'harness': harness, 'source': code_identity(),
            'recipe': owner.recipe, 'fixed_slot_cases': [s['xi_fingerprint'] for s in specs],
            'slot_sampling_seeds': {r['slot_id']: r['sampling_seed'] for r in window_spec['slots']},
            'context_projection': 'latest_observation_last4_tool_rounds' if harness == 'openhands_v16' else 'latest_observation',
            'external_tick_per_sweep': 1, 'transport_kind': 'resident_direct'},
        slot_specs=specs, min_class_count=2)
    atomic_write(output/'declaration.json', json_bytes(declaration))
    entries, records, summaries = [], [], []
    for row, prepared, folder, runtime, captured, scenario in prepared_rows:
        sid, started = row['slot_id'], time.time()
        owner.reseed(row['sampling_seed'], label=sid)
        episode = folder/'episode'
        begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), work_nodes=['TEAM::build'],
                      work_ids=[], scenario=scenario, policies=runtime.policy_identities)
        closed = False
        try:
            boundary = run_fragment(prepared, runtime, external_tick_per_sweep=1)
            finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
            closed = True
            atomic_write(folder/'public-capture.json', json_bytes(captured))
            atomic_write(folder/'runtime.json', json_bytes(runtime.snapshot()))
            members = {r['role_id']: {'actor_id': r['actor'], 'origin': 'target_model'} for r in prepared.scenario['roles']}
            rollout = export_online_rollout(episode, window=expected_window(declaration, sid), members=members,
                independent_capture=captured, reward_spec=prepared.reward_spec)
            graph = information_graph(rollout, read_operations=('read_object', 'read_alias', 'read_version'))
            mapping = map_joint_method(graph, route_id='basis', spec_id=MAPPER)
            atomic_write(folder/'team-rollout.json', json_bytes(rollout))
            atomic_write(folder/'mapping.json', json_bytes(mapping))
            atomic_write(folder/'information-graph.json', json_bytes(graph))
            entries.append({'slot_id': sid, 'rollout': rollout, 'reward': rollout['reward_eligibility'],
                            'active_members': list(prepared.active_roles)})
            records.append({'slot_id': sid, 'status': 'closed', 'rollout': rollout, 'mapping': mapping})
            summaries.append({'slot_id': sid, 'case_id': prepared.case['case_id'], 'harness': harness,
                'purpose': row.get('purpose', 'development_work'), 'boundary': boundary,
                'reward': rollout['reward_eligibility'], 'work_validity': rollout['work_validity'],
                'started_at': started, 'ended_at': time.time()})
        except Exception as error:
            detail = {'type': type(error).__name__, 'message': str(error), 'closed': closed, 'runtime': runtime.snapshot()}
            atomic_write(folder/'interruption.json', json_bytes(detail))
            atomic_write(folder/'public-capture.json', json_bytes(captured))
            entries.append({'slot_id': sid, 'rollout': None, 'reward': None, 'active_members': list(prepared.active_roles)})
            records.append({'slot_id': sid, 'status': 'closed_unassessed' if closed else 'interrupted'})
            summaries.append({'slot_id': sid, 'status': 'closed_unassessed' if closed else 'interrupted',
                              'error': {k: detail[k] for k in ('type', 'message')}})
        finally:
            if harness == 'openhands_v16':
                for worker in runtime.policies.values():
                    worker.close()
        atomic_write(output/'progress.json', json_bytes(summaries))
        print(json_bytes({'slot': sid, 'harness': harness,
              'reward': (entries[-1].get('reward') or {}).get('reward'),
              'status': summaries[-1].get('status', 'closed')}).decode(), flush=True)
    atomic_write(output/'support.json', json_bytes(diagnose_window(declaration, records)))
    atomic_write(output/'summary.json', json_bytes({'version': VERSION, 'actor_identity': identity,
        'actual_network_http_calls': 0, 'slots': summaries,
        'scope': 'Development evaluation only; current method labels are descriptive. No H2 training admission or ID-VTDO O4 is claimed.'}))
    return entries
