"""Loopback-only Qwen HTTP inference, with real token records and no world access.

The process only loads declared weights and receives public model requests. It
never opens a world, calls business algorithms, or invents tool responses.
"""

import argparse
import copy
import gc
import math
import json
import os
import queue
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .storage import atomic_write, digest, json_bytes
from .training import normalize_messages


def parse_generated(text):
    """Parse every Qwen tool block or reject all; preserve original generation."""
    content = text.replace("<|im_end|>", "").replace("<|endoftext|>", "").strip()
    blocks = list(re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", content, re.DOTALL))
    if content.count("<tool_call>") != len(blocks) or content.count("</tool_call>") != len(blocks):
        return {"role": "assistant", "content": content}, "incomplete_tool_block"
    calls = []
    for block in blocks:
        try:
            item = json.loads(block.group(1))
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("arguments"), dict)
            ):
                raise ValueError("Tool block requires name and object arguments")
            calls.append(
                {
                    "id": "call_" + uuid.uuid4().hex,
                    "type": "function",
                    "function": {
                        "name": item["name"],
                        "arguments": json.dumps(item["arguments"], ensure_ascii=False),
                    },
                }
            )
        except (ValueError, TypeError) as error:
            return {"role": "assistant", "content": content}, "invalid_tool_block: " + str(error)
    message = {
        "role": "assistant",
        "content": re.sub(r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL).strip()
        if calls
        else content,
    }
    if calls:
        message["tool_calls"] = calls
    return message, None


NATIVE_SINGLE_CALL_HINT = (
    "For this declared interface, produce exactly one native <tool_call> block per decision. "
    "Use a supplied function name and its argument object. Multiple calls are rejected as a whole. "
    "Use staff_wait or staff_done with a reason when those controls are appropriate. "
    "Only the returned real tool result establishes execution; never invent a result."
)


def prepare_prompt(request, tokenizer, native_tool_prompt="template_default"):
    """Exact service-side input projection, recorded independently of HTTP input."""
    if native_tool_prompt not in {"template_default", "single_call"}:
        raise ValueError("Unknown frozen native tool prompt")
    messages = normalize_messages(request["messages"])
    original = copy.deepcopy(messages)
    applied = bool(request.get("tools")) and native_tool_prompt == "single_call"
    if applied:
        if messages and messages[0]["role"] == "system":
            messages[0]["content"] += "\n" + NATIVE_SINGLE_CALL_HINT
        else:
            messages.insert(0, {"role": "system", "content": NATIVE_SINGLE_CALL_HINT})
    rendered = tokenizer.apply_chat_template(
        messages, tools=request.get("tools", []), tokenize=False, add_generation_prompt=True
    )
    projection = {
        "version": "local-prompt-projection-v0.12",
        "native_tool_prompt": native_tool_prompt,
        "single_call_hint_applied": applied,
        "request_sha256": digest(json_bytes(request)),
        "normalized_messages_sha256": digest(json_bytes(original)),
        "actual_prompt_messages_sha256": digest(json_bytes(messages)),
        "rendered_prompt_sha256": digest(rendered.encode()),
        "scope": "Normalization and optional frozen public syntax hint only; no task answer or world access",
    }
    return rendered, messages, projection


def completed_tokens(tokens, eos_ids):
    eos_ids = {eos_ids} if isinstance(eos_ids, int) else set(eos_ids)
    end = next((index for index, token in enumerate(tokens) if token in eos_ids), None)
    return (tokens[: end + 1], True) if end is not None else (tokens, False)


class SamplingTrace:
    """Record probabilities from the actual sampling scores, one step in memory.

    This processor applies the sole temperature transform itself. Generation uses
    temperature=1, top_p=1, top_k=0 and no repetition penalty. It stores only the
    chosen probabilities when the next token becomes known, not all vocab scores.
    """

    def __init__(self, temperature):
        self.temperature = temperature
        self.previous = None
        self.selected = []

    def __call__(self, input_ids, scores):
        if self.previous is not None:
            self.selected.append(self.previous.gather(1, input_ids[:, -1:]).squeeze(1))
        scaled = scores / self.temperature if self.temperature > 0 else scores
        self.previous = scaled.log_softmax(dim=-1)
        return scaled

    def finish(self, generated):
        import torch

        self.selected.append(self.previous.gather(1, generated[:, -1:]).squeeze(1))
        result = torch.stack(self.selected, dim=1).detach().cpu().tolist()
        self.previous = None
        # Greedy argmax is not a stochastic categorical rollout for RL.
        return result if self.temperature > 0 else None


def sdpa_explicit_kv_attention_forward(
    module,
    query,
    key,
    value,
    attention_mask,
    dropout=0.0,
    scaling=None,
    is_causal=None,
    **kwargs,
):
    """Preserve grouped KV semantics, require the efficient CUDA kernel.

    Only this invocation expands KV heads; the model's original four-head cache
    stays unchanged. There is no math, eager, lower-precision or CPU fallback.
    """
    import torch
    from torch.nn.attention import SDPBackend, sdpa_kernel

    if any(tensor.device.type != "cuda" for tensor in (query, key, value)):
        raise ValueError("sdpa_explicit_kv requires CUDA; no CPU math fallback")
    if kwargs.get("output_attentions", False) or kwargs.get("head_mask") is not None:
        raise ValueError("sdpa_explicit_kv does not produce attention weights or head masks")
    groups = module.num_key_value_groups
    if (
        type(groups) is not int
        or groups < 1
        or key.shape[1] != value.shape[1]
        or query.shape[1] != key.shape[1] * groups
    ):
        raise ValueError("Declared query/KV head grouping differs from the actual tensors")
    key = key.repeat_interleave(groups, dim=1)
    value = value.repeat_interleave(groups, dim=1)
    if attention_mask is not None and attention_mask.ndim == 4:
        attention_mask = attention_mask[:, :, :, : key.shape[-2]]
    if is_causal is None:
        is_causal = (
            query.shape[2] > 1 and attention_mask is None and getattr(module, "is_causal", True)
        )
    if torch.jit.is_tracing() and hasattr(is_causal, "item"):
        is_causal = is_causal.item()
    with sdpa_kernel(backends=[SDPBackend.EFFICIENT_ATTENTION]):
        result = torch.nn.functional.scaled_dot_product_attention(
            query,
            key,
            value,
            attn_mask=attention_mask,
            dropout_p=dropout,
            scale=scaling,
            is_causal=is_causal,
            enable_gqa=False,
        )
    return result.transpose(1, 2).contiguous(), None


def configure_attention_runtime(attention, matmul_precision="highest"):
    """Explicit process-local runtime setup; never edits installed libraries."""
    import torch

    if attention not in {"sdpa", "eager", "sdpa_explicit_kv"}:
        raise ValueError("Unknown frozen attention profile")
    if matmul_precision not in {"highest", "high"}:
        raise ValueError("Unknown frozen float32 matmul precision")
    torch.set_float32_matmul_precision(matmul_precision)
    if attention == "sdpa_explicit_kv":
        from transformers.masking_utils import ALL_MASK_ATTENTION_FUNCTIONS, AttentionMaskInterface
        from transformers.modeling_utils import AttentionInterface

        AttentionInterface.register(attention, sdpa_explicit_kv_attention_forward)
        # Keep exactly the installed SDPA mask/causal/position semantics. A custom
        # attention name without its mask registration would silently drop masks.
        AttentionMaskInterface.register(attention, ALL_MASK_ATTENTION_FUNCTIONS["sdpa"])
    return {
        "attention_adapter_version": "explicit-kv-efficient-v0.12.1"
        if attention == "sdpa_explicit_kv"
        else None,
        "sdpa_backend_policy": "efficient_only_no_fallback"
        if attention == "sdpa_explicit_kv"
        else "installed_library_default",
        "kv_head_handling": "repeat_interleave_in_attention_only"
        if attention == "sdpa_explicit_kv"
        else "installed_library_default",
        "declared_matmul_precision": matmul_precision,
        "actual_float32_matmul_precision": torch.get_float32_matmul_precision(),
        "cuda_matmul_allow_tf32": torch.backends.cuda.matmul.allow_tf32,
        "cudnn_allow_tf32": torch.backends.cudnn.allow_tf32,
        "nvidia_tf32_override": os.getenv("NVIDIA_TF32_OVERRIDE"),
    }


def startup_reserve_value(value):
    """CLI parser and helper boundary share the same finite 0..64 GiB rule."""
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("startup-reserve-gib must be finite in [0,64]") from error
    if isinstance(value, bool) or not math.isfinite(result) or not 0 <= result <= 64:
        raise argparse.ArgumentTypeError("startup-reserve-gib must be finite in [0,64]")
    return result


def cuda_resource_snapshot(torch):
    free, total = torch.cuda.mem_get_info()
    return {
        "allocated_bytes": torch.cuda.memory_allocated(),
        "reserved_bytes": torch.cuda.memory_reserved(),
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        "device_free_bytes": free,
        "device_total_bytes": total,
    }


def load_with_startup_reservation(load_cpu, *, torch, reserve_gib, record_path, on_device=None):
    """Reserve own CUDA capacity, CPU-load, then reuse own allocator cache.

    No other process is controlled. No empty_cache call releases the reservation
    between the CPU load and moving weights. Resource peaks are not compute peaks.
    """
    reserve_gib = startup_reserve_value(reserve_gib)
    record = {
        "version": "startup-resource-v0.12.1",
        "started_at": time.time(),
        "pid": os.getpid(),
        "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES"),
        "requested_reserve_gib": reserve_gib,
        "requested_reserve_bytes": int(reserve_gib * 1024**3),
        "allocator_environment": {
            key: os.getenv(key) for key in ("PYTORCH_CUDA_ALLOC_CONF", "PYTORCH_ALLOC_CONF")
        },
        "other_processes_controlled": False,
        "empty_cache_used": False,
        "scope": "Startup capacity reservation/loading only; separate from generation compute memory",
        "stages": [],
    }
    _reservation = None

    def save_stage(stage):
        record["stages"].append(
            {"stage": stage, "at": time.time(), **cuda_resource_snapshot(torch)}
        )
        atomic_write(record_path, json_bytes(record))

    atomic_write(record_path, json_bytes(record))
    try:
        save_stage("before_reservation")
        torch.cuda.reset_peak_memory_stats()
        if record["requested_reserve_bytes"]:
            _reservation = torch.empty(
                (record["requested_reserve_bytes"],), dtype=torch.uint8, device="cuda"
            )
        save_stage("reservation_held")
        network = load_cpu()
        save_stage("cpu_weights_loaded_reservation_held")
        _reservation = None
        gc.collect()
        save_stage("reservation_released_to_own_allocator_cache")
        network = network.to("cuda").eval()
        if on_device is not None:
            network = on_device(network)
        save_stage("weights_on_device")
        record["startup_peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
        record["startup_peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
        torch.cuda.reset_peak_memory_stats()
        save_stage("compute_peak_counters_reset")
        record.update(status="ready", ended_at=time.time())
        atomic_write(record_path, json_bytes(record))
        return network, record
    except Exception as error:
        _reservation = None
        gc.collect()
        record.update(
            status="startup_error",
            ended_at=time.time(),
            error={"type": type(error).__name__, "message": str(error)},
        )
        try:
            save_stage("startup_failed_reservation_released")
        except Exception as snapshot_error:
            record["resource_snapshot_error"] = {
                "type": type(snapshot_error).__name__,
                "message": str(snapshot_error),
            }
        atomic_write(record_path, json_bytes(record))
        raise


class LocalInference:
    def __init__(self, args):
        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.args = args
        self.torch = torch
        self.output = Path(args.output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token_id = self.tokenizer.eos_token_id
        torch.set_num_threads(8)
        torch.manual_seed(args.seed)
        numerical_profile = configure_attention_runtime(args.attention, args.matmul_precision)
        self.adapter_identity = None

        def load_cpu():
            return AutoModelForCausalLM.from_pretrained(
                args.model,
                local_files_only=True,
                dtype=getattr(torch, args.dtype),
                attn_implementation=args.attention,
            )

        def attach_adapter(network):
            if args.adapter:
                import hashlib
                from peft import PeftModel

                adapter = Path(args.adapter)
                self.adapter_identity = {
                    p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in adapter.iterdir()
                    if p.is_file()
                }
                return PeftModel.from_pretrained(network, adapter, is_trainable=False).eval()
            return network

        startup_path = self.output / "startup-resource.json"
        self.network, startup_resource = load_with_startup_reservation(
            load_cpu,
            torch=torch,
            reserve_gib=args.startup_reserve_gib,
            record_path=startup_path,
            on_device=attach_adapter,
        )
        self.policy_version = (
            args.revision
            if self.adapter_identity is None
            else args.revision
            + "+"
            + __import__("hashlib").sha256(json_bytes(self.adapter_identity)).hexdigest()
        )
        self.inference_profile = {
            "version": "local-inference-profile-v0.12.1",
            "dtype": args.dtype,
            "attention": args.attention,
            "actual_parameter_dtype": str(next(self.network.parameters()).dtype),
            "actual_attention": self.network.config._attn_implementation,
            "native_tool_prompt": args.native_tool_prompt,
            "max_batch": args.max_batch,
            "max_context_tokens": args.max_context,
            "seed": args.seed,
            **numerical_profile,
        }
        self.pending = queue.Queue(maxsize=24)
        self.batch_index = 0
        self.manifest = {
            "service": "loopback-qwen-transformers-v0.12",
            "model": args.model_id,
            "pid": os.getpid(),
            "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES"),
            "weights": str(Path(args.model).resolve()),
            "weight_revision": args.revision,
            "adapter": args.adapter,
            "adapter_identity": self.adapter_identity,
            "policy_version": self.policy_version,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "seed": args.seed,
            "sampling": "one shared RNG stream; batching/order recorded, not per-episode deterministic",
            "max_context_tokens": args.max_context,
            "max_batch": args.max_batch,
            "base_generation_config": self.network.generation_config.to_dict(),
            "inference_profile": self.inference_profile,
            "inference_profile_sha256": digest(json_bytes(self.inference_profile)),
            "startup_resource": startup_resource,
            "startup_resource_reference": {
                "path": str(startup_path.resolve()),
                "sha256": digest(startup_path.read_bytes()),
                "bytes": startup_path.stat().st_size,
            },
            "source_sha256": __import__("hashlib").sha256(Path(__file__).read_bytes()).hexdigest(),
            "weight_files": {
                p.name: {"bytes": p.stat().st_size, "mtime_ns": p.stat().st_mtime_ns}
                for p in Path(args.model).iterdir()
                if p.is_file()
            },
            "policy_probabilities": "chosen-token log-probabilities captured from actual temperature-scaled sampling logits; greedy requests keep None",
        }
        atomic_write(self.output / "service.json", json_bytes(self.manifest))
        threading.Thread(target=self._loop, daemon=True).start()

    def enqueue(self, request):
        if request.get("model") != self.args.model_id:
            return 400, {"error": {"code": "unknown_model", "message": "Declared model differs"}}
        if request.get("stream"):
            return 400, {"error": {"code": "unsupported_stream", "message": "Non-stream only"}}
        try:
            maximum = request.get("max_tokens", 8192)
            if type(maximum) is not int or not 1 <= maximum <= 8192:
                raise ValueError("max_tokens outside declared service range")
            rendered, prompt_messages, projection = prepare_prompt(
                request, self.tokenizer, self.args.native_tool_prompt
            )
            ids = self.tokenizer(rendered, add_special_tokens=False)["input_ids"]
            if len(ids) + maximum > self.args.max_context:
                return 400, {
                    "error": {
                        "code": "context_length_exceeded",
                        "message": "No history truncation",
                        "prompt_tokens": len(ids),
                        "requested_output": maximum,
                        "context_limit": self.args.max_context,
                    }
                }
        except (ValueError, TypeError, KeyError) as error:
            return 400, {"error": {"code": "invalid_request", "message": str(error)}}
        work = {
            "request": copy.deepcopy(request),
            "rendered": rendered,
            "input_ids": ids,
            "prompt_messages": prompt_messages,
            "prompt_projection": projection,
            "maximum": maximum,
            "started": time.time(),
            "ready": threading.Event(),
        }
        try:
            self.pending.put(work, timeout=1)
        except queue.Full:
            return 429, {"error": {"code": "queue_full", "message": "Local inference queue full"}}
        # The caller's HTTP timeout is independent; a disconnected generation is
        # still retained in the service ledger, with its actually consumed tokens.
        work["ready"].wait()
        return work["status"], work["response"]

    def _loop(self):
        while True:
            batch = [self.pending.get()]
            time.sleep(0.1)
            while len(batch) < self.args.max_batch:
                try:
                    batch.append(self.pending.get_nowait())
                except queue.Empty:
                    break
            self.batch_index += 1
            try:
                self._generate(batch)
            except Exception as error:
                for work in batch:
                    work["status"] = 503
                    work["response"] = {
                        "error": {
                            "code": "local_inference_error",
                            "type": type(error).__name__,
                            "message": str(error),
                        }
                    }
                    atomic_write(
                        self.output / ("error-" + uuid.uuid4().hex + ".json"),
                        json_bytes({"request": work["request"], "response": work["response"]}),
                    )
                    work["ready"].set()

    def _generate(self, batch):
        torch = self.torch
        # Different maximums/temperatures are handled in separate real generations,
        # avoiding unannounced output-budget or sampling changes.
        groups = {}
        for work in batch:
            config = (work["maximum"], float(work["request"].get("temperature", 0.3)))
            groups.setdefault(config, []).append(work)
        for (maximum, temperature), group in groups.items():
            group_id = uuid.uuid4().hex
            inputs = self.tokenizer(
                [w["rendered"] for w in group],
                padding=True,
                add_special_tokens=False,
                return_tensors="pt",
            ).to("cuda")
            width = inputs.input_ids.shape[1]
            options = {
                "max_new_tokens": maximum,
                "do_sample": temperature > 0,
                "pad_token_id": self.tokenizer.pad_token_id,
                "use_cache": True,
                "repetition_penalty": 1.0,
                "renormalize_logits": False,
            }
            if temperature > 0:
                options.update(temperature=1.0, top_p=1.0, top_k=0, typical_p=1.0)
            trace = SamplingTrace(temperature)
            options["logits_processor"] = [trace]
            torch.cuda.reset_peak_memory_stats()
            compute_baseline = cuda_resource_snapshot(torch)
            started = time.monotonic()
            with torch.inference_mode():
                generated = self.network.generate(**inputs, **options)
            sampled_logprobs = trace.finish(generated)
            elapsed = time.monotonic() - started
            compute_resource = cuda_resource_snapshot(torch)
            compute_resource["baseline_allocated_bytes"] = compute_baseline["allocated_bytes"]
            compute_resource["additional_peak_allocated_bytes"] = max(
                0, compute_resource["peak_allocated_bytes"] - compute_baseline["allocated_bytes"]
            )
            compute_resource["scope"] = (
                "Actual generation group after a fresh peak reset; allocated peak excludes the earlier "
                "startup reservation. Reserved totals may include reused startup cache. Shared by all "
                "rows of this same batch, not additive per response."
            )
            for index, work in enumerate(group):
                tokens = generated[index, width:].tolist()
                tokens, finished = completed_tokens(
                    tokens, self.network.generation_config.eos_token_id
                )
                raw = self.tokenizer.decode(tokens, skip_special_tokens=False)
                message, parse_error = parse_generated(raw)
                call_id = "local_" + uuid.uuid4().hex
                response = {
                    "id": call_id,
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": self.args.model_id,
                    "system_fingerprint": self.policy_version,
                    "choices": [
                        {
                            "index": 0,
                            "message": message,
                            "finish_reason": "tool_calls"
                            if finished and message.get("tool_calls")
                            else "stop"
                            if finished
                            else "length",
                            "logprobs": None,
                        }
                    ],
                    "usage": {
                        "prompt_tokens": len(work["input_ids"]),
                        "completion_tokens": len(tokens),
                        "total_tokens": len(work["input_ids"]) + len(tokens),
                    },
                    "raw_generated_text": raw,
                    "protocol_parse_error": parse_error,
                    "inference_profile": self.inference_profile,
                    "inference_profile_sha256": digest(json_bytes(self.inference_profile)),
                    "prompt_projection": work["prompt_projection"],
                    "token_trace": {
                        "input_ids": work["input_ids"],
                        "output_ids": tokens,
                        "input_mask": [0] * len(work["input_ids"]),
                        "output_mask": [1] * len(tokens),
                        "behavior_logprobs": sampled_logprobs[index][: len(tokens)]
                        if sampled_logprobs
                        else None,
                        "sampling_temperature": temperature,
                        "sampling_top_p": 1.0,
                        "sampling_top_k": 0,
                        "source": "actual generation token IDs and sampling logits, not retokenized text",
                    },
                    "effective_generation": {
                        key: value for key, value in options.items() if key != "logits_processor"
                    },
                    "service_record": {
                        "batch_index": self.batch_index,
                        "batch_size": len(group),
                        "batch_group_id": group_id,
                        "batch_row_index": index,
                        "prefix_width": width,
                        "batch_seconds": elapsed,
                        "compute_resource": compute_resource,
                        "queue_and_generation_seconds": time.time() - work["started"],
                    },
                }
                atomic_write(
                    self.output / (call_id + ".json"),
                    json_bytes(
                        {
                            "request": work["request"],
                            "rendered_prompt": work["rendered"],
                            "actual_prompt_messages": work["prompt_messages"],
                            "prompt_projection": work["prompt_projection"],
                            "response": response,
                        }
                    ),
                )
                work.update(status=200, response=response)
                work["ready"].set()


def service_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--model-id", default="Qwen2.5-7B-Instruct")
    parser.add_argument("--revision", required=True)
    parser.add_argument(
        "--adapter", help="Optional independently saved LoRA; base weights are never overwritten"
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", type=int, default=18761)
    parser.add_argument("--max-context", type=int, default=32768)
    parser.add_argument("--max-batch", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260924)
    parser.add_argument("--dtype", choices=("bfloat16", "float32"), default="bfloat16")
    parser.add_argument(
        "--attention", choices=("sdpa", "eager", "sdpa_explicit_kv"), default="sdpa"
    )
    parser.add_argument(
        "--native-tool-prompt",
        choices=("template_default", "single_call"),
        default="template_default",
    )
    parser.add_argument("--matmul-precision", choices=("highest", "high"), default="highest")
    parser.add_argument("--startup-reserve-gib", type=startup_reserve_value, default=0.0)
    return parser


def main():
    parser = service_parser()
    args = parser.parse_args()
    if args.max_batch < 1 or args.max_context < 1:
        parser.error("max-batch and max-context must be positive")
    inference = LocalInference(args)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, payload):
            data = json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path == "/v1/models":
                return self.respond(200, {"object": "list", "data": [inference.manifest]})
            self.respond(404, {"error": "unknown route"})

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                return self.respond(404, {"error": "unknown route"})
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 2_000_000:
                    raise ValueError("Request byte limit")
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise ValueError("Request object required")
            except (ValueError, TypeError) as error:
                return self.respond(
                    400, {"error": {"code": "invalid_request", "message": str(error)}}
                )
            status, response = inference.enqueue(request)
            self.respond(status, response)

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(json.dumps({"status": "ready", "port": args.port, "model": args.model_id}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
