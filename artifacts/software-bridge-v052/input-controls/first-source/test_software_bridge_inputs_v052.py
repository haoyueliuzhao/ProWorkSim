"""Pure initial-input gates; no SDK, tokenizer, repository or model execution."""
import copy
from pathlib import Path
import json

import pytest

from scripts.software_bridge_inputs_v052 import (
    CONTRACT, MetadataOwner, TASK_IDS, SDK_COMMIT, validate_capture_counters, validate_records,
)


def test_initial_release_requires_all_six_sources_and_stable_reference():
    design = json.loads((Path(__file__).resolve().parents[1] / 'docs/experiments/software-bridge-v052-design.json').read_bytes())
    runtime = {'path': '/synthetic/runtime.json', 'sha256': 'synthetic', 'bytes': 1}
    release = {'version': 'v052-initial-input-execution-release-v1', 'released': True,
               'maximum_initial_SDK_requests': 12, 'test_runtime': runtime}
    source = {'version': 'v052-shared-source-qualification-v1', 'passed': True, 'completed': True,
        'fixture_only': False, 'qualified_case_ids': list(TASK_IDS), 'blocked_case_ids': [], 'runtime_manifest': runtime}
    reference = {'version': 'v052-openhands-reference-runtime-v1', 'sdk_version': '1.49.6',
                 'sdk_commit': SDK_COMMIT, 'tools_version': '1.49.6'}
    assert len(validate_records(release, source, design, reference)) == 12
    for change in ({'passed': False}, {'fixture_only': True}, {'qualified_case_ids': list(TASK_IDS[:-1])}):
        with pytest.raises(ValueError):
            validate_records(release, {**source, **change}, design, reference)
    with pytest.raises(ValueError):
        validate_records({**release, 'released': False}, source, design, reference)
    with pytest.raises(ValueError):
        validate_records(release, source, design, {**reference, 'sdk_commit': 'different'})


def test_metadata_owner_raw_identity_is_not_loaded_weights_or_a_retained_actor():
    model = {'path': '/synthetic/model/proworksim-manifest.json', 'sha256': 'base', 'bytes': 1}
    metadata = {'actor_identity': {'raw_release': True, 'trained_adapter_loaded': False, 'checkpoint': None,
        'adapter_sha256': None, 'base_manifest': model, 'policy_version': 'raw-policy', 'model_path': '/synthetic/model'},
        'inference_profile': {'path': 'project', 'contract': CONTRACT}}
    owner = MetadataOwner(metadata, metadata_reference={'path': '/synthetic/old-owner.json'},
        model_manifest=model, slot_id='v052-synthetic-PS1', tokenizer=None)
    assert owner.freeze_identity() == metadata['actor_identity']
    assert owner.window_id == 'calibration-v051:v052-synthetic-PS1'
    assert not any(hasattr(owner, key) for key in ('model', 'torch', 'optimizer', 'capture_evaluation_state'))
    changed = copy.deepcopy(metadata)
    changed['actor_identity']['trained_adapter_loaded'] = True
    with pytest.raises(ValueError):
        MetadataOwner(changed, metadata_reference={}, model_manifest=model, slot_id='synthetic', tokenizer=None)


def test_capture_boundary_retains_real_bookkeeping_without_dispatch():
    ps1 = {'harness_decisions': 1, 'team_decisions': 1, 'attempts': 0, 'reservation_tokens': 0,
           'responses': 0, 'tool_actions': 0, 'model_generations': 0}
    assert validate_capture_counters('PS1', ps1)
    # A fake zero ledger would not match the real first-opportunity path.
    with pytest.raises(ValueError):
        validate_capture_counters('PS1', {**ps1, 'team_decisions': 0})
    oh = {**ps1, 'harness_decisions': None, 'team_decisions': None, 'adapter_decisions': 0,
          'native_SDK_LLM_entries': 1}
    assert validate_capture_counters('OH_ref', oh)
    for key in ('attempts', 'reservation_tokens', 'responses', 'tool_actions', 'model_generations'):
        with pytest.raises(ValueError):
            validate_capture_counters('OH_ref', {**oh, key: 1})
    with pytest.raises(ValueError):
        validate_capture_counters('PS1', ps1, unchanged=False)
