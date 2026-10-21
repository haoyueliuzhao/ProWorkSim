"""CPU-only synthetic REF endpoint; explicit fixture, never the formal vLLM port."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--model-local", required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    args = parser.parse_args()
    if args.port == 18054:
        raise ValueError("Synthetic service cannot impersonate formal REF")
    from transformers import AutoTokenizer
    from proworksim.software_benchmark_match_v054 import normalize_native_messages
    tokenizer = AutoTokenizer.from_pretrained(args.model_local, local_files_only=True)
    responses = json.loads(args.responses.read_text())
    state = {"calls": 0}

    def tokens(request):
        text = tokenizer.apply_chat_template(
            normalize_native_messages(request["messages"]), tools=request.get("tools") or None,
            tokenize=False, add_generation_prompt=True,
            **request.get("chat_template_kwargs", {}))
        return tokenizer(text, add_special_tokens=False)["input_ids"]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            ids = tokens(request)
            if self.path == "/tokenize":
                result = {"count": len(ids), "tokens": ids, "max_model_len": 131072}
            elif self.path == "/v1/chat/completions" and state["calls"] < len(responses):
                message = responses[state["calls"]]
                state["calls"] += 1
                output_ids = tokenizer.encode(json.dumps(message), add_special_tokens=False) + [248044]
                result = {"id": "synthetic-ref-" + str(state["calls"]),
                          "object": "chat.completion", "model": request["model"],
                          "choices": [{"index": 0, "message": message,
                                       "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
                          "usage": {"prompt_tokens": len(ids), "completion_tokens": len(output_ids),
                                    "total_tokens": len(ids) + len(output_ids)},
                          "programmed_fixture_only": True}
            else:
                self.send_error(400, "Unscheduled synthetic request")
                return
            encoded = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    with HTTPServer(("127.0.0.1", args.port), Handler) as server:
        args.ready.write_text(json.dumps({"ready": True, "programmed_fixture_only": True,
                                        "port": args.port, "model_calls": 0}))
        server.serve_forever(poll_interval=0.1)


if __name__ == "__main__":
    main()
