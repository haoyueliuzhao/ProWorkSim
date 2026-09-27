"""Two bounded R1 recovery controls: CPU fixtures, no model generation or GPU."""
from types import SimpleNamespace

import pytest

from proworksim import bridge_resume_v022 as recovery


def test_no_step_proof_requires_dead_processes_and_absent_mandatory_step_files(tmp_path, monkeypatch):
    source = {'code_commit': recovery.OLD_COMMIT, 'code_dirty': False}
    state = {'line': 'B1', 'status': 'stopped', 'stop_reason': 'task_time_budget', 'exit_code': -15,
             'pid': 123456, 'observer_pid': 123455, 'source': source}
    report = {'status': 'updating', 'source_before': source, 'train_rows': [{'status': 'closed'} for _ in range(4)]}
    update = {'window_id': 'v022-b1-train', 'stage': 'backward', 'backward_decisions_completed': 12,
              'admitted_decisions': 24, 'scheduled_slots': 4, 'actor_optimizer_steps': 0,
              'critic_optimizer_steps': 0, 'training_happened': False}
    monkeypatch.setattr(recovery, 'pid_alive', lambda _: False)
    proof = recovery.prove_no_step(state, report, update, tmp_path)
    assert proof['admitted'] and proof['terminal_tensor_hash_read_claimed'] is False
    (tmp_path / 'update').mkdir()
    marker = tmp_path / 'update/gradients-before-clip.pt'
    marker.write_bytes(b'explicit control: a mandatory pre-step file is present')
    with pytest.raises(ValueError, match='mandatory pre-step marker'):
        recovery.prove_no_step(state, report, update, tmp_path)
    marker.unlink()
    with pytest.raises(ValueError, match='12/24 pre-step'):
        recovery.prove_no_step(state, report, {**update, 'actor_optimizer_steps': 1}, tmp_path)
    monkeypatch.setattr(recovery, 'pid_alive', lambda _: True)
    with pytest.raises(ValueError, match='worker and observer gone'):
        recovery.prove_no_step(state, report, update, tmp_path)


def test_raw_before_state_restores_both_optimizers_rng_and_original_collecting_window(tmp_path):
    torch = pytest.importorskip('torch')
    from proworksim.online_training import SharedActor, tensor_tree_digest
    from proworksim.storage import digest

    class TinyActor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lora_logits = torch.nn.Parameter(torch.tensor([.2, .3]))
            self.config = SimpleNamespace(attention_dropout=0, use_cache=False)
            self.generation_config = SimpleNamespace(eos_token_id=99)
        def gradient_checkpointing_enable(self, **kwargs):
            pass

    def owner(name):
        return SharedActor(TinyActor(), object(), output=tmp_path / name, device='cpu', torch_module=torch,
                           base_identity={'manifest': {'sha256': digest(b'explicit CPU fixture')}},
                           inference_profile={'explicit_cpu_fixture': True})
    torch.manual_seed(17)
    original = owner('original')
    original.begin_window('v022-b1-train')
    saved = original._state_bundle()
    path = tmp_path / 'shared-before.pt'
    torch.save(saved, path)
    pinned = recovery.reference(path)
    fresh = owner('recovery')
    with torch.no_grad():
        fresh.actor_parameters['lora_logits'].fill_(99)
        for parameter in fresh.critic.parameters():
            parameter.fill_(42)
    fresh.actor_parameters['lora_logits'].grad = torch.ones(2)
    fresh.actor_optimizer.param_groups[0]['lr'] = .99
    fresh.critic_optimizer.param_groups[0]['lr'] = .88
    torch.manual_seed(12345)
    result = recovery.restore_before_update(fresh, pinned, saved['actor_identity'])
    assert result['exact_state_restored'] and result['partial_gradients_reused'] is False
    assert fresh.phase == 'collecting' and fresh.window_id == 'v022-b1-train'
    assert fresh.used_window_ids == ['v022-b1-train']
    assert tensor_tree_digest(fresh._state_bundle(), torch) == tensor_tree_digest(saved, torch)
    assert fresh.actor_parameters['lora_logits'].grad is None
    assert fresh.actor_steps == fresh.critic_steps == fresh.policy_revision == 0
    assert recovery.reference(path) == pinned
