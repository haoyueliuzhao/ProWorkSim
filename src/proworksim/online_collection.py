"""Live short-world collector for one frozen shared-policy window.

No reference policy runs inside the actor interval. Role deadlines are separate;
a finished provider never consumes the implementer's remaining opportunities.
"""

import copy
import time
from pathlib import Path

from .audit import code_identity
from .episode import begin_episode, finish_episode
from .experience import ExperienceRecorder, capture_port
from .information_mapper import information_graph, map_joint_method
from .model_policy import ModelPolicy
from .online_support import declare_window, expected_window, export_online_rollout, diagnose_window
from .scenarios import ScenarioController
from .staff_runtime import StaffRuntime
from .storage import atomic_write, digest, json_bytes
from .templates.online_work import build_online_case, case_spec
from .work_interface import WorkInterface, INTERFACE_VERSION, LEGACY_INTERFACE, V14_INTERFACE

VERSION = "online-collection-v0.14"
MAPPER = "online-basis-handoff-v0.13"


def _config(owner, role, task, limits):
    identity = owner.freeze_identity()
    return {
        "backend_id": "resident_direct", "model": "shared-local-actor",
        "base_url": "http://127.0.0.1:1/v1", "api_key_env": None,
        "model_revision": identity["policy_version"], "weight_identity": identity,
        "task": task, "thinking": None, "reasoning_effort": None,
        "action_protocol": "native_tools", "context_policy": "latest_observation",
        "format_error_policy": "format_feedback_continue",
        "format_limits": {"max_total": 4, "max_consecutive": 2},
        "temperature": owner.recipe["temperature"],
        "max_output_tokens": owner.recipe["max_output_tokens"],
        "max_context_tokens": owner.recipe["max_length"], "timeout_seconds": 600,
        "retry": {"max_attempts": 1, "retry_statuses": [], "backoff_seconds": []},
        "budget": {"max_decisions": limits[role], "max_http_attempts": limits[role],
                   "max_total_tokens": 500000, "max_cost_usd": 0, "max_context_bytes": 240000},
        "pricing": {"input_miss_per_million": 0, "input_hit_per_million": 0, "output_per_million": 0},
    }


def run_fragment(prepared, runtime, *, external_tick_per_sweep=1):
    """A declared finite deadline, no hidden evaluator stopping or action repair.

    Each role gets its own fixed generation budget. Control waits consume it;
    done/error/exhaustion retires that role. One additional opportunity flushes
    each role's last actual tool result before its adapter budget boundary.
    A fixed external clock advances transport only; it never supplies evidence.
    """
    if type(external_tick_per_sweep) is not int or not 0 <= external_tick_per_sweep <= 1:
        raise ValueError("Only predeclared zero/one world tick per sweep is supported")
    controller = ScenarioController(prepared.deployment, recorder=runtime.recorder)
    controller.record_environment()  # Set cursor; prefix events are not actor work.
    stopped, results = {}, []
    max_rounds = max(prepared.case['role_decision_limits'].values()) + 1
    for sweep in range(max_rounds):
        for label in runtime.labels:
            assert runtime.labels[runtime.cursor % len(runtime.labels)] == label
            if label in stopped:
                runtime.cursor += 1
                runtime.recorder.record('role_not_scheduled', {'worker_id': label, 'reason': stopped[label], 'sweep': sweep})
                continue
            result = runtime.step()
            results.append(result)
            controller.record_environment()
            status = result['status']
            if status in {'completed', 'model_budget_exhausted', 'model_service_error', 'model_format_error', 'model_usage_missing', 'binding_mismatch', 'environment_error'}:
                stopped[label] = status
            elif status == 'policy_error' and not result.get('action_performed'):
                stopped[label] = status
        if external_tick_per_sweep:
            response = prepared.world.session('operator').call('wait', ticks=external_tick_per_sweep)
            runtime.recorder.record('controller_action', {
                'stage': 'fixed_external_clock', 'origin': 'environment', 'sweep': sweep,
                'actor': 'operator', 'tool': 'wait', 'arguments': {'ticks': external_tick_per_sweep}, 'response': response,
            })
            controller.record_environment()
            if not response.get('ok'):
                return {'status': 'environment_error', 'kind': 'finite_task_deadline', 'role_stops': stopped, 'outcomes': results}
        if len(stopped) == len(runtime.labels):
            break
    return {
        'status': 'workers_done' if all(v == 'completed' for v in stopped.values()) else 'finite_task_deadline',
        'kind': 'finite_horizon_task_terminal', 'role_stops': stopped,
        'outcomes': results, 'opportunities': runtime.opportunities, 'actions': runtime.actions,
        'continuation': False, 'bootstrap': 0,
        'scope': 'Fixed short-task deadline; this terminal does not claim the business goal completed. No later continuation can backfill its reward.',
    }


def collect_window(owner, window_spec, output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    if not window_spec.get('slots'):
        raise ValueError('Predeclare all actual online slots')
    atomic_write(output / 'window-spec.json', json_bytes(window_spec))
    interface = window_spec.get('interface', 'v13')
    variant_id = {'v13': INTERFACE_VERSION, 'legacy': LEGACY_INTERFACE, 'v14': V14_INTERFACE}[interface]
    presentation = window_spec.get('presentation')
    template = window_spec.get('template', 'online_work')
    if template == 'learning_work':
        from .templates.learning_work import case_spec as resolve_case, build_learning_case as build_case
    elif template == 'online_work':
        resolve_case, build_case = case_spec, build_online_case
    else:
        raise ValueError('Unknown frozen online work template')
    identity = owner.freeze_identity()
    prepared_rows, declaration_rows = [], []
    # Freeze every environment/policy binding before the first model opportunity.
    for index, row in enumerate(window_spec['slots']):
        case = copy.deepcopy(row.get('case') or resolve_case(row['case_id']))
        folder = output / ('slot-' + str(index))
        prepared = build_case(case, folder)
        if prepared.deployment.status != 'ready':
            raise ValueError('Predeclared short scenario failed preparation')
        captured, interfaces, policies, ports = {}, {}, {}, {}
        for role in prepared.scenario['roles']:
            label = role['role_id']
            config = _config(owner, label, role['config']['task'], case['role_decision_limits'])
            policy = ModelPolicy(config, transport=owner.transport, audit_dir=folder / 'model-calls' / label)
            policies[label] = policy
            role.update(policy='model', config=copy.deepcopy(policy.config))
            interface_port = WorkInterface(prepared.world.session(role['actor'], role['project']), label,
                                           audit_dir=folder / 'public-projections' / label, variant=interface,
                                           **({'presentation': presentation} if presentation is not None else {}))
            interfaces[label] = interface_port
            ports[label] = capture_port(interface_port, captured.setdefault(label, []))
        runtime = StaffRuntime(ports, policies, recorder=ExperienceRecorder())
        environment_identity = {'version': VERSION, 'case': case, 'reward_spec': prepared.reward_spec,
                                'initial_business_sha256': prepared.prefix['prepared_business_state_sha256']}
        spec_record = copy.deepcopy(prepared.scenario)
        spec_record['variation']['online_collection'] = {
            'interface': variant_id, 'presentation': presentation, 'role_profile_binding': {label: interfaces[label].profile for label in interfaces},
            'deadline': 'per-role generation limit; fixed finite task horizon',
            'external_tick_per_sweep': window_spec.get('external_tick_per_sweep', 1),
        }
        atomic_write(folder / 'model-scenario.json', json_bytes(spec_record))
        declaration_rows.append({
            'slot_id': row['slot_id'], 'xi_id': case['case_id'],
            'xi_fingerprint': digest(json_bytes(environment_identity)), 'active_members': list(prepared.active_roles),
            'policies': runtime.policy_identities, 'mapping_spec_id': MAPPER,
        })
        prepared_rows.append((row, prepared, folder, runtime, captured, spec_record))
    declaration = declare_window(window_spec['window_id'], actor_identity=identity,
        gamma_identity={'collection_version': VERSION, 'interface_version': variant_id,
                        'presentation': presentation, 'template': template,
                        'recipe': owner.recipe, 'external_tick_per_sweep': window_spec.get('external_tick_per_sweep', 1),
                        'fixed_slot_cases': [r['xi_fingerprint'] for r in declaration_rows],
                        'slot_sampling_seeds': {r['slot_id']: r['sampling_seed'] for r in window_spec['slots']},
                        'rng_protocol': 'reseed CPU/all CUDA at slot entry; record true before/after hashes',
                        'source': code_identity(), 'transport_kind': 'resident_direct'},
        slot_specs=declaration_rows, min_class_count=window_spec.get('min_class_count', 2))
    atomic_write(output / 'declaration.json', json_bytes(declaration))
    entries, support_records, summaries = [], [], []
    for row, prepared, folder, runtime, captured, spec in prepared_rows:
        sid = row['slot_id']
        owner.reseed(row['sampling_seed'], label=sid)
        started = time.time()
        episode = folder / 'episode'
        begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(),
                      work_nodes=['TEAM::build'], work_ids=[], scenario=spec,
                      policies=runtime.policy_identities)
        closed = False
        try:
            boundary = run_fragment(prepared, runtime, external_tick_per_sweep=window_spec.get('external_tick_per_sweep', 1))
            finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
            closed = True
            atomic_write(folder / 'public-capture.json', json_bytes(captured))
            atomic_write(folder / 'runtime.json', json_bytes(runtime.snapshot()))
            actors = {r['role_id']: r['actor'] for r in prepared.scenario['roles']}
            members = {m: {'actor_id': actors[m], 'origin': 'target_model'} for m in prepared.active_roles}
            rollout = export_online_rollout(episode, window=expected_window(declaration, sid), members=members,
                                           independent_capture=captured, reward_spec=prepared.reward_spec)
            graph = information_graph(rollout, read_operations=('read_object', 'read_alias', 'read_version'))
            mapping = map_joint_method(graph, route_id='basis', spec_id=MAPPER)
            reward = rollout['reward_eligibility']
            atomic_write(folder / 'team-rollout.json', json_bytes(rollout))
            atomic_write(folder / 'information-graph.json', json_bytes(graph))
            atomic_write(folder / 'mapping.json', json_bytes(mapping))
            entries.append({'slot_id': sid, 'rollout': rollout, 'reward': reward, 'active_members': list(prepared.active_roles)})
            support_records.append({'slot_id': sid, 'status': 'closed', 'rollout': rollout, 'mapping': mapping})
            summaries.append({'slot_id': sid, 'case_id': prepared.case['case_id'], 'boundary': boundary['status'],
                              'reward': reward, 'work_validity': rollout['work_validity'],
                              'meters': {m: runtime.roles[m]['memory'].get('meter', {}) for m in runtime.labels},
                              'started_at': started, 'ended_at': time.time()})
        except Exception as error:
            # Preserve actual closure status; assessment failure is unknown, not R=0.
            status = 'closed_unassessed' if closed else 'interrupted'
            atomic_write(folder / 'interruption.json', json_bytes({'type': type(error).__name__, 'message': str(error), 'phase': 'postprocessing' if closed else 'interaction', 'closed': closed, 'runtime': runtime.snapshot()}))
            atomic_write(folder / 'public-capture.json', json_bytes(captured))
            support_records.append({'slot_id': sid, 'status': status, **({'episode': str(episode.resolve()), 'manifest_sha256': digest((episode / 'manifest.json').read_bytes())} if closed else {})})
            entries.append({'slot_id': sid, 'rollout': None, 'reward': None, 'active_members': list(prepared.active_roles)})
            summaries.append({'slot_id': sid, 'status': status, 'error': {'type': type(error).__name__, 'message': str(error)}})
        atomic_write(output / 'progress.json', json_bytes(summaries))
        print(json_bytes({'window': window_spec['window_id'], 'slot': sid,
                          'reward': (entries[-1].get('reward') or {}).get('reward'),
                          'status': summaries[-1].get('status', summaries[-1].get('boundary'))}).decode(), flush=True)
    support = diagnose_window(declaration, support_records)
    atomic_write(output / 'support.json', json_bytes(support))
    atomic_write(output / 'summary.json', json_bytes({'version': VERSION, 'actor_identity': identity,
        'actual_network_http_calls': 0, 'slots': summaries, 'support_ref': {'path': str((output/'support.json').resolve()), 'sha256': digest(json_bytes(support))}}))
    return entries
