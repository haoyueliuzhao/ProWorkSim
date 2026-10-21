"""Single programmed CPU combination control; no model/tokenizer/GPU is loaded."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import threading
import time
import uuid

ROOT = Path.cwd()
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
from proworksim.software_benchmark_owner_ipc_v054 import ScriptedOwner, ScriptedCodec  # noqa: E402
from proworksim.software_benchmark_candidates_v054 import reference, write_new  # noqa: E402
from proworksim.software_benchmark_match_v054 import TOOL_NAMES  # noqa: E402
from proworksim.software_benchmark_supervision_v054 import process_identity  # noqa: E402
from proworksim.storage import digest, json_bytes  # noqa: E402


class RNG:
    def __init__(self):
        self.random = random.Random(77)
    def read(self):
        return copy.deepcopy(self.random.getstate())
    def write(self, value):
        self.random.setstate(value)
    def fingerprint(self, value):
        return digest(json_bytes(value))
    def synchronize(self):
        pass


class Tokenizer:
    def apply_chat_template(self, messages, **kwargs):
        return json.dumps({"messages": messages, "tools": kwargs.get("tools")})
    def __call__(self, text, **_):
        return {"input_ids": self.encode(text)}
    def encode(self, text, **_):
        return [ord(value) for value in text]


class Shared:
    def __init__(self):
        self.rng, self.model = RNG(), object()
        self.active, self.maximum, self.calls = 0, 0, 0
        self.entered, self.unblock = threading.Event(), threading.Event()
        self.block = False


class Owner(ScriptedOwner):
    def __init__(self, output, shared):
        super().__init__(Tokenizer(), output, [])
        self.shared, self.model = shared, shared.model
    def capture_evaluation_state(self):
        assert self.phase == "idle" and not self.busy
        return self.shared.rng.read()
    def reseed(self, seed, *, label):
        self.shared.rng.random.seed(seed)
        return {"seed": seed, "label": label, "fixture_python_rng_only": True}
    def generate_native(self, native):
        self.shared.active += 1
        self.shared.maximum = max(self.shared.maximum, self.shared.active)
        self.shared.calls += 1
        self.busy = True
        try:
            if self.shared.block:
                self.shared.entered.set()
                assert self.shared.unblock.wait(5), "Fixture control failed to unblock its programmed request"
            self.responses.append("synthetic " + str(self.shared.rng.random.randrange(1000000)))
            return super().generate_native(native)
        finally:
            self.busy = False
            self.shared.active -= 1
    def finish_evaluation_guard(self, snapshot):
        self.shared.rng.write(snapshot)
        return {"learning_unchanged": True, "rng_restored_exactly": self.shared.rng.read() == snapshot,
                "fixture_python_rng_only": True, "actual_model_rng_checked": False}


def request(arm, label, *, condenser=False):
    names = [] if condenser else sorted(TOOL_NAMES) if arm == "MATCH" else ["terminal"]
    return {"model": "raw-qwen3.5-9b-v054-match", "messages": [{"role": "user", "content": label}],
        "tools": [{"type": "function", "function": {"name": name, "parameters": {"type": "object", "properties": {}}}}
                  for name in names], "temperature": .7, "max_tokens": 2048, "stream": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lifecycle-only", action="store_true")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("proworksim.software_benchmark_interleaved_owner_v054", args.module)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    shared = Shared()
    owner = Owner(root / "owner", shared)
    manager = mod.InterleavedOwner(owner, output=root / "resident", codec=ScriptedCodec(), synthetic=True,
        facade_factory=lambda output: Owner(output, shared), rng_backend=shared.rng)
    manager.socket_root = root / "s"
    manager.socket_root.mkdir()
    host = process_identity(os.getpid())
    receipts, results = [], {}

    def acquire(label, arm, lane):
        slot = {"slot_id": "synthetic-" + label, "arm": arm, "seed": 101 if arm == "MATCH" else 202,
                "instance_id": "synthetic-interleave"}
        claim = uuid.uuid4().hex
        value = manager.acquire(slot=slot, claim_id=claim, authorization=None,
                                host_process=host, session_slot=lane)
        client = mod.InterleavedOwnerClient(value["session_socket"], value["session_identity"])
        client.call("begin", slot=slot, claim_id=claim, authorization=None, started=time.monotonic())
        return value, client

    def close(value, client):
        finish = client.call("finish", entries=[])
        receipt = manager.release(claim_id=value["claim_id"], finish_receipt=finish["receipt"])
        receipts.append(receipt)
        assert not Path(value["session_socket"]).exists()
        return receipt

    def call(client, label):
        if label.startswith("A"):
            return client.call("match_complete", request=request("MATCH", label, condenser=label == "A2"),
                               usage_id="condenser" if label == "A2" else "agent")
        return client.call("project_complete", request=request("PROJECT", label))

    try:
        if args.lifecycle_only:
            a, ca = acquire("payload-cleanup-a", "MATCH", 0)
            call(ca, "A1")
            with ca.turn("match_complete", request=request("MATCH", "A2", condenser=True), usage_id="condenser") as ticket:
                cancelled_request = ticket["request_id"]
            close(a, ca)
            assert not manager.tickets and not manager.queue
            assert cancelled_request in manager.used_request_ids
            a, ca = acquire("idempotent-abort-a", "MATCH", 0)
            b, cb = acquire("idempotent-abort-b", "PROJECT", 1)
            try:
                with manager.condition:
                    manager.reserve_turn(manager.sessions[a["claim_id"]], original_operation="match_count",
                        original_arguments={"request": request("MATCH", "A1")}, request_id=cancelled_request,
                        dispatch_deadline=time.monotonic() + 10)
                raise AssertionError("Purged request identity was replayed")
            except ValueError:
                pass
            shared.block = True
            outputs = []
            generating = threading.Thread(target=lambda: outputs.append(call(ca, "A1")))
            generating.start()
            assert shared.entered.wait(2)
            barrier, aborted = threading.Barrier(2), []
            def abort_twice():
                barrier.wait()
                aborted.append(manager.abort_session(claim_id=b["claim_id"], reason="two simultaneous host observers"))
            threads = [threading.Thread(target=abort_twice) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(3)
            assert len(aborted) == 2 and aborted[0] == aborted[1]
            assert aborted[0]["shared_poisoned"] is False and aborted[0]["cleanup_pending"] is True
            assert manager.poisoned is None
            shared.unblock.set()
            generating.join(3)
            until = time.monotonic() + 3
            while b["claim_id"] in manager.sessions and time.monotonic() < until:
                time.sleep(.01)
            assert b["claim_id"] not in manager.sessions
            assert all(value["claim_id"] != b["claim_id"] for value in manager.tickets.values())
            assert manager.abort_session(claim_id=b["claim_id"], reason="later observer") == aborted[0]
            close(a, ca)
            assert manager.tickets == {} and manager.queue == [] and outputs
            print(json.dumps(write_new(root / "receipt.json", {"passed": True,
                "source": reference(args.module), "model_calls": 0, "GPU_loads": 0, "formal_claims": 0,
                "programmed_generation_operations": shared.calls, "actual_model_rng_checked": False,
                "checks": ["released_payloads_and_cancelled_queue_ids_removed", "small_request_tombstones_prevent_replay",
                    "simultaneous_abort_idempotent_during_other_generation", "cleanup_finishes_on_single_executor",
                    "closed_abort_does_not_repeat_cleanup", "aborted_payloads_reclaimed"]})))
            return
        a, ca = acquire("baseline-a", "MATCH", 0)
        results["base-A1"], results["base-A2"] = call(ca, "A1"), call(ca, "A2")
        assert results["base-A2"]["ledger"]["attempts"] == 2
        assert results["base-A2"]["ledger"]["decisions"] == 1
        close(a, ca)
        b, cb = acquire("baseline-b", "PROJECT", 1)
        results["base-B1"] = call(cb, "B1")
        close(b, cb)
        a, ca = acquire("interleave-a", "MATCH", 0)
        b, cb = acquire("interleave-b", "PROJECT", 1)
        assert len(manager.status()["active_claims"]) == 2
        results["mixed-A1"] = call(ca, "A1")
        results["mixed-B1"] = call(cb, "B1")
        results["mixed-A2"] = call(ca, "A2")
        rb = shared.rng.fingerprint(manager.sessions[b["claim_id"]]["rng"])
        released = close(a, ca)
        assert released["quiescence"]["other_active_claims"] == [b["claim_id"]]
        assert shared.rng.fingerprint(manager.sessions[b["claim_id"]]["rng"]) == rb
        close(b, cb)
        for label in ("A1", "A2", "B1"):
            left, right = results["base-" + label], results["mixed-" + label]
            assert left["body"]["choices"] == right["body"]["choices"]
            assert left["body"]["usage"] == right["body"]["usage"]
            for key in ("rng_before_sha256", "rng_after_sha256"):
                assert left["interleave_evidence"][key] == right["interleave_evidence"][key]
            assert right["interleave_evidence"]["shared_parked_rng_restored"]

        a, ca = acquire("deadline-a", "MATCH", 0)
        before = shared.calls
        ca.hard_deadline = time.monotonic() + 614
        try:
            call(ca, "A1")
            raise AssertionError("Insufficient generation remainder dispatched")
        except mod.InterleaveNotDispatched as error:
            assert error.receipt["dispatched"] is False and error.receipt["generation_calls"] == 0
            assert error.receipt["ledger"]["attempts"] == 0 and error.receipt["usage_unknown"] is False
        ca.hard_deadline = time.monotonic() + 6000
        try:
            with ca.turn("match_complete", request=request("MATCH", "A1"), usage_id="agent") as ticket:
                with manager.condition:
                    manager.tickets[ticket["ticket_id"]]["grant_deadline"] = time.monotonic() - .01
                    manager.condition.notify_all()
                call(ca, "A1")
            raise AssertionError("Expired grant dispatched")
        except mod.InterleaveNotDispatched:
            pass
        assert shared.calls == before
        ca.hard_deadline = time.monotonic() + 10
        close(a, ca)  # A finish is allowed with less than the 615s generation reserve.

        a, ca = acquire("local-abort-a", "MATCH", 0)
        b, cb = acquire("local-abort-b", "PROJECT", 1)
        shared.block = True
        output = []
        worker = threading.Thread(target=lambda: output.append(call(ca, "A1")))
        worker.start()
        assert shared.entered.wait(2)
        local = manager.abort_session(claim_id=b["claim_id"], reason="synthetic CPU host loss")
        assert local["own_dispatched"] is False and local["shared_poisoned"] is False
        assert manager.poisoned is None
        shared.unblock.set()
        worker.join(3)
        assert len(output) == 1
        until = time.monotonic() + 3
        while b["claim_id"] in manager.sessions and time.monotonic() < until:
            time.sleep(.01)
        assert b["claim_id"] not in manager.sessions
        close(a, ca)

        a, ca = acquire("shared-fault-a", "MATCH", 0)
        shared.entered.clear()
        shared.unblock.clear()
        errors = []
        def uncertain():
            try:
                call(ca, "A1")
            except BaseException as error:
                errors.append(error)
        worker = threading.Thread(target=uncertain)
        worker.start()
        assert shared.entered.wait(2)
        fault = manager.abort_session(claim_id=a["claim_id"], reason="synthetic dispatched host loss")
        assert fault["own_dispatched"] is True and fault["shared_poisoned"] is True
        shared.unblock.set()
        worker.join(3)
        assert errors and manager.poisoned and shared.maximum == 1
        receipt = {"passed": True, "source": reference(args.module), "model_calls": 0, "GPU_loads": 0,
            "actual_tokenizer_used": False, "actual_CalibrationActor_construction_tested": False,
            "fixture_python_RNG_not_Torch": True, "formal_claims": 0,
            "programmed_generation_operations": shared.calls, "maximum_concurrent_programmed_generations": shared.maximum,
            "checks": ["baseline_A1_A2_B1_equals_interleaved_A1_B1_A2", "agent_condenser_two_attempts_one_decision",
                "private_RNG_continuation", "finish_A_keeps_B_window_RNG", "stale_socket_removed",
                "insufficient_remaining_time_no_dispatch", "late_commit_no_dispatch", "finish_under_615_seconds",
                "local_CPU_abort_does_not_stop_other_generation", "unknown_dispatched_fault_shared_poison"],
            "release_receipts": receipts}
        print(json.dumps(write_new(root / "receipt.json", receipt)))
    finally:
        shared.unblock.set()
        manager.stop_event.set()
        with manager.condition:
            manager.condition.notify_all()
        for context in list(manager.sessions.values()):
            if context.get("server"):
                context["server"].shutdown()
                context["server"].server_close()
        manager.executor.join(3)


if __name__ == "__main__":
    main()
