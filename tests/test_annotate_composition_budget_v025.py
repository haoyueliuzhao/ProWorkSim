"""One finite terminal fixture: byte preservation, unchanged outcomes, idempotence."""
import copy
import hashlib
import json

from scripts.annotate_composition_budget_v025 import (
    ACCOUNTING_ADDITIONS, AMENDMENT_VERSION, EFFECTIVE, ORIGINAL, UNCHANGED,
    annotate,
)


def test_terminal_budget_annotation_preserves_original_evidence_bytes_and_is_idempotent(tmp_path):
    root, checkout = tmp_path/'run', tmp_path/'checkout'
    root.mkdir()
    folder = checkout/'docs/experiments'
    folder.mkdir(parents=True)
    files = ['docs/experiments/composition-pilot-v025.json', 'docs/experiments/composition-pilot-v025.md']
    source = {'code_commit': 'actual-frozen-fixture', 'source_tree_sha256': 'fixture-tree', 'code_dirty': False}

    def put(path, value):
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')

    plan_path = tmp_path/'frozen-plan.json'
    put(plan_path, {'internal_gpu_seconds': 208800, 'resource_caps': {'train_base': 43200},
                    'task_caps': {'update': 39600},
                    'terminal_archive': {'checkout': str(checkout), 'json': files[0], 'markdown': files[1]}})
    plan_bytes = plan_path.read_bytes()
    plan_ref = {'path': str(plan_path), 'sha256': hashlib.sha256(plan_bytes).hexdigest()}
    put(root/'supervisor.json', {'source': source, 'plan': plan_ref, 'status': 'complete', 'ended_at': 100})
    put(root/'archive-status.json', {'status': 'committed_and_pushed', 'ended_at': 102,
                                    'experiment_source': source, 'files': files})
    original = {'version': 'member-composition-report-v0.25', 'run_root': str(root),
                'source': source, 'execution_terminal': True, 'report_kind': 'closed_no_supported_block',
                'references': {'plan': plan_ref}, 'planned_primary_composition_difference': None,
                'configuration_changed': False, 'closed_new_episode_counts': {'support': 16, 'confirmation': 12, 'continuation': 2},
                'new_actor_steps': 1, 'new_critic_steps': 1, 'training_episode_consumptions_started': 16,
                'confirmation': {'base': {'completed': 0, 'known': 12}, 'configured': {'completed': 0, 'known': 0}},
                'accounting': {'budget_gpu_seconds': 208800, 'final_gpu_seconds': 78000.125}}
    original_json = (json.dumps(original, indent=4, ensure_ascii=False)+'\r\n').encode()
    original_md = '# 原自动报告\r\n\r\n完整职责0/12，预定主比较未知。\r\n已结算成本21.66 GPU小时，新上限58；外部模型/API为0。\r\n'.encode()
    (checkout/files[0]).write_bytes(original_json)
    (checkout/files[1]).write_bytes(original_md)
    amendment_path = root/'budget-amendment.json'
    put(amendment_path, {'version': AMENDMENT_VERSION, 'amendment_id': 'v025-budget-extension-fixture',
        'authorization': {'user_instruction': '提高预算，继续实验', 'recorded_at_epoch': 50},
        'run_root': str(root), 'original_source': source, 'original_plan': plan_ref, 'stage': 'train_base',
        'original_limits': ORIGINAL, 'effective_limits': EFFECTIVE, 'unchanged_limits': UNCHANGED,
        'experiment_changes': {'additional_episodes': 0, 'extra_optimizer_updates': 0}})
    first = annotate(root, amendment_path, checkout)
    revised = json.loads((checkout/files[0]).read_bytes())
    assert revised['accounting']['budget_gpu_seconds'] == 208800
    assert revised['accounting']['original_plan_budget_gpu_seconds'] == 208800
    assert revised['accounting']['effective_budget_gpu_seconds'] == 237600
    unchanged = copy.deepcopy(revised)
    extension = unchanged.pop('authorized_budget_extension')
    for key in ACCOUNTING_ADDITIONS:
        unchanged['accounting'].pop(key)
    assert unchanged == original
    assert extension['completion_within_original_deadline_claimed'] is False
    assert (root/'budget-extension/original-terminal-report.json').read_bytes() == original_json
    assert (root/'budget-extension/original-terminal-report.md').read_bytes() == original_md
    assert first['original_terminal_reports']['json']['sha256'] == hashlib.sha256(original_json).hexdigest()
    modified = [(checkout/f).read_bytes() for f in files]
    assert '原计划上限58 GPU小时／获授权有效上限66 GPU小时' in modified[1].decode()
    assert '不能表述为在原时限内完成' in modified[1].decode()
    second = annotate(root, amendment_path, checkout)
    assert second == first and second['files'] == files and not second['git_performed']
    assert [(checkout/f).read_bytes() for f in files] == modified
    assert plan_path.read_bytes() == plan_bytes  # The frozen plan remains byte-identical.
