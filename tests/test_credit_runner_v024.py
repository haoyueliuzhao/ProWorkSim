"""One runner/API integration; CPU native parsing, no model or optimizer step."""
import copy
import json
from types import SimpleNamespace

import pytest

from proworksim.collaboration_training_v024 import training_admission, validate_window_declaration
from proworksim.credit_consumption_v024 import prepare_common_consumption, save_common_origin
from proworksim.deterministic_work_v024 import DeterministicCandidateActor
from proworksim.online_training import SharedActor, prepare_window
from proworksim.storage import digest, json_bytes, read_json
from proworksim.templates import retail_collaboration_v024 as world
from scripts.credit_pilot_v024 import collect_window, credit_signals
from test_collaboration_training_v022 import ExplicitSyntheticTokenTransport


def test_formal_collection_native_parse_common_branches_and_rtg_signal_wrapper(tmp_path):
    torch = pytest.importorskip('torch')
    if not (world.DEFAULT_ASSETS / 'manifest.json').exists():
        pytest.skip('Pinned new v024 source materials required')
    catalog = world.registry()
    contract = catalog['sampling_windows'][0]
    native_parser = object.__new__(DeterministicCandidateActor)

    class TinyActor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lora_logits = torch.nn.Parameter(torch.tensor([.2, .3]))
            self.config = SimpleNamespace(attention_dropout=0, use_cache=False)
            self.generation_config = SimpleNamespace(eos_token_id=99)
        def gradient_checkpointing_enable(self, **kwargs):
            pass

    class Owner(SharedActor):
        @property
        def transport(self):
            return self

        def reseed(self, seed, *, label):
            super().reseed(seed, label=label)
            slot = next(s for s in contract['slots'] if s['slot_id'] == label)
            self.task, self.counters = slot['task'], {}

        def complete(self, request, *, timeout_seconds):
            result = ExplicitSyntheticTokenTransport.complete(self, request, timeout_seconds=timeout_seconds)
            body = result['body']
            message = body['choices'][0]['message']
            if message.get('tool_calls'):
                call = message['tool_calls'][0]['function']
                arguments = json.loads(call['arguments'])
                params = ''.join('<parameter=' + key + '>\n'
                    + (value if isinstance(value, str) else json.dumps(value)) + '\n</parameter>\n'
                    for key, value in arguments.items())
                raw = message['content'] + '\n<tool_call><function=' + call['name'] + '>\n' + params + '</function></tool_call>'
            else:
                raw = message['content']
            parsed, error = native_parser.parse_response(raw, request)
            assert error is None
            body['choices'][0]['message'] = parsed
            body['native_cpu_fixture_raw'] = raw
            body['fixture_provenance'] += '; actual production XML parser executed'
            result['raw_body'] = json_bytes(body).decode()
            self.responses[-1]['body'] = copy.deepcopy(body)
            self.parsed_calls += 1
            return result

    def owner(name):
        result = Owner(TinyActor(), object(), output=tmp_path / name, device='cpu', torch_module=torch,
            recipe={'max_length': 16384, 'max_output_tokens': 2048},
            base_identity={'manifest': {'sha256': digest(b'CPU formal runner fixture')}},
            inference_profile={'explicit_cpu_fixture': True})
        result.requests, result.responses, result.counters, result.task = [], [], {}, None
        result.parsed_calls = 0
        return result

    source = owner('source')
    admission = training_admission(catalog, world.PIN_PATH)
    collection = tmp_path / 'common' / 'collection'
    collection.mkdir(parents=True)
    entries, rows = collect_window(source, catalog, contract, admission, collection, world.DEFAULT_ASSETS)
    declaration = read_json(collection / 'declaration.json')
    assert len(rows) == 6 and all(row['status'] == 'closed' for row in rows)
    assert source.parsed_calls > 0
    assert declaration['gamma_identity']['recipe'] == source.recipe
    assert declaration['gamma_identity']['credit_arm'] == 'common'
    raw = json_bytes(entries)
    origin = tmp_path / 'origin'
    save_common_origin(source, origin, entries, declaration, admission)
    for arm in ('mc', 'handoff_rtg'):
        learner = owner(arm)
        proof = prepare_common_consumption(learner, origin, entries, declaration, admission, arm)
        assert proof['comparison']['target_changes'] and proof['exact_common_state_restored']
        assert learner.parsed_calls == 0
        prepared = prepare_window(entries, learner.freeze_identity(), learner.window_id, learner.recipe)
        update = tmp_path / arm / 'synthetic-signal-control' / 'update'
        update.mkdir(parents=True)
        (update / 'admission.json').write_bytes(json_bytes(prepared))
        # Observational wrapper control only. No actual loss or optimizer is run.
        (update / 'report.json').write_bytes(json_bytes({'status': 'explicit_CPU_signal_fixture',
            'old_critic_values': [0.] * len(prepared['decisions']),
            'advantages': [row['reward'] for row in prepared['decisions']],
            'actor_optimizer_steps': 0, 'critic_optimizer_steps': 0}))
        signal = credit_signals(entries, update.parent, learner)
        assert signal['credit_assignment'] == learner.recipe['credit_assignment']
        assert signal['version'] == 'work-credit-diagnostics-v0.24'
        assert all(row['return_target'] == row['advantage'] for row in signal['decisions'])
        if arm == 'handoff_rtg':
            assert any(row['terminal_reward'] == .2 and row['return_target'] == 0
                       and row['advantage_sign'] == 'zero' for row in signal['decisions'])
        assert all(row['reward_ledger']['version'] == 'actual-handoff-credit-v0.24' for row in signal['decisions'])
        # A second collection has its own original sampling window, not a new
        # name pasted onto D0. The unchanged old declaration cannot pass it.
        second = next(w for w in catalog['sampling_windows'] if w['credit_arm'] == arm)
        fake_second = copy.deepcopy(declaration)
        fake_second['window_id'] = second['window_id']
        with pytest.raises(ValueError, match='order/cases'):
            validate_window_declaration(fake_second, admission)
    assert json_bytes(entries) == raw
    assert source.actor_steps == source.critic_steps == 0
