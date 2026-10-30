"""Exercise original validate_request through real independent -m children."""
from __future__ import annotations

import copy
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile

from proworksim import software_benchmark_rescore_v095 as scoring
from proworksim.software_benchmark_candidates_v054 import reference, write_new


def run():
    plan = scoring.load(reference(scoring.PLAN_FILE))
    candidates = [job for job in plan['jobs'] if job['endpoint'] == 'code']
    selected = [next(j for j in candidates if j['source_family'] == 'recovery_v094'
                     and j.get('administrative_recovery_audit') is None and arm in j['slot_id'])
                for arm in ('DEEPSEEK_REF_', 'DEEPSEEK_PROJECT_')]
    selected += [next(j for j in candidates if j.get('administrative_recovery_audit')),
                 next(j for j in candidates if j['source_family'] == 'original_v066')]
    spec = importlib.util.spec_from_file_location('prepare95', scoring.ROOT/'tools/prepare_rescore_v095.py')
    prepare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prepare)
    environment = {key: value for key, value in os.environ.items()
        if key not in {'PYTHONHOME', 'PYTHONPATH', 'PYTHONEXECUTABLE', 'LD_LIBRARY_PATH', 'LD_PRELOAD'}}
    results, negatives = [], []
    with tempfile.TemporaryDirectory(prefix='v095-real-validator-') as temporary:
        root = Path(temporary)
        manifest_ref = write_new(root/'manifest.json', prepare.child_manifest())
        fixture_plan = {**plan, 'administrative_root': str(root/'run'),
            'authorization_path': str(root/'authorization.json'), 'source_index_path': str(root/'sources.json'),
            'scorer_manifest': manifest_ref}
        fixture_plan_ref = write_new(root/'plan.json', fixture_plan)
        sources = write_new(root/'sources.json', {'files': [reference(scoring.__file__)]})
        write_new(root/'authorization.json', {'version': scoring.VERSION, 'status': 'approved',
            'plan': fixture_plan_ref, 'source_index': sources, 'maximum_score_containers': len(plan['jobs']),
            'maximum_concurrent_graders': 4, 'new_model_calls': 0, 'host_configuration_changes': 0})
        context = scoring.Context(fixture_plan_ref, fixture=root)
        policy = scoring.policy(context)
        for index, job in enumerate(selected):
            folder = context.grading_root/job['resource_key']
            folder.mkdir(parents=True)
            request = scoring.load(reference(scoring.RUN_ROOT/'grading'/job['resource_key']/'request.json'))
            request.update(plan=fixture_plan_ref, scorer_manifest=manifest_ref, directory=str(folder))
            request_ref = write_new(folder/'request.json', request)
            claim = policy.claim_resource(job['resource_key'])
            write_new(folder/'capacity-claim.json', {'prepared_request': request_ref, 'claim': claim})
            try:
                command = prepare.module_command('--validate-request', str(folder/'request.json'), '--cpu-fixture', str(root))
                result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=120)
                if result.returncode:
                    raise RuntimeError('Actual -m validate_request failed for '+job['resource_key']+': '+result.stderr[-4500:])
                parsed = json.loads(result.stdout)
                if parsed.get('passed') is not True or parsed.get('actual_original_validate_request_executed') is not True:
                    raise ValueError('Scorer child did not execute actual original validation')
                results.append({'resource_key': job['resource_key'], 'source_family': job['source_family'],
                    'administrative_recovery': job.get('administrative_recovery_audit') is not None, **parsed})
                if index == 0:
                    contaminated = copy.deepcopy(scoring.load(manifest_ref))
                    contaminated['parent']['parent']['effective_dependency_versions']['deepseek-recipe'] = '0.2.0'
                    bad_ref = write_new(root/'API-owner-contaminated-manifest.json', contaminated)
                    request['scorer_manifest'] = bad_ref
                    # Keep the original content-addressed prepared request
                    # mapping valid for this isolated negative fixture.
                    (folder/'request.json').write_text(json.dumps(request))
                    changed = reference(folder/'request.json')
                    (folder/'capacity-claim.json').write_text(json.dumps({'prepared_request': changed, 'claim': claim}))
                    failed = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=120)
                    assert failed.returncode != 0 and 'Capability scorer changed after freezing' in failed.stderr
                    negatives.append('API_overlay_manifest_rejected_by_original_validator')
            finally:
                policy.release_resource(claim, quiescent=True)
    return {'passed': True, 'real_independent_minus_m_scorer_children': len(results),
        'actual_validate_request_cases': results, 'negative_controls': negatives,
        'candidate_bytes_changed': False, 'Docker_operations': 0, 'model_calls': 0,
        'temporary_claims_only': True, 'original_run_directories_changed': False,
        'manifest_generation': 'fresh fixed scorer interpreter, no API counter overlay'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=scoring.PLAN_FILE)
    parser.add_argument('--output', type=Path, default=scoring.ROOT/'artifacts/software-benchmark-v095/real-scorer-validation-r2')
    args = parser.parse_args()
    scoring.PLAN_FILE = args.plan.resolve()
    scoring.RUN_ROOT = scoring.PLAN_FILE.parent
    result = run()
    folder = args.output
    folder.mkdir(parents=True, exist_ok=True)
    result['sources'] = [reference(scoring.__file__), reference(__file__)]
    write_new(folder/'summary.json', result)
    print(json.dumps(result, ensure_ascii=False))
