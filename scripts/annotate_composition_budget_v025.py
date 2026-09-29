"""Annotate a closed v025 report with an authorized, separately pinned budget.

No process control, model call, scoring, tensor load, git operation or budget
mutation occurs here. Original automatic report bytes are retained exactly.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

from proworksim.storage import atomic_write, json_bytes

VERSION = 'v025-terminal-budget-annotation-v1'
AMENDMENT_VERSION = 'authorized-v025-budget-extension-v1'
ORIGINAL = {'update_seconds': 39600, 'stage_seconds': 43200,
            'plan_gpu_seconds': 208800, 'no_support_gpu_seconds': 84600}
EFFECTIVE = {'update_seconds': 64800, 'stage_seconds': 72000,
             'plan_gpu_seconds': 237600, 'no_support_gpu_seconds': 113400}
UNCHANGED = {'wall_seconds': 259200, 'host_rss_bytes': 68719476736,
             'own_gpu_memory_mib': 57344, 'artifact_bytes': 34359738368}
ACCOUNTING_ADDITIONS = ('original_plan_budget_gpu_seconds', 'effective_budget_gpu_seconds',
                        'budget_gpu_seconds_meaning')


def _read(path):
    return json.loads(Path(path).read_bytes())


def _ref(path):
    path = Path(path).resolve()
    content = path.read_bytes()
    return {'path': str(path), 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}


def _checked(ref):
    if not isinstance(ref, dict) or not isinstance(ref.get('path'), str) or not isinstance(ref.get('sha256'), str):
        raise ValueError('A pinned original plan reference is required')
    path = Path(ref['path']).resolve()
    actual = _ref(path)
    if actual['sha256'] != ref['sha256'] or ('bytes' in ref and actual['bytes'] != ref['bytes']):
        raise ValueError('Original plan SHA differs from the amendment')
    return path


def _same_ref(left, right):
    return (isinstance(left, dict) and isinstance(right, dict)
            and Path(left.get('path', '')).resolve() == Path(right.get('path', '')).resolve()
            and left.get('sha256') == right.get('sha256'))


def _new_or_same(path, data):
    """An existing original is an immutable witness, never an overwrite target."""
    try:
        with path.open('xb') as stream:
            stream.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise ValueError('Refusing to overwrite different retained original bytes: ' + str(path))


def _bound_inputs(root, amendment_path, checkout):
    amendment, supervisor = _read(amendment_path), _read(root/'supervisor.json')
    authorization = amendment.get('authorization', {})
    recorded = authorization.get('recorded_at_epoch')
    if (amendment.get('version') != AMENDMENT_VERSION or not amendment.get('amendment_id')
            or Path(amendment.get('run_root', '')).resolve() != root
            or amendment.get('original_source') != supervisor.get('source')
            or not _same_ref(amendment.get('original_plan'), supervisor.get('plan'))
            or amendment.get('stage') != 'train_base'
            or authorization.get('user_instruction') != '提高预算，继续实验'
            or type(recorded) not in (int, float) or not math.isfinite(recorded)
            or amendment.get('original_limits') != ORIGINAL or amendment.get('effective_limits') != EFFECTIVE
            or amendment.get('unchanged_limits') != UNCHANGED):
        raise ValueError('Amendment authorization, source, run, stage or finite budget contract differs')
    changes = amendment.get('experiment_changes', {})
    if changes.get('additional_episodes') != 0 or changes.get('extra_optimizer_updates') != 0:
        raise ValueError('This annotation cannot authorize new episodes or parameter updates')
    if supervisor.get('status') not in {'complete', 'closed_with_incomplete_stages', 'supervisor_error'} or not supervisor.get('ended_at'):
        raise ValueError('Only a closed original supervisor may receive terminal annotation')
    archive = _read(root/'archive-status.json')
    if (archive.get('status') not in {'reports_written', 'committed_and_pushed', 'archive_failed'}
            or not archive.get('ended_at') or archive.get('experiment_source') != amendment['original_source']):
        raise ValueError('Original automatic archive must have ended before annotation')
    plan = _read(_checked(amendment['original_plan']))
    if (plan.get('internal_gpu_seconds') != ORIGINAL['plan_gpu_seconds']
            or plan.get('resource_caps', {}).get('train_base') != ORIGINAL['stage_seconds']
            or plan.get('task_caps', {}).get('update') != ORIGINAL['update_seconds']):
        raise ValueError('Frozen original plan no longer has the original stated limits')
    settings = plan['terminal_archive']
    if Path(settings['checkout']).resolve() != checkout:
        raise ValueError('Report checkout differs from the original frozen archive declaration')
    paths, relative = [], []
    for key in ('json', 'markdown'):
        name = settings[key]
        path = (checkout/name).resolve()
        if Path(name).is_absolute() or not path.is_relative_to(checkout/'docs/experiments') or not path.is_file():
            raise ValueError('Only existing original docs/experiments reports may be annotated')
        paths.append(path)
        relative.append(str(path.relative_to(checkout)))
    if len(set(paths)) != 2 or archive.get('files') != relative:
        raise ValueError('Automatic archive files differ from the frozen report pair')
    return amendment, paths, relative


def annotate(root, amendment_path, checkout):
    """Return two reviewable file paths; root owns any commit/push decision.

    Re-entry accepts only the exact expected original or annotated bytes, which
    also permits completing a previously interrupted pair of atomic replacements.
    """
    root, amendment_path, checkout = Path(root).resolve(), Path(amendment_path).resolve(), Path(checkout).resolve()
    amendment, paths, relative = _bound_inputs(root, amendment_path, checkout)
    amendment_ref = _ref(amendment_path)
    folder = root/'budget-extension'
    folder.mkdir(parents=True, exist_ok=True)
    originals = [folder/'original-terminal-report.json', folder/'original-terminal-report.md']
    current = [path.read_bytes() for path in paths]
    raw = [original.read_bytes() if original.is_file() else content for original, content in zip(originals, current)]
    report = json.loads(raw[0])
    if (report.get('version') != 'member-composition-report-v0.25'
            or Path(report.get('run_root', '')).resolve() != root
            or report.get('source') != amendment['original_source']
            or report.get('execution_terminal') is not True
            or not _same_ref(report.get('references', {}).get('plan'), amendment['original_plan'])
            or report.get('accounting', {}).get('budget_gpu_seconds') != ORIGINAL['plan_gpu_seconds']
            or 'authorized_budget_extension' in report
            or any(key in report.get('accounting', {}) for key in ACCOUNTING_ADDITIONS)):
        raise ValueError('Original report is not the unmodified bound terminal artifact')
    for original, content in zip(originals, raw):
        _new_or_same(original, content)
    original_refs = {'json': _ref(originals[0]), 'markdown': _ref(originals[1])}
    revised = copy.deepcopy(report)
    revised['authorized_budget_extension'] = {
        'version': VERSION, 'amendment_id': amendment['amendment_id'],
        'authorization': copy.deepcopy(amendment['authorization']), 'amendment_reference': amendment_ref,
        'original_source': copy.deepcopy(amendment['original_source']),
        'original_plan': copy.deepcopy(amendment['original_plan']),
        'stage': 'train_base', 'original_limits': copy.deepcopy(ORIGINAL),
        'effective_limits': copy.deepcopy(EFFECTIVE), 'unchanged_limits': copy.deepcopy(UNCHANGED),
        'original_terminal_reports': original_refs,
        'original_plan_and_frozen_source_modified': False,
        'business_outcomes_or_sampling_or_update_counts_modified': False,
        'completion_within_original_deadline_claimed': False,
        'scope': 'User-authorized budget extension for the same base worker/update. Original automatic report bytes retained; outcome/score/sample/update/cost evidence unchanged. Not completion within the original deadline.'}
    revised['accounting'].update(original_plan_budget_gpu_seconds=ORIGINAL['plan_gpu_seconds'],
        effective_budget_gpu_seconds=EFFECTIVE['plan_gpu_seconds'],
        budget_gpu_seconds_meaning='Original frozen plan limit, retained unchanged; effective authorized limit is effective_budget_gpu_seconds.')
    original_md = raw[1].decode('utf-8')
    if original_md.count('新上限58') != 1:
        raise ValueError('Original Markdown budget statement differs; refusing a broad text rewrite')
    notice = (
        '> **获授权预算修订**：用户指示“提高预算，继续实验”。同一基线更新的时限由 11 延至 18 小时，阶段由 12 延至 20 小时；'
        '原计划名义上限 58 GPU 小时，有效上限 66 GPU 小时（无支持路径由 23.5 延至 31.5 GPU 小时）。'
        '本轮采用运行中获授权延长，不能表述为在原时限内完成。冻结计划、业务结果及采样/更新次数保持原记录；原自动报告完整字节与 SHA 已另存。\n\n')
    expected = [json_bytes(revised), (notice + original_md.replace('新上限58', '原计划上限58 GPU小时／获授权有效上限66 GPU小时')).encode()]
    for path, actual, original, updated in zip(paths, current, raw, expected):
        if actual not in (original, updated):
            raise ValueError('A report was independently changed; refusing to overwrite: ' + str(path))
    record_path = folder/'annotation.json'
    record = {'version': VERSION, 'amendment_reference': amendment_ref,
              'original_source': amendment['original_source'], 'run_root': str(root),
              'original_terminal_reports': original_refs,
              'annotated_reports': {key: {'path': str(path), 'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
                                    for key, path, content in zip(('json', 'markdown'), paths, expected)},
              'files': relative, 'business_outcomes_changed': False, 'git_performed': False}
    if record_path.exists() and _read(record_path) != record:
        raise ValueError('An existing annotation belongs to different source/report/amendment bytes')
    for path, actual, updated in zip(paths, current, expected):
        if actual != updated:
            atomic_write(path, updated)
    _new_or_same(record_path, json_bytes(record))
    # Mechanical field-level preservation, independent of any result score.
    check = _read(paths[0])
    check.pop('authorized_budget_extension')
    for key in ACCOUNTING_ADDITIONS:
        check['accounting'].pop(key)
    if check != report:
        raise ValueError('Annotation unexpectedly changed original report evidence')
    return {'version': VERSION, 'files': relative, 'annotation_record': _ref(record_path),
            'original_terminal_reports': original_refs, 'annotated_reports': record['annotated_reports'],
            'git_performed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--amendment', type=Path, required=True)
    parser.add_argument('--checkout', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(annotate(args.run, args.amendment, args.checkout), ensure_ascii=False))


if __name__ == '__main__':
    main()
