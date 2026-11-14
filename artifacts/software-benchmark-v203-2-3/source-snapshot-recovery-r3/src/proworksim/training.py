"""Explicit local SFT adapter. Teacher data is not relabeled as self-generated experience."""

import copy
import hashlib
import json
import re
import uuid
from collections import Counter
from pathlib import Path


def normalize_messages(messages):
    converted = []
    for message in messages:
        row = {"role": message["role"], "content": message.get("content") or ""}
        if message.get("tool_calls"):
            row["tool_calls"] = copy.deepcopy(message["tool_calls"])
            for call in row["tool_calls"]:
                arguments = call["function"]["arguments"]
                if isinstance(arguments, str):
                    call["function"]["arguments"] = json.loads(arguments)
        if "tool_call_id" in message:
            row["tool_call_id"] = message["tool_call_id"]
        # Provider reasoning_content is intentionally NOT mapped to another model's think format.
        converted.append(row)
    return converted


def tokenize_record(tokenizer, record, max_length=8192):
    if not record["eligible"] or record["message_loss_mask"] != [0] * (
        len(record["messages"]) - 1
    ) + [1]:
        raise ValueError("Only an eligible final-assistant target is supported")
    messages = normalize_messages(record["messages"])
    kwargs = {"tools": record["tools"], "tokenize": False}
    prefix = tokenizer.apply_chat_template(messages[:-1], add_generation_prompt=True, **kwargs)
    rendered = tokenizer.apply_chat_template(messages, add_generation_prompt=False, **kwargs)
    if not rendered.startswith(prefix):
        raise ValueError("Target tokenizer template does not preserve the generation prefix")
    encoded = tokenizer(rendered, add_special_tokens=False, return_offsets_mapping=True)
    if len(encoded["input_ids"]) > max_length:
        raise ValueError("length_limit: record is excluded, never silently truncated")
    labels = [
        token if start >= len(prefix) and end > start else -100
        for token, (start, end) in zip(encoded["input_ids"], encoded["offset_mapping"])
    ]
    if not any(label != -100 for label in labels):
        raise ValueError("No supervised tokens after rendering")
    return {
        "input_ids": encoded["input_ids"],
        "labels": labels,
        "target_tokens": sum(label != -100 for label in labels),
        "prompt_tokens": sum(label == -100 for label in labels),
        "call_id": record["call_id"],
        "episode_id": record["branch_id"],
        "teacher_provider": record["provider"],
        "teacher_model": record["model"],
        "source_record_sha256": hashlib.sha256(
            json.dumps(record, sort_keys=True).encode()
        ).hexdigest(),
    }


def load_training_records(tokenizer, exports, max_length=8192, per_episode=2):
    selected, excluded, counts = [], [], Counter()
    for directory in exports:
        for line in (Path(directory) / "sft.jsonl").read_text().splitlines():
            record = json.loads(line)
            if record["split"] != "train":
                raise ValueError("Training input contains a non-training lineage")
            if counts[record["branch_id"]] >= per_episode:
                excluded.append({"call_id": record["call_id"], "reason": "per_episode_smoke_cap"})
                continue
            try:
                sample = tokenize_record(tokenizer, record, max_length)
            except ValueError as exc:
                excluded.append({"call_id": record["call_id"], "reason": str(exc)})
                continue
            selected.append(sample)
            counts[sample["episode_id"]] += 1
    if not selected:
        raise ValueError("No usable supervised examples")
    for row in selected:
        row["weight"] = 1 / len(counts) / counts[row["episode_id"]]
    return selected, excluded


def adapter_digest(model):
    from peft import get_peft_model_state_dict

    value = hashlib.sha256()
    for name, tensor in sorted(get_peft_model_state_dict(model).items()):
        value.update(name.encode())
        value.update(tensor.detach().float().cpu().contiguous().numpy().tobytes())
    return value.hexdigest()


class LocalModelBackend:
    provider = "local_transformers"

    def __init__(self, model, tokenizer, model_name, policy_version, max_new_tokens=384):
        self.network, self.tokenizer = model, tokenizer
        self.model, self.policy_version = model_name, policy_version
        self.max_new_tokens = max_new_tokens

    def payload(self, messages):
        from .tools import TOOLS

        return {
            "model": self.model,
            "messages": messages,
            "tools": TOOLS,
            "policy_version": self.policy_version,
            "do_sample": False,
            "max_new_tokens": self.max_new_tokens,
        }

    def complete(self, request):
        import torch

        rendered = self.tokenizer.apply_chat_template(
            normalize_messages(request["messages"]),
            tools=request["tools"],
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(rendered, add_special_tokens=False, return_tensors="pt").to(
            self.network.device
        )
        if (
            inputs.input_ids.shape[1] + self.max_new_tokens
            > self.network.config.max_position_embeddings
        ):
            raise ValueError("Local model context budget exceeded")
        self.network.eval()
        with torch.no_grad():
            output = self.network.generate(
                **inputs,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        tokens = output[0, inputs.input_ids.shape[1] :].tolist()
        text = self.tokenizer.decode(tokens, skip_special_tokens=False)
        calls = []
        for match in re.finditer(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL):
            try:
                candidate = json.loads(match.group(1))
                if not isinstance(candidate.get("name"), str) or not isinstance(
                    candidate.get("arguments"), dict
                ):
                    continue
                calls.append(
                    {
                        "id": uuid.uuid4().hex,
                        "type": "function",
                        "function": {
                            "name": candidate["name"],
                            "arguments": json.dumps(candidate["arguments"], ensure_ascii=False),
                        },
                    }
                )
            except (ValueError, TypeError):
                continue
        assistant = {
            "role": "assistant",
            "content": text
            if not calls
            else re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.DOTALL)
            .replace("<|im_end|>", "")
            .strip(),
        }
        if calls:
            assistant["tool_calls"] = calls
        return {
            "model": self.model,
            "policy_version": self.policy_version,
            "raw_generated_text": text,
            "output_token_ids": tokens,
            "choices": [{"message": assistant, "logprobs": None}],
            "usage": {
                "prompt_tokens": inputs.input_ids.shape[1],
                "completion_tokens": len(tokens),
                "total_tokens": inputs.input_ids.shape[1] + len(tokens),
            },
        }
