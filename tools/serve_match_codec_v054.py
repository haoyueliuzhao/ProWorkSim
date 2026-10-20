"""Serve only the official parser on a private Unix socket; no model loading."""
from __future__ import annotations

import argparse
import faulthandler
import importlib.util
import json
import os
from pathlib import Path
import socket
import socketserver
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-local", type=Path, required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--identity-output", type=Path, required=True)
    parser.add_argument("--diagnostic-traceback-seconds", type=int, default=0)
    args = parser.parse_args()
    if args.socket.exists() or args.identity_output.exists():
        raise ValueError("Codec requires a new private socket and identity receipt")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "" or os.environ.get("NVIDIA_VISIBLE_DEVICES") != "void":
        raise ValueError("The parser sidecar must use the explicit CPU runtime")
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        raise ValueError("The parser may only read existing local tokenizer files")
    def audit(event, values):
        if event == "socket.getaddrinfo" or (
                event in {"socket.connect", "socket.sendto"}
                and values[0].family != socket.AF_UNIX):
            raise RuntimeError("Only private Unix IPC is permitted in the parser")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                raise RuntimeError("Parser may not read model weights")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                raise RuntimeError("Parser may not access GPU devices")
    sys.addaudithook(audit)
    from transformers import AutoTokenizer
    # The REF parser environment deliberately does not install project business
    # adapters. Load this standalone module without proworksim.__init__ imports.
    module_path = Path(__file__).resolve().parents[1] / "src/proworksim/software_benchmark_codec_v054.py"
    spec = importlib.util.spec_from_file_location("v054_standalone_codec", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    OfficialQwenCodec, MAX_WIRE_BYTES = module.OfficialQwenCodec, module.MAX_WIRE_BYTES
    tokenizer = AutoTokenizer.from_pretrained(
        str(args.model_local), local_files_only=True, trust_remote_code=False)
    codec = OfficialQwenCodec(tokenizer)
    args.identity_output.parent.mkdir(parents=True, exist_ok=True)
    args.identity_output.write_text(json.dumps(
        codec.identity, ensure_ascii=False, sort_keys=True, indent=2) + "\n")

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            line = self.rfile.readline(MAX_WIRE_BYTES + 1)
            try:
                if args.diagnostic_traceback_seconds:
                    faulthandler.dump_traceback_later(args.diagnostic_traceback_seconds)
                if len(line) > MAX_WIRE_BYTES or not line.endswith(b"\n"):
                    raise ValueError("Incomplete or oversized parser request")
                incoming = json.loads(line)
                result = codec.decode(**incoming)
            except Exception as error:
                result = {"error": {"type": type(error).__name__, "message": str(error)}}
            finally:
                if args.diagnostic_traceback_seconds:
                    faulthandler.cancel_dump_traceback_later()
            encoded = (json.dumps(result, ensure_ascii=False) + "\n").encode()
            if len(encoded) > MAX_WIRE_BYTES:
                encoded = b'{"error":{"type":"OversizedResponse"}}\n'
            self.wfile.write(encoded)

    args.socket.parent.mkdir(parents=True, exist_ok=True)
    try:
        with socketserver.UnixStreamServer(str(args.socket), Handler) as server:
            os.chmod(args.socket, 0o600)
            server.serve_forever(poll_interval=0.5)
    finally:
        args.socket.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
