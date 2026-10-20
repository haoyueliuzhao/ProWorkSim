"""Four CPU controls for common exact counters and synthetic local HTTP REF."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
import traceback
from types import SimpleNamespace


class FixtureHTTP:
    def __init__(self):
        self.mode, self.calls, self.generations = "normal", [], 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.calls.append({"path": self.path, "payload": payload})
                mode = owner.mode
                template = {key: payload[key] for key in (
                    "model", "messages", "tools", "chat_template_kwargs",
                    "add_generation_prompt", "continue_final_message", "add_special_tokens")}
                # These are explicit synthetic backend IDs, not Qwen token counts.
                ids = list(json.dumps(template, sort_keys=True).encode())
                if mode == "redirect":
                    self.send_response(302)
                    self.send_header("Location", "http://example.invalid/unapproved")
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(b"{}")
                    return
                if self.path == "/tokenize":
                    body = {"tokens": ids, "count": len(ids) + (mode == "bad_count"),
                            "max_model_len": 131072}
                elif self.path == "/v1/chat/completions":
                    owner.generations += 1
                    if mode == "timeout":
                        time.sleep(0.25)
                    prompt = len(ids) + (mode == "bad_usage")
                    body = {
                        "id": f"synthetic-http-{owner.generations}",
                        "model": payload["model"], "object": "chat.completion",
                        "choices": [{"index": 0, "message": {
                            "role": "assistant", "content": "synthetic HTTP response"},
                            "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": prompt, "completion_tokens": 3,
                                  "total_tokens": prompt + 3,
                                  "completion_tokens_details": {"reasoning_tokens": 1}},
                    }
                else:
                    raise AssertionError("Unexpected fixture endpoint")
                encoded = json.dumps(body).encode()
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.05), daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-local", type=Path, required=True)
    parser.add_argument("--interface-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = {
        "version": "software-benchmark-v054-exact-transport-control-v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "passed": False,
        "real_model_calls": 0, "gpu_device_opens": 0, "weight_file_opens": 0,
        "external_network_attempts": 0, "formal_execution_authorized": False,
        "controls": {},
    }
    servers = []

    def audit(event, values):
        remote = False
        if event == "socket.getaddrinfo":
            remote = values[0] != "127.0.0.1"
        elif event in {"socket.connect", "socket.sendto"}:
            remote = values[0].family != socket.AF_UNIX and values[1][0] != "127.0.0.1"
        if remote:
            receipt["external_network_attempts"] += 1
            raise RuntimeError("Only the owned loopback HTTP fixture may be contacted")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                receipt["weight_file_opens"] += 1
                raise RuntimeError("Weights are forbidden in this CPU control")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                receipt["gpu_device_opens"] += 1
                raise RuntimeError("GPU devices are forbidden in this CPU control")

    sys.addaudithook(audit)
    try:
        assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
        assert os.environ.get("NVIDIA_VISIBLE_DEVICES") == "void"
        from openhands.sdk import Message, TextContent
        from openhands.sdk.event import MessageEvent
        from transformers import AutoTokenizer
        from proworksim import software_benchmark_exact_transport_v054 as exact
        from proworksim.software_benchmark_match_v054 import CONTRACT, MatchBridge
        from proworksim.software_benchmark_native_v054 import build_agent

        interface = json.loads(args.interface_manifest.read_bytes())

        class ToolView:
            def __init__(self, schema):
                self.schema = schema

            def to_openai_tool(self, **kwargs):
                return copy.deepcopy(self.schema)

        tools = [ToolView(value) for value in interface["tool_schemas"].values()]
        messages = [
            Message(role="system", content=[TextContent(text=interface["static_system_prompt"])]),
            Message(role="user", content=[TextContent(text="Synthetic exact-counter control.")]),
        ]

        def create_ref(name, *, timeout=2):
            server = FixtureHTTP()
            servers.append(server)
            adapter = exact.RefExactAdapter(
                transport=exact.LoopbackHTTP(server.url, timeout_seconds=timeout),
                folder=args.output / name, slot_id="synthetic-" + name, seed=42,
                service_identity={"programmed_fixture": True},
                programmed_http_fixture=True)
            return server, adapter, exact.build_llm(adapter)

        server, adapter, llm = create_ref("shared-budget")
        agent = build_agent(llm)
        assert agent.condenser.llm._adapter is adapter
        count = llm.get_token_count(messages, tools, add_security_risk_prediction=True)
        assert count > 0 and len(server.calls) == 1 and server.generations == 0
        agent.llm.generate(messages=messages, tools=tools, add_security_risk_prediction=True)
        assert len(server.calls) == 2  # The same exact count proof is reused.
        event = MessageEvent(source="user", llm_message=Message(
            role="user", content=[TextContent(text="Earlier synthetic observation.")]))
        summary = agent.condenser._generate_condensation(
            forgotten_events=[event], summary_offset=0)
        assert summary.summary == "synthetic HTTP response"
        snapshot = adapter.ledger.snapshot()
        assert (snapshot["attempts"], snapshot["decisions"], server.generations) == (2, 1, 2)
        assert set(snapshot["per_usage_id"]) == {"agent", "condenser"}
        assert all(call["reservation"] == call["prompt_tokens"] + 32768
                   for call in snapshot["calls"])
        assert all(call["payload"]["chat_template_kwargs"] == {"enable_thinking": True}
                   for call in server.calls)
        tokenization = [call["payload"] for call in server.calls if call["path"] == "/tokenize"]
        for call in server.calls:
            if call["path"] == "/v1/chat/completions":
                assert {key: call["payload"][key] for key in exact.TEMPLATE_KEYS} in tokenization
        adapter.ledger.attempt_limit = 2
        try:
            llm.generate(messages=messages, tools=tools, add_security_risk_prediction=True)
            raise AssertionError("Shared attempt cap was bypassed")
        except exact.DispatchStopped:
            pass
        assert server.generations == 2
        receipt["controls"]["shared_sdk_condenser_and_exact_wire"] = {
            "passed": True, "synthetic_input_count": count, "ledger": snapshot,
            "tokenize_requests": len(tokenization), "chat_requests": server.generations,
        }

        bad_server, bad_adapter, bad_llm = create_ref("usage-mismatch")
        bad_server.mode = "bad_usage"
        try:
            bad_llm.generate(messages=messages, tools=tools, add_security_risk_prediction=True)
            raise AssertionError("Wrong prompt usage was accepted")
        except exact.AccountingFault:
            pass
        bad_state = bad_adapter.ledger.snapshot()
        assert bad_state["complete_actual_tokens"] is None
        assert bad_state["uncertain_reserved_tokens"] > 32768
        try:
            bad_llm.generate(messages=messages, tools=tools, add_security_risk_prediction=True)
            raise AssertionError("Failed completion was sampled again")
        except exact.DispatchStopped:
            pass
        assert bad_server.generations == 1
        count_server, count_adapter, count_llm = create_ref("bad-counter")
        count_server.mode = "bad_count"
        try:
            count_llm.get_token_count(messages, tools, add_security_risk_prediction=True)
            raise AssertionError("Invalid exact-count reply was accepted")
        except exact.AccountingFault:
            pass
        assert count_server.generations == count_adapter.ledger.attempts == 0
        receipt["controls"]["usage_mismatch_and_invalid_count"] = {
            "passed": True, "incomplete_usage_ledger": bad_state,
            "invalid_count_generation_requests": count_server.generations,
        }

        timeout_server, timeout_adapter, timeout_llm = create_ref("timeout", timeout=0.05)
        timeout_server.mode = "timeout"
        try:
            timeout_llm.generate(messages=messages, tools=tools, add_security_risk_prediction=True)
            raise AssertionError("Fixture generation did not time out")
        except exact.AccountingFault:
            pass
        assert timeout_adapter.ledger.inflight is not None
        assert timeout_server.generations == 1
        for forbidden in ("https://127.0.0.1:18054", "http://example.invalid:18054",
                          "http://localhost:18054"):
            try:
                exact.LoopbackHTTP(forbidden)
                raise AssertionError("A non-fixed endpoint was accepted")
            except ValueError:
                pass
        redirect = FixtureHTTP()
        servers.append(redirect)
        redirect.mode = "redirect"
        try:
            exact.LoopbackHTTP(redirect.url).post("/tokenize", tokenization[0])
            raise AssertionError("Redirect was followed")
        except exact.HTTPFailure:
            pass
        assert len(redirect.calls) == 1
        receipt["controls"]["timeout_unknown_and_no_remote_redirect"] = {
            "passed": True, "ledger": timeout_adapter.ledger.snapshot(),
            "synthetic_chat_requests": timeout_server.generations,
            "redirect_requests": len(redirect.calls),
        }

        tokenizer = AutoTokenizer.from_pretrained(
            str(args.model_local), local_files_only=True, trust_remote_code=False)
        output_ids = tokenizer.encode("synthetic MATCH response", add_special_tokens=False) + [248044]

        class Owner:
            programmed_fixture, path, contract = True, "project", CONTRACT

            def __init__(self):
                self.tokenizer = tokenizer

            def freeze_identity(self):
                return {"raw_release": True, "checkpoint": None, "adapter_sha256": None}

            def generate_native(self, native):
                return {
                    "attempt_id": "synthetic-match", "actor_identity": self.freeze_identity(),
                    "input": native, "output_ids": output_ids,
                    "raw_generated_text": tokenizer.decode(output_ids, skip_special_tokens=False),
                    "finish_reason": "stop", "usage": {
                        "prompt_tokens": native["prompt_tokens"], "completion_tokens": len(output_ids),
                        "total_tokens": native["prompt_tokens"] + len(output_ids)},
                }

        bridge = MatchBridge(
            Owner(), codec=SimpleNamespace(decode=lambda **kw: {
                "message": {"role": "assistant", "content": "synthetic MATCH response"},
                "codec_identity": {"programmed_fixture": True}}),
            folder=args.output / "match", slot_id="synthetic-match", allow_programmed_fixture=True)
        match_adapter = exact.MatchExactAdapter(bridge)
        match_llm = exact.build_llm(match_adapter)
        assert type(match_llm) is type(llm)
        match_count = match_llm.get_token_count(messages, tools, add_security_risk_prediction=True)
        match_request = exact.export_request(
            match_llm, match_adapter, messages, tools, add_security_risk_prediction=True)
        measure = match_adapter.count(match_request)
        assert measure["prompt_tokens"] == match_count == len(measure["input_ids"])
        assert match_request["messages"] == server.calls[0]["payload"]["messages"]
        assert match_request["tools"] == server.calls[0]["payload"]["tools"]
        match_llm.generate(messages=messages, tools=tools, add_security_risk_prediction=True)
        assert bridge.ledger.calls[0]["usage"]["prompt_tokens"] == match_count
        receipt["controls"]["same_counter_class_real_match_tokenizer"] = {
            "passed": True, "actual_match_prompt_tokens": match_count,
            "same_sdk_llm_class": True, "same_messages_and_tools": True,
            "count_matches_native_generated_input_ids": True,
            "model_generation_is_programmed_fixture": True,
        }
        receipt["passed"] = all(item["passed"] for item in receipt["controls"].values())
        receipt["control_count"] = len(receipt["controls"])
    except BaseException as error:
        receipt["error"] = {"type": type(error).__name__, "message": str(error)}
        receipt["traceback"] = traceback.format_exc()
    finally:
        for server in servers:
            server.close()
    receipt["ended_at_utc"] = datetime.now(timezone.utc).isoformat()
    receipt["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (args.output / "receipt.json").write_text(json.dumps(
        receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps({key: value for key, value in receipt.items() if key != "controls"},
                     ensure_ascii=False, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
