"""A real LoRA update/save/reload/environment smoke test; not a learning-gain study."""

import argparse
import gc
import json
import math
import time
from pathlib import Path

import torch
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

from proworksim.audit import code_identity
from proworksim.compiler import compile_world
from proworksim.designer import design
from proworksim.kernel import World
from proworksim.runtime import run_model
from proworksim.storage import Store, atomic_write, json_bytes
from proworksim.training import LocalModelBackend, adapter_digest, load_training_records
from proworksim.validation import evaluate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--model", required=True)
    parser.add_argument("--exports", nargs="+", required=True)
    parser.add_argument("--steps", type=int, default=2)
    parser.add_argument("--max-length", type=int, default=8192)
    parser.add_argument("--max-turns", type=int, default=12)
    args = parser.parse_args()
    destination = Path(args.output)
    if destination.exists():
        parser.error("Output destination must not exist")
    if args.steps < 1:
        parser.error("steps must be positive")
    destination.mkdir(parents=True)
    torch.manual_seed(20260922)
    torch.set_num_threads(8)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    rows, excluded = load_training_records(tokenizer, args.exports, args.max_length)
    atomic_write(
        destination / "tokenized.json", json_bytes({"records": rows, "excluded": excluded})
    )
    print(
        json.dumps(
            {
                "usable_records": len(rows),
                "supervised_tokens": sum(r["target_tokens"] for r in rows),
            }
        ),
        flush=True,
    )
    network = AutoModelForCausalLM.from_pretrained(
        args.model, local_files_only=True, torch_dtype=torch.bfloat16, attn_implementation="sdpa"
    ).to("cuda")
    network.config.use_cache = False
    model = get_peft_model(
        network,
        LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0,
            target_modules=["q_proj", "v_proj"],
            task_type="CAUSAL_LM",
        ),
    )
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4)
    before = adapter_digest(model)
    step_losses = []
    started = time.monotonic()

    def batch(row):
        return {
            "input_ids": torch.tensor([row["input_ids"]], device="cuda"),
            "labels": torch.tensor([row["labels"]], device="cuda"),
        }

    model.train()
    for step in range(args.steps):
        optimizer.zero_grad(set_to_none=True)
        total = 0
        for row in rows:
            loss = model(**batch(row)).loss
            if not torch.isfinite(loss):
                raise ValueError("Non-finite training loss")
            (loss * row["weight"]).backward()
            total += float(loss.detach()) * row["weight"]
        norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1)
        if not torch.isfinite(norm) or float(norm) == 0:
            raise ValueError("No finite nonzero gradient")
        optimizer.step()
        step_losses.append({"step": step + 1, "weighted_loss": total, "gradient_norm": float(norm)})
        print(json.dumps(step_losses[-1]), flush=True)
    after = adapter_digest(model)
    if before == after:
        raise ValueError("Adapter parameters did not change")
    checkpoint = destination / "checkpoint"
    model.save_pretrained(checkpoint)
    tokenizer.save_pretrained(checkpoint)
    model.eval()
    with torch.no_grad():
        after_loss = float(model(**batch(rows[0])).loss)
    train_seconds = time.monotonic() - started
    peak_memory = torch.cuda.max_memory_allocated()
    del optimizer, model, network
    gc.collect()
    torch.cuda.empty_cache()
    base = AutoModelForCausalLM.from_pretrained(
        args.model, local_files_only=True, torch_dtype=torch.bfloat16, attn_implementation="sdpa"
    ).to("cuda")
    reloaded = PeftModel.from_pretrained(base, checkpoint, is_trainable=False)
    reloaded.eval()
    restored = adapter_digest(reloaded)
    with torch.no_grad():
        restored_loss = float(reloaded(**batch(rows[0])).loss)
    if restored != after or not math.isclose(after_loss, restored_loss, rel_tol=1e-5, abs_tol=1e-5):
        raise ValueError("Checkpoint reload verification failed")
    world_path = compile_world(design(702, "short"), destination / "post_reload_world")
    backend = LocalModelBackend(reloaded, tokenizer, "Qwen2.5-7B-Instruct+LoRA", after)
    result = run_model(
        World(world_path),
        backend,
        args.max_turns,
        progress=lambda row: print(json.dumps(row), flush=True),
    )
    evaluations = evaluate(world_path)
    state = Store(world_path).load()
    report = {
        **code_identity(),
        "experiment": "training_pipeline_smoke",
        "learning_gain_measured": False,
        "data_origin": "DeepSeek teacher trajectories revalidated by finance-v0.1.2",
        "base_model": str(Path(args.model).resolve()),
        "adapter": "LoRA rank=8 q_proj/v_proj alpha=16 dropout=0",
        "torch": torch.__version__,
        "device": torch.cuda.get_device_name(),
        "weighting": "equal episode; equal call within episode; mean supervised-token CE per call",
        "records": len(rows),
        "episodes": len({r["episode_id"] for r in rows}),
        "supervised_tokens_per_step": sum(r["target_tokens"] for r in rows),
        "excluded": excluded,
        "optimizer_steps": args.steps,
        "losses": step_losses,
        "before_adapter_sha256": before,
        "after_adapter_sha256": after,
        "reloaded_adapter_sha256": restored,
        "first_record_loss_after_training": after_loss,
        "first_record_loss_after_reload": restored_loss,
        "train_and_save_seconds": train_seconds,
        "peak_gpu_bytes": peak_memory,
        "post_reload_run": result,
        "post_reload_evaluations": evaluations,
        "post_reload_tool_actions": sum(r["actor_id"] == "analyst" for r in state["interactions"]),
        "reasoning_transfer": "provider reasoning_content omitted; not mapped to target hidden thinking",
        "strict_on_policy_ready": False,
    }
    atomic_write(destination / "summary.json", json_bytes(report))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
