"""CPU-only real-SDK controls for opt-in PROJECT cursor restoration."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]


def control(output):
    if os.getuid() == 0 or os.geteuid() == 0:
        raise PermissionError("Use an ordinary user for scripted CPU controls")
    output = Path(output).resolve()
    if not (output.is_relative_to(Path("/tmp"))
            or output.is_relative_to(ROOT / "runs/software-benchmark-v090")):
        raise ValueError("Use a fresh task-local control directory")
    output.mkdir(parents=True, exist_ok=False)
    forbidden = {"network": 0, "weights": 0, "gpu": 0}

    def audit(event, values):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto", "socket.bind"}:
            forbidden["network"] += 1
            raise AssertionError("No network allowed")
        if event == "open" and values and isinstance(values[0], (str, bytes)):
            path = os.fsdecode(values[0])
            if path.endswith((".safetensors", ".gguf")) or "pytorch_model" in path:
                forbidden["weights"] += 1
                raise AssertionError("No weight loading allowed")
            if path.startswith(("/dev/nvidia", "/dev/dri/")):
                forbidden["gpu"] += 1
                raise AssertionError("No GPU allowed")

    sys.addaudithook(audit)
    from proworksim.harness_sdk import HarnessWorker
    from proworksim.software_benchmark_nullable_cursor_v090 import (
        CURSOR_TOOLS, create_project_worker, install_project_nullable_cursors,
        needs_null_cursor_restoration,
    )
    from proworksim.software_benchmark_world_v054 import TOOLS

    definitions = [copy.deepcopy(row) for row in TOOLS if row["name"] in CURSOR_TOOLS]
    config = {"model": "cpu-fixture-not-a-model", "api_key_env": None,
              "base_url": "http://127.0.0.1", "backend_id": "explicit_test_fixture",
              "retry": {"max_attempts": 1, "backoff_seconds": []},
              "budget": {"max_cost_usd": 50},
              "weight_identity": {"step": 0, "policy_version": "fixture-policy-0"},
              "model_revision": "fixture-policy-0"}
    result = {"passed": False, "model_calls": 0, "remote_tool_calls": 0,
              "scripted_responses": 0, "positive_cases": [], "negative_cases": [],
              "baseline_null_rejected": False, "strict_boundary_controls": 0,
              "forbidden_operations": forbidden}

    class FixtureTransport:
        def __init__(self, calls):
            self.calls, self.requests = list(calls), []

        def complete(self, request, **kwargs):
            self.requests.append(copy.deepcopy(request))
            name, args = self.calls.pop(0)
            result["scripted_responses"] += 1
            body = {"id": f"fixture-{result['scripted_responses']}", "model": config["model"],
                    "object": "chat.completion", "created": 0,
                    "choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
                        "role": "assistant", "content": None, "tool_calls": [{
                            "id": f"fixture-call-{result['scripted_responses']}", "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args)}}]}}],
                    "usage": {"prompt_tokens": 17, "completion_tokens": 3, "total_tokens": 20}}
            return {"http_status": 200, "body": body, "raw_body": json.dumps(body)}

    def run_case(name, arguments, *, repaired, label):
        actual, events = [], []
        transport = FixtureTransport([(name, arguments)])

        def execute(tool, args, association):
            actual.append((tool, copy.deepcopy(args)))
            return {"ok": True, "fixture_only": True}

        factory = create_project_worker if repaired else HarnessWorker
        worker = factory("member_001", definitions, config, transport, execute,
                         event_sink=lambda k, p: events.append((k, p)), directory=output / label)
        caught, outcome = None, None
        try:
            outcome = worker.step({"fixture": label}, {"run_id": "cpu", "opportunity_id": label})
        except Exception as error:
            caught = str(error)
        finally:
            worker.close()
        return {"actual": actual, "error": caught,
                "executed": bool(outcome and outcome.get("executed")),
                "restorations": sum(k == "sdk_explicit_null_cursor_restored" for k, _ in events),
                "original_gateway_rejection_observed": "SDK transformed arguments" in json.dumps(events),
                "requests": len(transport.requests), "worker": worker}

    try:
        schema = {"type": "object", "properties": {
            "cursor": {"type": ["string", "null"]}, "path": {"type": "string", "minLength": 1}},
            "required": ["path"], "additionalProperties": False}
        good = [({"path": "a", "cursor": None}, {"path": "a"}, True),
                ({"path": "a", "cursor": None}, {"path": "a", "cursor": None}, False),
                ({"path": "a"}, {"path": "a"}, False),
                ({"path": "a", "cursor": ""}, {"path": "a", "cursor": ""}, False),
                ({"path": "a", "cursor": "next"}, {"path": "a", "cursor": "next"}, False)]
        for original, projected, expected in good:
            assert needs_null_cursor_restoration("read_file", schema, original, projected) is expected
            result["strict_boundary_controls"] += 1
        bad = [({"path": "a", "cursor": ""}, {"path": "a"}),
               ({"path": "a", "cursor": "next"}, {"path": "a"}),
               ({"path": "a", "cursor": None}, {"path": "b"}),
               ({"path": "a", "cursor": None}, {"path": "a", "unknown": 1}),
               ({"path": "a", "cursor": None}, {}),
               ({"path": "a", "cursor": None, "unknown": None}, {"path": "a"}),
               ({"path": None, "cursor": None}, {}), ({"cursor": None}, {}),
               ({"path": "a", "cursor": 1}, {"path": "a"})]
        from jsonschema.exceptions import ValidationError
        for original, projected in bad:
            try:
                needs_null_cursor_restoration("read_file", schema, original, projected)
            except (ValueError, ValidationError):
                result["strict_boundary_controls"] += 1
            else:
                raise AssertionError("Unexpected widened argument equivalence")
        for variant in ["required", "nonnullable", "extra", "other-tool", "default"]:
            altered, name = copy.deepcopy(schema), "read_file"
            if variant == "required":
                altered["required"].append("cursor")
            elif variant == "nonnullable":
                altered["properties"]["cursor"]["type"] = "string"
            elif variant == "extra":
                altered["additionalProperties"] = True
            elif variant == "default":
                altered["properties"]["cursor"]["default"] = "different"
            else:
                name = "write_file"
            try:
                needs_null_cursor_restoration(name, altered, {"path": "a", "cursor": None}, {"path": "a"})
            except ValueError:
                result["strict_boundary_controls"] += 1
            else:
                raise AssertionError("Unsupported nullable schema must remain rejected")
        old = run_case("list_files", {"cursor": None}, repaired=False, label="baseline")
        assert not old["actual"] and old["original_gateway_rejection_observed"]
        result["baseline_null_rejected"] = True
        for name in sorted(CURSOR_TOOLS):
            base = {"path": "fixture.py"} if name in {"read_file", "search_file"} else {}
            if name == "search_file":
                base["text"] = "needle"
            for label, value in [("null", None), ("empty", ""), ("next", "exact-cursor"), ("omitted", None)]:
                args = {**base, **({} if label == "omitted" else {"cursor": value})}
                observed = run_case(name, args, repaired=True, label=name + "-" + label)
                assert observed["executed"] and observed["actual"] == [(name, args)], observed
                assert observed["requests"] == 1
                assert observed["restorations"] == (1 if label == "null" else 0)
                try:
                    install_project_nullable_cursors(observed["worker"])
                except ValueError:
                    pass
                else:
                    raise AssertionError("Installing after decisions must fail")
                result["positive_cases"].append({"tool": name, "cursor_case": label,
                                                  "original_arguments_executed_once": True})
        negatives = [("list_files", {"cursor": None, "unknown": 1}),
                     ("read_file", {"cursor": None}),
                     ("read_file", {"path": None, "cursor": None}),
                     ("list_files", {"cursor": 1})]
        for index, (name, args) in enumerate(negatives):
            observed = run_case(name, args, repaired=True, label=f"negative-{index}")
            assert not observed["actual"] and not observed["executed"]
            assert observed["requests"] == 1 and observed["restorations"] == 0
            result["negative_cases"].append({"tool": name, "arguments": args, "gateway_calls": 0})
        result["passed"] = not any(forbidden.values())
    except BaseException as error:
        result.update(error={"type": type(error).__name__, "message": str(error)},
                      traceback=traceback.format_exc())
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "error": result.get("error"),
                      "positive_cases": len(result["positive_cases"]),
                      "negative_cases": len(result["negative_cases"])}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(control(parser.parse_args().output))
