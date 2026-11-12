"""Private namespace and actual pre-cleanup hook controls; no Docker creation."""
import hashlib
import json
from pathlib import Path
import sys
from types import FunctionType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from proworksim import software_benchmark_environment_passive_v203_2_1_r3 as repair
from proworksim import software_benchmark_environment_passive_v203_2_1_r2 as frozen
from proworksim import software_benchmark_grading_v105 as base
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace
from proworksim.software_benchmark_candidates_v054 import reference

ART = Path(__file__).parent
run = ART / 'binding-cpu'
run.mkdir(exist_ok=False)
def retain(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')
    return reference(path)
scope = SimpleNamespace(ROOT=ROOT, BATCH_ROOT=run, GRADING_ROOT=run / 'grading',
                        __file__=repair.__file__, retain=retain)
policy = SimpleNamespace(require_v066_allowed=lambda *args, **kwargs: {}, __file__=repair.__file__)
before = {key: id(value) for key, value in vars(frozen).items()}
namespace = clone_namespace(base, scope=scope)
namespace['private_environment'] = lambda policy: repair.private_environment(policy, scope, base.private_environment)
scorer = namespace['scorer'](policy)
router = scorer.environment
router.prepare()
assert router.request_fields(repair.TASK)['environment_revision']['path'].endswith('requests2317-offline-ca-r3.json')
assert router.offline.fixture_environment(router.offline.PROFILES[repair.TASK], {})['PYTHONPATH'].split(':')[0] == repair.FIXTURE_ROOT
assert router.offline.environment_manifest()['private_CA_augmentation']['verify_mode_changed'] is False
assert {key: id(value) for key, value in vars(frozen).items()} == before

actual = scorer.validate_request.__globals__
events = []
sentinel = {'official_result': 'unaltered'}
def old_cleanup(client, container, logger):
    events.append('original_cleanup')
def evaluator(client, container, logger):
    events.append('official_evaluator')
    cleanup_container(client, container, logger)
    return sentinel
private_evaluator = FunctionType(evaluator.__code__, {**evaluator.__globals__, 'cleanup_container': old_cleanup})
prior = actual['diagnostics']
actual['diagnostics'] = SimpleNamespace(**{**vars(prior), 'make_repaired_run_instance': lambda *args: (private_evaluator, {'original': True})})
repair.bind_scorer_environment(scorer)
rebound, provenance = actual['diagnostics'].make_repaired_run_instance(None, None)
container = SimpleNamespace(_before_stop=lambda: events.append('CA_verified_before_remove'))
assert rebound(None, container, None) is sentinel
assert events == ['official_evaluator', 'CA_verified_before_remove', 'original_cleanup']
assert rebound.__code__ is private_evaluator.__code__
assert private_evaluator.__globals__['cleanup_container'] is old_cleanup
assert provenance['original_official_evaluator_code_unchanged']
summary = {'passed': True, 'r2_module_namespace_unchanged': True, 'new_environment_manifest_written_only_in_CPU_folder': True,
           'actual_evaluator_cleanup_binding_measures_before_original_removal': events,
           'evaluator_code_object_unchanged': True, 'return_object_identity_preserved': True,
           'original_cleanup_binding_unchanged': True, 'Docker_calls': 0, 'network_calls': 0,
           'model_API_calls': 0, 'source_sha256': hashlib.sha256(Path(repair.__file__).read_bytes()).hexdigest()}
(ART / 'binding-cpu-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({'passed': True, 'controls': 2}))
