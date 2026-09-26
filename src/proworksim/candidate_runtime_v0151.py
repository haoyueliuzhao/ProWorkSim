"""Explicit native chat termination for the frozen Qwen hybrid checkpoints.

v0.15 remains available as historical source. This profile changes stopping only;
all sampling, templates, model weights and training hyperparameters are retained.
"""
import copy
from pathlib import Path

from .candidate_runtime_v015 import (
    CHECKPOINTS, CandidateActor as PreviousCandidateActor,
    candidate_profile as previous_profile,
    freeze_candidate_generation as previous_generation_contract,
)
from .online_training import recipe_config, reference, sha_file
from .storage import atomic_write, digest, json_bytes, read_json

VERSION = "candidate-runtime-v0.15.1"
CHAT_STOP = {
    "version": "native-chat-stop-v0.15.1",
    "native_end_token": "<|im_end|>", "native_end_token_id": 248046,
    "end_of_text_token": "<|endoftext|>", "end_of_text_token_id": 248044,
    "eos_token_ids": [248046, 248044],
    "source": "Registered official tokenizer EOS, token vocabulary and assistant chat-template terminator",
    "forbid_tokens_after_first_declared_eos": True,
    "require_raw_output_ids_equal_training_output_ids": True,
}


def candidate_profile(candidate_id, *, dtype="float32", devices=1):
    profile = previous_profile(candidate_id, dtype=dtype, devices=devices)
    profile.update(version=VERSION, chat_stop_contract=copy.deepcopy(CHAT_STOP))
    return profile


def freeze_chat_generation(model, tokenizer, output_budget, profile, source_files):
    contract = previous_generation_contract(model, tokenizer, output_budget)
    declared = profile["chat_stop_contract"]
    native, eot = declared["native_end_token"], declared["end_of_text_token"]
    native_id, eot_id = tokenizer.convert_tokens_to_ids(native), tokenizer.convert_tokens_to_ids(eot)
    if (tokenizer.eos_token != native or tokenizer.eos_token_id != native_id
            or native_id != declared["native_end_token_id"]
            or eot_id != declared["end_of_text_token_id"]
            or tokenizer(native, add_special_tokens=False)["input_ids"] != [native_id]
            or tokenizer(eot, add_special_tokens=False)["input_ids"] != [eot_id]):
        raise ValueError("Actual official tokenizer does not satisfy registered chat-stop IDs")
    rendered = tokenizer.apply_chat_template([
        {"role": "user", "content": "Chat terminator metadata probe."},
        {"role": "assistant", "content": "Recorded."}], tokenize=False,
        add_generation_prompt=False, **profile["chat_template_kwargs"])
    if not rendered.rstrip().endswith(native):
        raise ValueError("Official assistant template does not terminate with the declared chat marker")
    original = model.generation_config.eos_token_id
    original_ids = [original] if isinstance(original, int) else list(original or [])
    resolved = [native_id, eot_id]
    if any(token not in resolved for token in original_ids):
        raise ValueError("Checkpoint declares an unregistered extra stop token")
    if resolved != declared["eos_token_ids"]:
        raise ValueError("Resolved EOS sequence differs from frozen chat-stop contract")
    model.generation_config.eos_token_id = resolved
    model.generation_config._from_model_config = False
    effective = copy.deepcopy(model.generation_config)
    effective.update(**contract["fixed_generate_overrides"])
    eos_contract = {
        "version": declared["version"], "declared": copy.deepcopy(declared),
        "actual_tokenizer_eos_token": tokenizer.eos_token,
        "actual_tokenizer_eos_token_id": tokenizer.eos_token_id,
        "actual_marker_ids": {native: native_id, eot: eot_id},
        "original_model_generation_eos_ids": original_ids,
        "effective_model_generation_eos_ids": resolved,
        "assistant_template_probe_sha256": digest(rendered.encode()),
        "official_source_files": {name: source_files[name] for name in
                                  ("tokenizer_config.json", "tokenizer.json", "chat_template.jinja")},
        "scope": "Real generator stopping before parser; no tail cropping or old trace correction",
    }
    contract.update(effective_generation_config=effective.to_dict(),
        fixed_generation_config_overrides={"eos_token_id": resolved},
        chat_stop_contract=eos_contract)
    return contract, eos_contract


def inspect_chat_stop(body, profile):
    trace = body.get("token_trace", {}) if isinstance(body, dict) else {}
    raw, retained = trace.get("raw_output_ids"), trace.get("output_ids")
    raw_logps, retained_logps = trace.get("raw_behavior_logprobs"), trace.get("behavior_logprobs")
    declared = profile["chat_stop_contract"]
    stops = declared["eos_token_ids"]
    positions = [i for i, token in enumerate(raw or []) if token in stops]
    native_positions = [i for i, token in enumerate(raw or []) if token == declared["native_end_token_id"]]
    raw_valid = isinstance(raw, list) and bool(raw)
    passed = (raw_valid and raw == retained and isinstance(raw_logps, list)
              and raw_logps == retained_logps and len(raw_logps) == len(raw)
              and bool(positions) and positions[0] == len(raw)-1)
    return {"version": declared["version"], "passed": bool(passed),
        "raw_output_tokens": len(raw) if isinstance(raw, list) else None,
        "first_declared_eos_position": positions[0] if positions else None,
        "first_native_chat_end_position": native_positions[0] if native_positions else None,
        "raw_ids_equal_retained": raw_valid and raw == retained,
        "raw_logps_equal_retained": isinstance(raw_logps, list) and raw_logps == retained_logps,
        "native_end_present": bool(native_positions),
        "core_generation_stop_check": body.get("generation_stop_check") if isinstance(body, dict) else None,
        "scope": "Checks actual pre-trimming generation IDs; absence of observed EOS is not a passed calibration"}


class CandidateActor(PreviousCandidateActor):
    @classmethod
    def from_candidate(cls, model_path, *, manifest, profile, output, recipe=None):
        import torch
        import transformers
        import peft
        from transformers import AutoConfig, AutoTokenizer, Qwen3_5ForCausalLM
        from peft import LoraConfig, get_peft_model

        profile = copy.deepcopy(profile)
        expected = candidate_profile(profile["candidate_id"], dtype=profile["dtype"],
                                     devices=profile["devices"])
        if profile != expected:
            raise ValueError("Candidate profile contains undeclared changes")
        recipe = recipe_config(recipe)
        if (recipe["max_length"] != profile["max_context_tokens"]
                or recipe["max_output_tokens"] != profile["max_output_tokens"]
                or recipe["temperature"] != profile["temperature"]):
            raise ValueError("Recipe differs from declared candidate interface budget")
        model_path = Path(model_path).resolve()
        identity = read_json(Path(manifest))
        registered = CHECKPOINTS[profile["candidate_id"]]
        if (identity.get("repo_id") != registered["repo_id"]
                or identity.get("declared_hf_revision") != registered["revision"]):
            raise ValueError("Candidate label differs from frozen official checkpoint identity")
        files = identity.get("files", {})
        if not files or not any(name.endswith(".safetensors") for name in files):
            raise ValueError("Complete original checkpoint manifest required")
        for name, record in files.items():
            path = (model_path / name).resolve()
            if (not path.is_relative_to(model_path) or path.stat().st_size != record["bytes"]
                    or sha_file(path) != record["sha256"]):
                raise ValueError("Candidate checkpoint identity differs: " + name)
        if torch.cuda.device_count() < profile["devices"]:
            raise ValueError("Declared CUDA devices unavailable; no CPU/offload fallback")
        torch.manual_seed(recipe["seed"])
        torch.set_num_threads(8)
        torch.set_float32_matmul_precision("highest")
        torch.backends.cudnn.allow_tf32 = False
        config = AutoConfig.from_pretrained(model_path, local_files_only=True)
        if config.model_type != "qwen3_5":
            raise ValueError("Candidate requires official qwen3_5 hybrid architecture")
        text_config = config.get_text_config()
        if (text_config.num_hidden_layers != registered["layers"]
                or text_config.hidden_size != registered["hidden_size"]
                or text_config.layer_types != (["linear_attention"]*3+["full_attention"])*(registered["layers"]//4)):
            raise ValueError("Candidate architecture differs from frozen official profile")
        layers = text_config.num_hidden_layers
        devices = profile["devices"]
        # Explicit contiguous model parallelism, no inference CPU/disk offload.
        device_map = {"model.embed_tokens": 0, "model.norm": devices - 1,
                      "model.rotary_emb": 0, "lm_head": devices - 1}
        for i in range(layers):
            device_map[f"model.layers.{i}"] = min(i * devices // layers, devices - 1)
        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        tokenizer.padding_side = "left"
        if tokenizer.pad_token_id is None:
            tokenizer.pad_token_id = tokenizer.eos_token_id
        output = Path(output)
        load_path = output.parent / (output.name + "-model-loading.json")
        if output.exists() or load_path.exists():
            raise FileExistsError("Candidate owner/loading outputs already exist")
        network, loading_info = Qwen3_5ForCausalLM.from_pretrained(
            model_path, config=text_config, local_files_only=True,
            dtype=getattr(torch, profile["dtype"]), attn_implementation="sdpa",
            device_map=device_map, output_loading_info=True, use_kernels=False,
        )
        loading_info = {k: sorted(v) if isinstance(v, set) else v
                        for k, v in loading_info.items()}
        original_keys = read_json(model_path / "model.safetensors.index.json")["weight_map"]
        unused_keys = [k for k in original_keys if k.startswith(("model.visual.", "mtp."))]
        load_record = {"loading_info": loading_info, "unused_original_keys": unused_keys,
                       "original_tensor_count": len(original_keys),
                       "actual_model_parameter_count": sum(p.numel() for p in network.parameters()),
                       "text_prefix_conversion": "Installed official qwen3_5_text PrefixChange removes language_model",
                       "actual_device_map": device_map}
        atomic_write(load_path, json_bytes(load_record))
        if (loading_info.get("missing_keys") or loading_info.get("mismatched_keys")
                or loading_info.get("error_msgs") or any(
                    not key.startswith(("model.visual.", "mtp."))
                    for key in loading_info.get("unexpected_keys", []))):
            raise ValueError("Official text checkpoint did not load exactly; inspect loading record")
        generation_contract, eos_contract = freeze_chat_generation(
            network, tokenizer, recipe["max_output_tokens"], profile, files)
        atomic_write(output.parent / (output.name + "-eos-contract.json"), json_bytes(eos_contract))
        atomic_write(output.parent / (output.name + "-generation-contract.json"), json_bytes(generation_contract))
        network = get_peft_model(network, LoraConfig(
            r=8, lora_alpha=16, lora_dropout=0, target_modules=profile["lora_target_modules"],
            bias="none", task_type="CAUSAL_LM",
        ))
        matched = [name for name, module in network.named_modules() if hasattr(module, "lora_A")]
        if len(matched) != 2 * sum(kind == "full_attention" for kind in text_config.layer_types):
            raise ValueError("Unexpected LoRA matched modules in candidate architecture")
        profile.update(torch=str(torch.__version__), transformers=str(transformers.__version__),
                       peft=str(peft.__version__), actual_device_map=device_map,
                       actual_lora_modules=matched, loading_info_sha256=digest(json_bytes(load_record)),
                       generation_contract_sha256=digest(json_bytes(generation_contract)),
                       eos_contract_sha256=digest(json_bytes(eos_contract)),
                       actual_float32_matmul_precision=torch.get_float32_matmul_precision(),
                       cuda_matmul_allow_tf32=torch.backends.cuda.matmul.allow_tf32,
                       actual_cudnn_allow_tf32=torch.backends.cudnn.allow_tf32,
                       checkpoint_scope="Official text backbone and LM head; unused vision/MTP excluded",
                       custom_attention_patch=False, use_kernels=False,
                       deltanet_runtime="Installed official PyTorch reference; no optional fast kernels")
        return cls(network, tokenizer, output=output, recipe=recipe, device="cuda:0",
                   inference_profile=profile, base_identity={"path": str(model_path),
                       "manifest": reference(manifest), "revision": identity.get("declared_hf_revision")})
