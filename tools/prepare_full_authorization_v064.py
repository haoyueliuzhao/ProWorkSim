"""Seal the concrete full evaluation within the user's existing batch grant.

This preparation only writes project files. It neither changes the shared hold
nor contacts Docker, a GPU, the API, or the user service manager.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path

from proworksim import software_benchmark_dispatch_v064 as policy
from proworksim import software_benchmark_sdk_bundle_v064 as sdk
from proworksim.software_benchmark_candidates_v054 import reference, write_new
from proworksim.storage import atomic_write, json_bytes

ROOT, BATCH = policy.ROOT, policy.BATCH_ROOT
OUT = ROOT / "artifacts/software-benchmark-v064/runtime-authorization-r1"


def module_file(name):
    path = ROOT / "src" / Path(*name.split('.'))
    return path.with_suffix('.py') if path.with_suffix('.py').is_file() else path / '__init__.py'


def dependency_sources():
    initial = set((ROOT / 'src/proworksim').glob('*v064*.py'))
    initial.update((ROOT / 'tools').glob('*v064*.py'))
    initial.update(ROOT / 'src/proworksim' / name for name in sdk.PROJECT_MODULES)
    initial.update(ROOT / name for name in policy.MANDATORY_SOURCE_PATHS if name.endswith('.py'))
    initial.update(ROOT / name for name in (
        'tools/start_ref_capacity_server_v054.py', 'tools/run_offline_scorer_v058.py',
        'src/proworksim/software_benchmark_ref_host_v061.py',
        'src/proworksim/software_benchmark_ref_service_v056.py',
        'src/proworksim/software_benchmark_gpu_lease_v054.py'))
    pending, seen = list(initial), set()
    while pending:
        path = pending.pop().resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        node = ast.parse(path.read_bytes(), filename=str(path))
        if path.is_relative_to(ROOT / 'src'):
            parts = path.relative_to(ROOT / 'src').with_suffix('').parts
            package = parts[:-1]
            for length in range(1, len(package)+1):
                pending.append(ROOT / 'src' / Path(*package[:length]) / '__init__.py')
        else:
            package = ()
        for entry in ast.walk(node):
            names = []
            if isinstance(entry, ast.Import):
                names.extend(alias.name for alias in entry.names)
            elif isinstance(entry, ast.ImportFrom):
                if entry.level:
                    if not package or entry.level > len(package):
                        continue
                    base = list(package[:len(package)-entry.level+1])
                    if entry.module:
                        base.extend(entry.module.split('.'))
                    names.append('.'.join(base))
                    names.extend('.'.join([*base, alias.name]) for alias in entry.names)
                elif entry.module:
                    names.append(entry.module)
                    names.extend(entry.module + '.' + alias.name for alias in entry.names)
            pending.extend(module_file(name) for name in names if name == 'proworksim' or name.startswith('proworksim.'))
    files = seen | {ROOT / name for name in policy.MANDATORY_SOURCE_PATHS}
    files.update({sdk.OUTPUT / 'manifest.json',
        ROOT / 'runs/software-benchmark-v061/model-runtime-r3/manifest.json',
        ROOT / 'runs/assets/models/Qwen3.5-9B-c20223623576/proworksim-manifest.json',
        ROOT / 'runs/software-benchmark-v055/tokenizer-r1/manifest.json',
        ROOT / 'runs/software-benchmark-v064/archive-codec/manifest.json',
        ROOT / 'runs/software-benchmark-v064/archive-codec/zstd',
        ROOT / 'config/v054-public-test-registry.json'})
    return [reference(path) for path in sorted(files)]


def tool_module(name):
    spec = importlib.util.spec_from_file_location('v064_prepare_' + name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare(*, record_user_authorization=False):
    if (policy.COORDINATOR_RUN_ROOT / 'execution-started.json').exists() or list((BATCH / 'resource-claims').glob('*.json')):
        raise ValueError('Never revise the sources or plan after a runtime identity was consumed')
    # Draft resource plans were made before the final API/spool constraints.
    # Preserve them before materializing the final identical 6000 task bindings.
    if policy.PLAN_FILE.exists():
        old = json.loads(policy.PLAN_FILE.read_bytes())
        if old.get('constraints') != policy.CONSTRAINTS:
            old_ref = reference(policy.PLAN_FILE)
            destination = BATCH / 'drafts' / ('resource-plan-' + old_ref['sha256'] + '.json')
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise ValueError('An earlier draft was already archived; inspect preparation instead of overwriting')
            policy.PLAN_FILE.rename(destination)
    policy.create_plan()
    bundle = sdk.prepare_bundle()
    source_ref = policy.retain(policy.SOURCE_INDEX_FILE, {
        'version': 'v064-runtime-sources-r1', 'files': dependency_sources(),
        'actor_bundle': reference(sdk.OUTPUT / 'manifest.json'),
        'source_selection': 'new runtime entries plus transitive local Python imports and pinned assets',
        'shared_host_configuration_changed': False})
    coordinator = tool_module('run_full_benchmark_v064')
    prepared = coordinator.prepare()
    api_preparation = tool_module('qualify_deepseek_v064').prepare()
    unit = tool_module('launch_full_benchmark_v064').prepare()
    OUT.mkdir(parents=True, exist_ok=True)
    proposal = {'version': policy.VERSION, 'plan': reference(policy.PLAN_FILE),
        'sources': policy.sources(), 'constraints': policy.CONSTRAINTS,
        'operations': sorted(policy.OPERATIONS), 'coordinator_plan': prepared,
        'SDK_bundle': reference(sdk.OUTPUT / 'manifest.json'), 'SDK_archive': bundle['archive'],
        'api_preparation': api_preparation, 'coordinator_unit': unit,
        'experiment': {'dataset': 'SWE-bench Verified official test, fixed complete 500 tasks',
            'groups': 12, 'fresh_episodes': 6000, 'models': ['original raw Qwen3.5-9B', 'DeepSeek Flash thinking/high'],
            'arms': ['REF', 'PROJECT'], 'input_output_token_budgets': [5000000, 7500000, 10000000],
            'formal_token_upper_bound': 45000000000, 'API_token_upper_bound': 22500000000,
            'cash_cap_CNY': '1500.00', 'cash_includes_neutral_and_condenser': True,
            'training': False, 'single_agent': True, 'extra_repeats': 0},
        'authorization_basis': {
            'user_request': '在此基础上做完整的评测，500万tokens，750万tokens，1000万tokens，此外将我们的项目实际上下文，输入输出等设置于ref对齐，做ref与project两个条件，本地qwen模型与deepseek api共十二组实验，注意统计各个组的实际平均tokens消耗，本轮实验开放权限',
            'API_budget_reply': '1500', 'API_thinking_reply': '采用思考模式',
            'question_item': '["request_user_input_async","call_5109a82e8b2349bc9b7b5bddc0c643aa"]'},
        'runtime_boundaries': {
            'existing_project_Docker_API_new_owned_objects_only': True,
            'no_host_binds_devices_or_privileged_containers': True,
            'actor_controller_network_none_drop_ALL': True,
            'only_predeclared_four_Requests_graders_have_private_network_capabilities': True,
            'API_host_direct_TLS_no_proxy_no_remote_search': True,
            'new_owned_ordinary_user_model_and_coordinator_units_only': True,
            'no_shared_mount_network_driver_linger_daemon_or_existing_service_changes': True,
            'old_v062_and_v063_must_be_completed_and_quiescent': True,
            'cleanup_owned_resources_on_completion': True,
            'unrelated_resources_affected': False},
        'actual_runtime_operations_in_preparation': 0, 'model_calls_in_preparation': 0}
    proposal_ref = policy.retain(OUT / 'proposal.json', proposal)
    auth = {'version': policy.VERSION, 'status': 'approved' if record_user_authorization else 'pending',
        'automatic_release': False, 'constraints': policy.CONSTRAINTS,
        'plan': reference(policy.PLAN_FILE), 'proposal': proposal_ref, 'sources': policy.sources(),
        'explicit_rootful_authorization': (
            '用户明确要求本轮完整500题×12组并开放本轮实验权限；沿已经确认的隔离Docker/普通用户GPU路径，仅本批自建对象与私有评分网络；不改共享服务器配置。用户另明确DeepSeek思考模式、总现金1500元。实际操作收窄为本提案的资源/对象/出网边界。'
            if record_user_authorization else None),
        'recorded_utc': datetime.now(timezone.utc).isoformat(),
        'user_scope_unchanged': True, 'shared_incident_hold_released': False}
    if policy.AUTHORIZATION_FILE.exists():
        raise ValueError('An existing v064 authorization must not be silently replaced')
    saved = write_new(OUT / ('approved-authorization.json' if record_user_authorization else 'pending-authorization.json'), auth)
    atomic_write(policy.AUTHORIZATION_FILE, json_bytes(auth))
    return {'proposal': proposal_ref, 'authorization': saved, 'source_index': source_ref,
            'coordinator_plan': prepared, 'runtime_operations': 0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--record-user-authorization', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(record_user_authorization=args.record_user_authorization), ensure_ascii=False))
