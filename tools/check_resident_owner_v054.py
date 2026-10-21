"""Small CPU fixture for resident session isolation; no real model or tokenizer."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import time
import uuid

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from proworksim.software_benchmark_owner_ipc_v054 import OwnerClient, ScriptedOwner, ScriptedCodec  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import write_new, reference  # noqa: E402
from proworksim.software_benchmark_supervision_v054 import process_identity  # noqa: E402
from proworksim.software_benchmark_match_v054 import TOOL_NAMES  # noqa: E402


class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return json.dumps({"messages": messages, "tools": kwargs.get("tools")})
    def __call__(self, text, **_):
        return {"input_ids": self.encode(text)}
    def encode(self, text, **_):
        return [ord(value) for value in text]


class Owner(ScriptedOwner):
    def __init__(self, *args):
        super().__init__(*args)
        self.rng, self.seeds, self.guards = random.Random(99), [], []
    def capture_evaluation_state(self):
        if self.phase != "idle" or self.busy:
            raise ValueError("Fixture window is not idle")
        return self.rng.getstate()
    def reseed(self, seed, *, label):
        self.rng.seed(seed)
        self.seeds.append(seed)
        return {"seed": seed, "label": label, "programmed_fixture_only": True}
    def generate_native(self, native):
        self.rng.random()
        return super().generate_native(native)
    def finish_evaluation_guard(self, snapshot):
        self.rng.setstate(snapshot)
        value = {"learning_unchanged": True, "rng_restored_exactly": self.rng.getstate() == snapshot,
                 "fixture_python_rng_only": True, "actual_model_rng_checked": False}
        self.guards.append(value)
        return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    name = "proworksim.software_benchmark_resident_owner_v054"
    spec = importlib.util.spec_from_file_location(name, args.module)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    owner = Owner(Tokenizer(), root / "owner", ["fixture response one", "fixture response two"])
    manager = module.ResidentOwner(owner, output=root / "resident", codec=ScriptedCodec(), synthetic=True)
    manager.socket_root = root / "sockets"
    manager.socket_root.mkdir()
    host = process_identity(os.getpid())
    releases, old_socket, old_claim = [], None, None
    try:
        for ordinal, arm in enumerate(["MATCH", "PROJECT", "MATCH"], 1):
            slot = {"slot_id": "synthetic-resident-" + str(ordinal), "arm": arm, "seed": 10 + ordinal,
                    "instance_id": "synthetic-control"}
            claim = uuid.uuid4().hex
            acquired = manager.acquire(slot=slot, claim_id=claim, authorization=None, host_process=host)
            client = OwnerClient(acquired["session_socket"], acquired["session_identity"])
            if old_socket is not None:
                assert not Path(old_socket).exists()
                try:
                    manager.episode_dispatch(old_claim, {})
                    raise AssertionError("Old claim reached the next session")
                except ValueError:
                    pass
                assert manager.poisoned is None
            begun = client.call("begin", slot=slot, claim_id=claim, authorization=None, started=time.monotonic())
            assert begun["seed"]["seed"] == 10 + ordinal
            assert owner.output.is_relative_to(Path(acquired["session_root"]))
            assert manager.active["child"].sequences != {}
            if arm == "MATCH":
                assert manager.active["child"].bridge.ledger.snapshot()["attempts"] == 0
            else:
                assert manager.active["child"].bridge is None
            tools = [{"type": "function", "function": {"name": value, "parameters": {"type": "object", "properties": {}}}}
                     for value in (sorted(TOOL_NAMES) if arm == "MATCH" else ["terminal"])]
            request = {"model": "raw-qwen3.5-9b-v054-match", "messages": [{"role": "user", "content": "synthetic-" + str(ordinal)}],
                       "tools": tools, "temperature": .7, "max_tokens": 2048, "stream": False}
            if ordinal == 3:
                try:
                    client.call("match_complete", request=request, usage_id="agent")
                    raise AssertionError("Exhausted scripted response unexpectedly generated")
                except RuntimeError:
                    assert manager.poisoned and manager.owner is owner
                    assert manager.active["child"].bridge.ledger.snapshot()["inflight"] is not None
                try:
                    manager.acquire(slot={**slot, "slot_id": "synthetic-another"}, claim_id=uuid.uuid4().hex,
                                    authorization=None, host_process=host)
                    raise AssertionError("Poisoned resident reused")
                except RuntimeError:
                    pass
                break
            if arm == "MATCH":
                result = client.call("match_complete", request=request, usage_id="agent")
                assert result["ledger"]["attempts"] == 1
            else:
                result = client.call("project_complete", request=request)
                assert result["http_status"] == 200
                prompt = result["body"]["prompt_projection"]["rendered_prompt"]
                assert "synthetic-2" in prompt and "synthetic-1" not in prompt
            finished = client.call("finish", entries=[])
            releases.append(manager.release(claim_id=claim, finish_receipt=finished["receipt"]))
            assert manager.owner is owner and manager.status()["state"] == "idle"
            old_socket, old_claim = acquired["session_socket"], claim
        assert owner.seeds == [11, 12, 13] and len(owner.guards) == 2
        assert all(item["quiescence"]["rng_restored_exactly"] for item in releases)
        print(json.dumps(write_new(root / "receipt.json", {"status": "passed", "actual_model_calls": 0,
            "actual_GPU_loads": 0, "actual_tokenizer_used": False, "formal_slots_claimed": 0,
            "checks": ["MATCH_to_PROJECT_same_owner", "new_seed_and_window_each_session",
                "MATCH_ledger_zero_each_session", "PROJECT_no_MATCH_ledger_carried_over",
                "new_owner_call_directory_and_no_previous_prompt_in_PROJECT_input",
                "finish_guard_and_fixture_rng_restore", "old_socket_removed_and_old_claim_fenced",
                "unsettled_failure_poisoned_no_reuse"], "release_receipts": releases,
            "source": reference(args.module)})))
    finally:
        if manager.active and manager.active.get("server"):
            manager.active["server"].shutdown()
            manager.active["server"].server_close()
            manager.active["thread"].join(timeout=5)


if __name__ == "__main__":
    main()
