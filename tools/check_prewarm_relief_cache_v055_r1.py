"""Only the new fixed wrapper/allowlist controls; reuse the prior eight controls."""
import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'tools/reclaim_prewarm_relief_cache_v055_r1.py'
spec = importlib.util.spec_from_file_location('prewarm_relief_cache_control', PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def run():
    helper = module.recovery()
    base = helper.original()
    plan = {'version': module.VERSION, 'invocation_wrapper': base.ref(PATH),
        'source': base.ref(module.RECOVERY_PATH), 'original_helper': {'sha256': helper.ORIGINAL_SHA},
        'allowlist': [{'instance_id': name, 'payload': str(module.target_path(name)), 'device': 66306,
            'allocated_bytes_observed_du': value[1]} for name, value in module.TARGETS.items()]}
    module.validate_plan(plan, base, helper)
    checks = ['exact_two_item_plan_accepted']
    def reject(label, callback):
        try:
            callback()
        except ValueError:
            checks.append(label)
        else:
            raise AssertionError(label)
    reject('third_instance_rejected', lambda: module.target_path('pydata__xarray-2905'))
    changed = copy.deepcopy(plan)
    changed['allowlist'][0]['payload'] = str(module.target_path('pydata__xarray-6744').parent)
    reject('parent_directory_rejected', lambda: module.validate_plan(changed, base, helper))
    changed = copy.deepcopy(plan)
    changed['allowlist'][0]['device'] = 66307
    reject('different_volume_rejected', lambda: module.validate_plan(changed, base, helper))
    changed = copy.deepcopy(plan)
    changed['invocation_wrapper']['sha256'] = '0' * 64
    reject('wrapper_source_change_rejected', lambda: module.validate_plan(changed, base, helper))
    return {'version': module.VERSION + '-CPU-control', 'passed': True, 'checks': checks,
        'sources': [base.ref(PATH), base.ref(__file__), base.ref(module.RECOVERY_PATH)],
        'new_model_calls': 0, 'deletions': 0, 'service_signals': 0,
        'previous_eight_quiescence_controls_reused_without_repetition': True}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
