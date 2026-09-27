"""Real CPU tensors/sampling with an explicitly tiny loader fixture, no GPU/base claim."""

from types import SimpleNamespace

import pytest

from proworksim.storage import json_bytes, read_json


@pytest.fixture
def replica_fixture(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    from proworksim.candidate_runtime_v019 import CandidateActor, candidate_profile
    from proworksim.online_training import reference
    import proworksim.sampling_replica_v019 as replicas

    source = {"code_commit": "cpu-fixture", "code_dirty": False, "source_tree_sha256": "fixture"}
    monkeypatch.setattr(replicas, "code_identity", lambda: dict(source))
    monkeypatch.setattr(replicas, "_source_refs", lambda: {"fixture": "no production-source claim"})
    base = tmp_path / "base"
    base.mkdir()
    weights = base / "weights.json"
    weights.write_bytes(json_bytes({"fixture": True}))
    base_identity = {"path": str(base), "manifest": reference(weights), "revision": "fixture"}

    class TinyActor(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lora_logits = torch.nn.Parameter(torch.zeros(7))
            self.config = SimpleNamespace(attention_dropout=0, use_cache=False,
                                          model_type="qwen3_5_text", is_encoder_decoder=False)
            self.config.get_text_config = lambda: self.config
            self.generation_config = SimpleNamespace(eos_token_id=99)

        def gradient_checkpointing_enable(self, **kwargs):
            self.checkpoint_kwargs = kwargs

        def generate(self, input_ids, logits_processor, max_new_tokens, **kwargs):
            ids = input_ids
            for _ in range(max_new_tokens):
                scores = logits_processor[0](ids, self.lora_logits[None, :])
                chosen = torch.multinomial(scores.softmax(-1), 1)
                ids = torch.cat([ids, chosen], dim=1)
            return ids

    class Tokenizer:
        pad_token_id = 0

        def apply_chat_template(self, *args, **kwargs):
            return "tiny exact sampling fixture"

        def __call__(self, text, **kwargs):
            return {"input_ids": [1, 2]}

        def decode(self, ids, **kwargs):
            return "fixture " + str(ids)

    def construct(cls, output, profile, recipe=None):
        return cls(TinyActor(), Tokenizer(), output=output, base_identity=base_identity,
                   inference_profile=profile,
                   recipe=recipe or {"max_length": profile["max_context_tokens"],
                                     "max_output_tokens": profile["max_output_tokens"]},
                   device="cpu", torch_module=torch)

    parent = construct(CandidateActor, tmp_path / "parent", candidate_profile("qwen3.5-9b", devices=2))
    # Synthetic previous-parent-history metadata; no test claims these as actual optimizer steps.
    with torch.no_grad():
        parent.actor_parameters["lora_logits"][0] = 0.75
    parent.policy_revision, parent.actor_steps, parent.critic_steps = 3, 3, 4
    parent._identity = parent._make_identity()
    parent.begin_window("declared-window")
    snapshot = tmp_path / "snapshot"
    exported = parent.export_sampling_snapshot(snapshot)
    called = []

    def loader(cls, model_path, *, manifest, profile, output, recipe):
        called.append(True)
        return construct(cls, output, profile, recipe)

    monkeypatch.setattr(replicas.SamplingReplica, "from_candidate", classmethod(loader))
    return SimpleNamespace(torch=torch, module=replicas, parent=parent, snapshot=snapshot,
                           exported=exported, called=called, root=tmp_path)


def test_snapshot_load_has_no_optimizer_and_preserves_actual_tokens_identity(replica_fixture, monkeypatch):
    f = replica_fixture
    # A readonly load must not even construct a critic or optimizer.
    def forbidden(*args, **kwargs):
        raise AssertionError("A sampling replica tried to construct learning state")
    monkeypatch.setattr(f.torch.optim, "AdamW", forbidden)
    monkeypatch.setattr(f.torch.nn, "Linear", forbidden)
    replica = f.module.load_replica(f.snapshot, f.root / "replica")
    verified = replica.verify_sampling_identity()
    assert verified["passed"] and verified["optimizer_absent"] and verified["critic_absent"]
    assert replica.freeze_identity() == f.parent.freeze_identity()
    assert replica.actor_steps == replica.critic_steps == 0
    assert verified["parent_update_counts"] == {"actor": 3, "critic": 4}
    assert replica.policy_revision == 3 and not any(p.requires_grad for p in replica.model.parameters())
    tensor_file = f.torch.load(f.snapshot / "snapshot.pt", weights_only=True)
    assert set(tensor_file) == {"lora_logits"}
    request = {"messages": [{"role": "user", "content": "fixture"}], "model": "fixture",
               "temperature": 0.7, "max_tokens": 2}
    responses = []
    for owner in (f.parent, replica):
        owner.reseed(210, label="same-predeclared-slot")
        response = owner.transport.complete(request, timeout_seconds=10)
        assert response["http_status"] == 200, response
        responses.append(response["body"])
    assert responses[0]["token_trace"] == responses[1]["token_trace"]
    assert responses[0]["actor_identity"] == responses[1]["actor_identity"]
    assert responses[1]["online_window_id"] == "declared-window"
    assert replica.verify_sampling_identity()["local_optimizer_updates"] == 0
    for action in (
        lambda: replica.update_window([], f.root / "forbidden-update"),
        lambda: replica.save_checkpoint(f.root / "forbidden-save"),
        lambda: replica.restore_checkpoint(f.root / "forbidden-restore"),
        lambda: replica.learning_logprobs({}),
        lambda: replica.export_sampling_snapshot(f.root / "forbidden-export"),
        lambda: replica.begin_window("other-window"),
    ):
        with pytest.raises(ValueError):
            action()
    assert not list(f.root.glob("forbidden-*"))
    with f.torch.no_grad():
        replica.actor_parameters["lora_logits"][0] += 0.1
    with pytest.raises(ValueError, match="identity"):
        replica.verify_sampling_identity()


@pytest.mark.parametrize("corruption", ["source", "profile", "snapshot"])
def test_replica_checks_metadata_and_adapter_bytes_before_loader(replica_fixture, corruption):
    f = replica_fixture
    manifest_path = f.snapshot / "manifest.json"
    manifest = read_json(manifest_path)
    if corruption == "source":
        manifest["source_identity"]["source_tree_sha256"] = "other-source"
    elif corruption == "profile":
        manifest["runtime_profile"]["devices"] = 3
    else:
        with (f.snapshot / "snapshot.pt").open("ab") as stream:
            stream.write(b"modified")
    manifest_path.write_bytes(json_bytes(manifest))
    with pytest.raises(ValueError):
        f.module.load_replica(f.snapshot, f.root / "replica")
    assert not f.called and not (f.root / "replica").exists()
