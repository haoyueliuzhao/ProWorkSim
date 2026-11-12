"""The pinned REF qwen3 parser reused by MATCH through a CPU-only sidecar."""
from __future__ import annotations

import hashlib
from importlib.metadata import version
import inspect
import json
from pathlib import Path
import socket

VERSION = "software-benchmark-v054-official-qwen-codec-v1"
MAX_WIRE_BYTES = 4 * 1024 * 1024


class OfficialQwenCodec:
    """Runs in the separate REF service environment, never in the model owner."""

    def __init__(self, tokenizer):
        if version("vllm") != "0.32.0":
            raise ValueError("Use the exact REF vLLM parser package")
        from vllm.tool_parsers.qwen3_engine_tool_parser import Qwen3EngineToolParser
        from vllm.reasoning.qwen3_engine_reasoning_parser import Qwen3ParserReasoningAdapter
        self.tokenizer = tokenizer
        self.tool_parser = Qwen3EngineToolParser
        self.reasoning_parser = Qwen3ParserReasoningAdapter
        manifest_path = Path(tokenizer.name_or_path) / "proworksim-manifest.json"
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if (manifest.get("repo_id") != "Qwen/Qwen3.5-9B"
                or manifest.get("declared_hf_revision")
                != "c202236235762e1c871ad0ccb60c8ee5ba337b9a"):
            raise ValueError("Codec tokenizer differs from the frozen raw model")
        source = {}
        for cls in (Qwen3EngineToolParser, Qwen3ParserReasoningAdapter):
            path = Path(inspect.getfile(cls))
            source[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.identity = {
            "version": VERSION, "vllm_version": "0.32.0",
            "tool_call_parser": "qwen3_coder", "reasoning_parser": "qwen3",
            "enable_thinking": False, "parser_source_files": source,
            "tokenizer_source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "tokenizer_chat_template_sha256": hashlib.sha256(
                tokenizer.chat_template.encode()).hexdigest(),
            "terminal_eos_presentation": "exclude_last_stop_token_from_text_keep_all_usage_ids",
        }

    def decode(self, *, request, result):
        from vllm.entrypoints.openai.chat_completion.protocol import ChatCompletionRequest
        ids = result["output_ids"]
        if not isinstance(ids, list) or not ids:
            raise ValueError("Official decoding requires complete generated token IDs")
        stop = result["finish_reason"] == "stop"
        if stop and ids[-1] not in (248044, 248046):
            raise ValueError("The native stop boundary has no expected terminal EOS")
        # vLLM's IncrementalDetokenizer excludes the last stop token from text
        # when include_stop_str_in_output=False, but retains it in token usage.
        visible_ids = ids[:-1] if stop else ids
        text = self.tokenizer.decode(
            visible_ids, skip_special_tokens=False, clean_up_tokenization_spaces=False)
        protocol_request = ChatCompletionRequest(
            model=request["model"], messages=request["messages"],
            tools=request.get("tools") or None,
            tool_choice="auto" if request.get("tools") else "none",
            chat_template_kwargs={"enable_thinking": False},
        )
        reasoning = self.reasoning_parser(
            self.tokenizer, chat_template_kwargs={"enable_thinking": False})
        reasoning_text, content = reasoning.extract_reasoning(text, protocol_request)
        message = {"role": "assistant", "content": content}
        if reasoning_text:
            message["reasoning_content"] = reasoning_text
        if protocol_request.tools and content:
            parser = self.tool_parser(
                self.tokenizer, tools=protocol_request.tools,
                chat_template_kwargs={"enable_thinking": False})
            parsed = parser.extract_tool_calls(content, protocol_request)
            message["content"] = parsed.content
            if parsed.tools_called:
                message["tool_calls"] = [
                    call.model_dump(mode="json") for call in parsed.tool_calls]
        return {
            "message": message, "codec_identity": self.identity,
            "generated_token_count": len(ids),
            "presentation_token_count": len(visible_ids),
            "all_generated_ids_retained_by_caller": True,
        }


class UnixSocketCodec:
    """One local request, no reconnect/retry or fallback parser."""

    def __init__(self, socket_path, expected_identity, *, timeout_seconds=60):
        self.socket_path = str(socket_path)
        self.expected_identity = expected_identity
        self.timeout_seconds = timeout_seconds

    def decode(self, *, request, result):
        payload = (json.dumps({"request": request, "result": result},
                              ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        if len(payload) > MAX_WIRE_BYTES:
            raise ValueError("Codec request exceeds its declared IPC byte bound")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(self.timeout_seconds)
            stream.connect(self.socket_path)
            stream.sendall(payload)
            with stream.makefile("rb") as response:
                line = response.readline(MAX_WIRE_BYTES + 1)
        if len(line) > MAX_WIRE_BYTES or not line.endswith(b"\n"):
            raise ValueError("Codec response is missing or incomplete")
        value = json.loads(line)
        if value.get("error") or value.get("codec_identity") != self.expected_identity:
            raise ValueError("Pinned official codec failed or changed identity")
        return value
