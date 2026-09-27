"""Real CPU tensors/sampling with an explicitly tiny loader fixture, no GPU/base claim."""

from types import SimpleNamespace

import pytest

from proworksim.storage import json_bytes, read_json


@pytest.fixture
def replica_fixture(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    from proworksim.candidate_runtime_v019 import CandidateActor, candidate_profile
    from proworksim.candidate_runtime_v0151 import candidate_profile as numeric_loader_profile
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

        def set_attn_implementation(self, value):
            # This is an explicit constructor fixture, not an attention kernel.
            self.config._attn_implementation = value

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
        # The real inherited numeric 15.1 loader strips the newer diagnostics
        # profile before constructing cls. Passing profile19 directly hid that gap.
        numeric = numeric_loader_profile(
            profile["candidate_id"], dtype=profile["dtype"], devices=profile["devices"]
        )
        assert "parser_contract" not in numeric
        return cls(TinyActor(), Tokenizer(), output=output, base_identity=base_identity,
                   inference_profile=numeric,
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


def test_official_tiny_qwen_constructor_registers_full_attention_and_mask_without_forward(tmp_path):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    if transformers.__version__ != "5.17.0":
        pytest.skip("Installed official Transformers 5.17.0 constructor control")
    from transformers import Qwen3_5ForCausalLM, Qwen3_5TextConfig
    from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS
    from transformers.masking_utils import ALL_MASK_ATTENTION_FUNCTIONS
    from peft import LoraConfig, get_peft_model
    from proworksim.candidate_runtime_v019 import CandidateActor, candidate_profile
    from proworksim.candidate_runtime_v0151 import candidate_profile as numeric_loader_profile
    from proworksim.local_model_service import sdpa_explicit_kv_attention_forward

    config = Qwen3_5TextConfig(
        vocab_size=128, hidden_size=64, intermediate_size=128, num_hidden_layers=4,
        num_attention_heads=4, num_key_value_heads=2, head_dim=16,
        linear_key_head_dim=16, linear_value_head_dim=16,
        linear_num_key_heads=2, linear_num_value_heads=2,
        layer_types=["linear_attention"] * 3 + ["full_attention"],
        rope_parameters={"rope_type": "default", "rope_theta": 10000,
                         "partial_rotary_factor": 0.5, "mrope_section": [1, 1, 2],
                         "mrope_interleaved": True},
        pad_token_id=0, eos_token_id=127,
    )
    config._attn_implementation = "sdpa"
    with torch.device("cpu"):
        base = Qwen3_5ForCausalLM(config).float()
        network = get_peft_model(base, LoraConfig(
            r=8, lora_alpha=16, lora_dropout=0, target_modules=["q_proj", "v_proj"],
            bias="none", task_type="CAUSAL_LM",
        ))
    layer_classes = [type(layer) for layer in base.model.layers]
    owner = CandidateActor(
        network, object(), output=tmp_path / "actual-tiny-constructor",
        base_identity={"manifest": {"sha256": "random-tiny-no-candidate-base"}},
        inference_profile=numeric_loader_profile("qwen3.5-9b", devices=1),
        device="cpu", torch_module=torch,
    )
    assert network.config._attn_implementation == "sdpa_explicit_kv"
    assert base.model.layers[3].self_attn.config._attn_implementation == "sdpa_explicit_kv"
    assert [type(layer) for layer in base.model.layers] == layer_classes
    assert base.config.layer_types == ["linear_attention"] * 3 + ["full_attention"]
    assert ALL_ATTENTION_FUNCTIONS["sdpa_explicit_kv"] is sdpa_explicit_kv_attention_forward
    assert ALL_MASK_ATTENTION_FUNCTIONS["sdpa_explicit_kv"] is ALL_MASK_ATTENTION_FUNCTIONS["sdpa"]
    assert owner.inference_profile["sdpa_backend_policy"] == "efficient_only_no_fallback"
    assert owner.inference_profile["matmul_precision"] == "high"
    assert owner.prefix_cache.matmul_precision == "high"
    expected = candidate_profile("qwen3.5-9b", devices=1)
    assert all(owner.inference_profile.get(key) == value for key, value in expected.items())
    assert all(p.device.type == "cpu" for p in network.parameters())


def test_numeric_loader_shape_restores_every_declared_factory_field(replica_fixture):
    from proworksim.candidate_runtime_v019 import candidate_profile
    from proworksim.candidate_runtime_v017 import PARSER_CONTRACT

    owner = replica_fixture.parent
    expected = candidate_profile("qwen3.5-9b", devices=2)
    assert all(owner.inference_profile.get(key) == value for key, value in expected.items())
    assert owner.inference_profile["parser_contract"] == PARSER_CONTRACT
    assert owner.inference_profile["parser_contract"] is not PARSER_CONTRACT
    assert replica_fixture.module._runtime_profile(owner.inference_profile) == expected
