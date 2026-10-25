"""Retain the v056-r2 REF algorithm with the new owned resident port identities."""
from __future__ import annotations

import copy
from pathlib import Path
import threading
import time

from .software_benchmark_exact_transport_v054 import REF_MODEL
from .software_benchmark_ref_budget_v056 import BudgetLedger, BudgetRefAdapter, OptionalToolsCounter, validate_condition
from .storage import atomic_write, json_bytes

VERSION = "v061-ref-budget-owned-resident-binding-r1"
PORTS = (18161, 18162)


class RecoveryBudgetRefAdapter(BudgetRefAdapter):
    """Only constructor identity admission changes; counting/generation is inherited."""
    def __init__(self, *, transport, folder, slot_id, seed, service_identity, condition):
        self.limits = validate_condition(condition)
        expected = {
            "model_revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a",
            "vllm_version": "0.32.0", "raw_release": True, "adapter_sha256": None,
            "model_manifest_sha256": "030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6",
            "context_limit": 131072, "max_output_tokens": 32768, "service_admission_complete": True,
        }
        if (any(service_identity.get(key) != value for key, value in expected.items())
                or service_identity.get("port") != transport.port or transport.port not in PORTS
                or type(seed) is not int or not 0 <= seed < 2**63):
            raise ValueError("Recovery REF requires the same raw model at its exact new owned port")
        self.transport, self.folder = transport, Path(folder)
        self.folder.mkdir(parents=True, exist_ok=False)
        self.counter = OptionalToolsCounter(transport, self.folder)
        self.ledger = BudgetLedger(condition)
        self.slot_id, self.seed = slot_id, seed
        self.service_identity, self.condition = copy.deepcopy(service_identity), copy.deepcopy(condition)
        self.authorized, self.fixture = True, False
        self.halted, self.started = None, time.monotonic()
        self.lock = threading.Lock()
        self.request_defaults = {
            "model": REF_MODEL, "max_tokens": 32768, "temperature": .6,
            "top_p": .95, "top_k": 20, "min_p": 0., "presence_penalty": 0.,
            "repetition_penalty": 1., "stream": False, "seed": seed,
            "chat_template_kwargs": {"enable_thinking": True}, "add_generation_prompt": True,
            "continue_final_message": False, "add_special_tokens": False,
        }
        self.save()

    def save(self):
        atomic_write(self.folder / "ledger.json", json_bytes({
            "version": VERSION, "inference_algorithm": "v056-qwen-ref-budget-gradient-r2-empty-tools",
            "arm": "REF", "condition_id": self.condition["condition_id"], "slot_id": self.slot_id,
            "service_identity": self.service_identity, "formal_execution_authorized": True,
            "programmed_http_fixture": False, "halted": self.halted,
            "tokenize_http_requests": self.counter.requests, **self.ledger.snapshot(),
        }))
