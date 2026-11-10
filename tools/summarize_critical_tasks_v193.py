"""Read the active deployment while preserving the retired zero-model attempt."""
import importlib.util
import json

from proworksim import software_benchmark_scope_v193 as scope


def summary():
    spec = importlib.util.spec_from_file_location('critical_progress_base', scope.ROOT / 'tools/summarize_critical_tasks_v192.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.scope = scope
    value = module.summary()
    value.update(version='v193-readonly-progress-r1',
                 prior_zero_model_diagnostic_pairs_failed_and_removed=4,
                 prior_formal_API_calls=0, total_authorized_formal_attempts=60,
                 total_authorized_new_cash_CNY=300)
    return value


if __name__ == '__main__':
    print(json.dumps(summary(), ensure_ascii=False, indent=2))
