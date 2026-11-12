"""Official Qwen hybrid checkpoints using the same resident online learner.

No model-specific attention patch, task answer, tool execution, or hidden retry is
introduced here. Native XML parameter values are decoded against public schemas.
"""

import copy
import json
import re
import uuid
from pathlib import Path

from .online_training import SharedActor, recipe_config, reference, sha_file
from .storage import atomic_write, digest, json_bytes, read_json
from .training import normalize_messages

VERSION = "candidate-runtime-v0.15"
CHECKPOINTS = {
    "qwen3.5-9b": {"repo_id": "Qwen/Qwen3.5-9B",
                   "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
                   "layers": 32, "hidden_size": 4096},
    "qwen3.8-27b": {"repo_id": "Qwen/Qwen3.8-27B",
                    "revision": "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
                    "layers": 64, "hidden_size": 5120},
}
XML_SINGLE_CALL_HINT = (
    "For this declared interface, produce exactly one native <tool_call> block per decision. "
    "Use the function and parameter syntax specified above and a supplied function name. "
    "Multiple calls are rejected as a whole. Use staff_wait or staff_done with a reason "
    "when those controls are appropriate. Only the returned real tool result establishes "
    "execution; never invent a result."
)


def prepare_candidate_prompt(request, tokenizer, profile):
    messages = normalize_messages(request["messages"])
    original = copy.deepcopy(messages)
    if request.get("tools"):
        if messages and messages[0]["role"] == "system":
            messages[0]["content"] += "\n" + XML_SINGLE_CALL_HINT
        else:
            messages.insert(0, {"role": "system", "content": XML_SINGLE_CALL_HINT})
    kwargs = profile["chat_template_kwargs"]
    if kwargs.get("enable_thinking") is not False:
        raise ValueError("v0.15 candidate condition requires explicit non-thinking mode")
    rendered = tokenizer.apply_chat_template(
        messages, tools=request.get("tools", []), tokenize=False,
        add_generation_prompt=True, **kwargs,
    )
    return rendered, messages, {
        "version": VERSION, "native_tool_prompt": "official_xml_single_call",
        "single_call_hint_applied": bool(request.get("tools")),
        "chat_template_kwargs": kwargs,
        "request_sha256": digest(json_bytes(request)),
        "normalized_messages_sha256": digest(json_bytes(original)),
        "actual_prompt_messages_sha256": digest(json_bytes(messages)),
        "rendered_prompt_sha256": digest(rendered.encode()),
        "scope": "Official template plus public syntax hint; no task answer or world access",
    }


def _invalid_json_constant(value):
    raise ValueError("Non-finite JSON constant is not a native parameter value: " + value)


def _parameter_value(text, schema):
    """Decode the template's textual parameters; do not infer hidden schemas."""
    kind = schema.get("type")
    if kind == "string" or not kind:
        return text
    if kind == "boolean" and text in {"true", "false", "True", "False"}:
        return text.lower() == "true"
    try:
        value = json.loads(text, parse_constant=_invalid_json_constant)
    except json.JSONDecodeError as error:
        raise ValueError("Native parameter does not match public JSON type") from error
    allowed = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "integer": type(value) is int,
        "number": type(value) in (int, float),
        "null": value is None, "boolean": type(value) is bool,
    }
    if not allowed.get(kind, False):
        raise ValueError("Native parameter does not match public schema type " + str(kind))
    return value


def parse_candidate_generated(raw, request):
    content = raw.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip()
    blocks = list(re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", content, re.DOTALL))
    if content.count("<tool_call>") != len(blocks) or content.count("</tool_call>") != len(blocks):
        return {"role": "assistant", "content": content}, "incomplete_tool_block"
    schemas = {t["function"]["name"]: t["function"].get("parameters", {})
               for t in request.get("tools", [])}
    calls = []
    try:
        for block in blocks:
            function = re.fullmatch(r"<function=([A-Za-z_][A-Za-z0-9_.-]*)>\s*(.*?)\s*</function>",
                                    block.group(1), re.DOTALL)
            if function is None:
                raise ValueError("Expected one native function block")
            name, body = function.groups()
            params = list(re.finditer(r"<parameter=([A-Za-z_][A-Za-z0-9_.-]*)>\n?(.*?)\n?</parameter>",
                                      body, re.DOTALL))
            residue = re.sub(r"<parameter=[A-Za-z_][A-Za-z0-9_.-]*>.*?</parameter>",
                             "", body, flags=re.DOTALL)
            if residue.strip():
                raise ValueError("Unexpected text inside native function parameters")
            arguments = {}
            properties = schemas.get(name, {}).get("properties", {})
            for param in params:
                key, value = param.groups()
                if key in arguments:
                    raise ValueError("Duplicate native parameter " + key)
                arguments[key] = _parameter_value(value, properties.get(key, {}))
            calls.append({"id": "call_" + uuid.uuid4().hex, "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments, ensure_ascii=False),
            }})
    except (ValueError, TypeError) as error:
        return {"role": "assistant", "content": content}, "invalid_tool_block: " + str(error)
    message = {"role": "assistant", "content": re.sub(
        r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL).strip() if calls else content}
    if calls:
        message["tool_calls"] = calls
    return message, None


def candidate_profile(candidate_id, *, dtype="float32", devices=1):
    if candidate_id not in {"qwen3.5-9b", "qwen3.8-27b"}:
        raise ValueError("Unregistered candidate")
    if dtype not in {"float32", "bfloat16"} or type(devices) is not int or devices < 1:
        raise ValueError("Invalid declared candidate numeric profile")
    return {"version": VERSION, "candidate_id": candidate_id, "dtype": dtype,
            "devices": devices, "attention": "sdpa", "matmul_precision": "highest",
            "cudnn_allow_tf32": False,
            "chat_template_kwargs": {"enable_thinking": False, "preserve_thinking": False},
            "max_context_tokens": 16384, "max_output_tokens": 2048,
            "temperature": 0.7, "top_p": 1.0, "top_k": 0,
            "native_tool_prompt": "official_xml_single_call",
            "lora_target_modules": ["q_proj", "v_proj"],
            "lora_scope": "Full-attention projections only; DeltaNet is frozen",
            "history_policy": "Full public messages supplied to official template; non-thinking requested; preserve_thinking=False",
            "dtype_scope": "Base weights and LoRA; float32 selected-token normalization"}


GENERATION_OVERRIDES = {
    "do_sample": True, "use_cache": True, "repetition_penalty": 1.0,
    "renormalize_logits": False, "temperature": 1.0, "top_p": 1.0,
    "top_k": 0, "typical_p": 1.0,
}


def validate_generation_defaults(actual, baseline):
    """Fail closed on checkpoint defaults outside the declared sampling path."""
    allowed = set(GENERATION_OVERRIDES) | {
        "max_new_tokens", "max_length", "pad_token_id", "eos_token_id", "bos_token_id",
        "_from_model_config", "transformers_version", "_commit_hash",
    }
    differences = {key: value for key, value in actual.items()
                   if key not in allowed and value != baseline.get(key)
                   and not (key in {"output_attentions", "output_hidden_states"}
                            and (value is None or value is False))}
    if differences:
        raise ValueError("Non-neutral undeclared generation defaults: " + ", ".join(sorted(differences)))
    return True


def freeze_candidate_generation(model, tokenizer, output_budget):
    from transformers import GenerationConfig

    original = model.generation_config.to_dict()
    validate_generation_defaults(original, GenerationConfig().to_dict())
    # Prevent the library's legacy model-config synchronization from silently
    # replacing this verified configuration after SharedActor changes use_cache.
    model.generation_config._from_model_config = False
    effective = copy.deepcopy(model.generation_config)
    overrides = {**GENERATION_OVERRIDES, "max_new_tokens": output_budget,
                 "pad_token_id": tokenizer.pad_token_id}
    effective.update(**overrides)
    return {"original_generation_config": original,
            "fixed_generate_overrides": overrides,
            "effective_generation_config": effective.to_dict(),
            "custom_logits_processors": ["SamplingTrace: sole temperature=0.7"],
            "validation": "All non-overridden defaults equal installed neutral GenerationConfig",
            "dynamic_generation_config_from_model_disabled": True}


class CandidateActor(SharedActor):
    def prepare_request(self, request):
        return prepare_candidate_prompt(request, self.tokenizer, self.inference_profile)

    def parse_response(self, raw, request):
        return parse_candidate_generated(raw, request)

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
        generation_contract = freeze_candidate_generation(network, tokenizer, recipe["max_output_tokens"])
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
                       actual_float32_matmul_precision=torch.get_float32_matmul_precision(),
                       cuda_matmul_allow_tf32=torch.backends.cuda.matmul.allow_tf32,
                       actual_cudnn_allow_tf32=torch.backends.cudnn.allow_tf32,
                       checkpoint_scope="Official text backbone and LM head; unused vision/MTP excluded",
                       custom_attention_patch=False, use_kernels=False,
                       deltanet_runtime="Installed official PyTorch reference; no optional fast kernels")
        return cls(network, tokenizer, output=output, recipe=recipe, device="cuda:0",
                   inference_profile=profile, base_identity={"path": str(model_path),
                       "manifest": reference(manifest), "revision": identity.get("declared_hf_revision")})
