"""Once-only slots and host deadlines; no model runner or automatic authorization."""
from __future__ import annotations

from contextlib import contextmanager
import copy
import json
from pathlib import Path
import threading
import time

from .software_benchmark_candidates_v054 import checked, reference, write_new
from .software_benchmark_supervision_v054 import (
    assert_outer_launcher_exited, assert_quiet, claim_nonce, start_watchdog,
)
from .storage import atomic_write, digest, json_bytes

VERSION = "software-benchmark-episode-v054"
DEFAULT_CLAIMS = Path(__file__).resolve().parents[2] / "runs/software-benchmark-v054/episode-claims"


class Episode:
    """An entered claim is never resumed or resampled, including infrastructure faults."""

    def __init__(self, slots_reference, slot_id, *, binding, authorization=None,
                 synthetic=False, synthetic_claim_root=None, clock=time.monotonic):
        slots = json.loads(checked(slots_reference).read_text())
        matches = [row for row in slots["slots"] if row["slot_id"] == slot_id]
        if len(matches) != 1:
            raise ValueError("Expected one immutable planned slot")
        self.slot, self.synthetic, self.clock = copy.deepcopy(matches[0]), synthetic, clock
        if synthetic:
            if not slot_id.startswith("synthetic-") or synthetic_claim_root is None:
                raise ValueError("Synthetic controls cannot claim formal slots")
            claims = Path(synthetic_claim_root)
        else:
            if synthetic_claim_root is not None or authorization is None:
                raise ValueError("Formal slots require separate explicit run authorization")
            permit = json.loads(checked(authorization).read_text())
            if (permit.get("execution_authorized") is not True
                    or permit.get("slots_sha256") != slots_reference["sha256"]
                    or slot_id not in permit.get("slot_ids", [])):
                raise ValueError("Formal model and budget authorization is absent")
            claims = DEFAULT_CLAIMS
        if set(binding) != {"configuration", "environment", "owner"}:
            raise ValueError("Bind configuration, environment and owner admission receipts")
        for item in binding.values():
            checked(item)
        claims.mkdir(parents=True, exist_ok=True)
        self.root = claims / digest(slot_id.encode())
        self.root.mkdir(exist_ok=False)  # Atomic global once-only slot claim.
        self.claim_id, self.phase = claim_nonce(), "claimed"
        self.lock, self.owner, self.snapshot = threading.RLock(), None, None
        self.scopes, self.started, self.inflight = [], None, None
        self.guard_path = self.root / "watchdog-guard.json"
        self.guard = {"claim_id": self.claim_id, "stop_requested": False,
                      "request_deadline": None}
        write_new(self.root / "claim.json", {
            "version": VERSION, "claim_id": self.claim_id, "slot": self.slot,
            "slots": slots_reference, "binding": binding, "authorization": authorization,
            "synthetic": synthetic, "resume_or_resample_permitted": False,
        })
        self._save()

    def _save(self):
        atomic_write(self.root / "state.json", json_bytes({
            "version": VERSION, "claim_id": self.claim_id, "slot_id": self.slot["slot_id"],
            "phase": self.phase, "started": self.started, "inflight": self.inflight,
            "entered": (self.root / "entered.json").exists(),
            "model_attempts_inferred": False,
        }))
        atomic_write(self.guard_path, json_bytes(self.guard))

    def register_scope(self, scope):
        if self.phase != "claimed" or scope["claim_id"] != self.claim_id:
            raise ValueError("Register owned scopes before entering this episode")
        if any(item["unit"] == scope["unit"] for item in self.scopes):
            raise ValueError("Duplicate scope")
        self.scopes.append(copy.deepcopy(scope))

    def enter(self, *, owner=None, ref_adapter=None, synthetic_limits=None):
        with self.lock:
            if self.phase != "claimed" or not self.scopes:
                raise RuntimeError("Enter only one fresh claim with admitted scopes")
            if not self.synthetic:
                if {scope["role"] for scope in self.scopes} != {"controller", "actor", "model"}:
                    raise ValueError("All writers and the exclusive model service need owned scopes")
            limits = synthetic_limits or (5400, 6000)
            if synthetic_limits and not self.synthetic:
                raise ValueError("Formal time limits are frozen")
            self.started = self.clock()
            self.soft_at, self.hard_at = (self.started + value for value in limits)
            # Consume the slot before calling anything capable of entering owner state.
            write_new(self.root / "entered.json", {
                "claim_id": self.claim_id, "seed": self.slot["seed"],
                "started": self.started, "soft_at": self.soft_at, "hard_at": self.hard_at,
                "resume_or_resample_permitted": False,
            })
            self.phase = "entering"
            self._save()
            self.watchdog, self.quiescence_path = start_watchdog({
                "claim_id": self.claim_id, "scopes": self.scopes, "hard_at": self.hard_at,
                "guard_path": str(self.guard_path),
            }, self.root)
            try:
                if self.slot["arm"] in {"MATCH", "PROJECT"}:
                    if owner is None:
                        raise ValueError("A real project numerical owner is required")
                    self.owner = owner
                    identity = owner.freeze_identity()
                    if (identity.get("raw_release") is not True
                            or identity.get("checkpoint") is not None
                            or identity.get("adapter_sha256") is not None
                            or identity.get("trained_adapter_loaded", False)):
                        raise ValueError("Only the admitted raw owner may enter")
                    if not self.synthetic:
                        from .software_benchmark_match_v054 import CONTRACT
                        from .software_calibration_runtime_v051 import CalibrationActor
                        if (not isinstance(owner, CalibrationActor) or owner.path != "project"
                                or owner.contract != CONTRACT
                                or identity.get("base_revision")
                                != "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
                                or identity.get("base_manifest", {}).get("sha256")
                                != "030031b27513e399360f26a8db31746e719bb15a3d2f4d68874c1dba3ccc60a6"
                                or owner.inference_profile.get("base_storage_dtype")
                                != "bfloat16_backbone_float32_lm_head"):
                            raise ValueError("Owner differs from the frozen PROJECT numerical path")
                    self.snapshot = owner.capture_evaluation_state()
                    owner.begin_window(self.slot["slot_id"] + ":" + self.claim_id)
                    seed_receipt = owner.reseed(self.slot["seed"], label=self.slot["slot_id"])
                else:
                    if ref_adapter is None or ref_adapter.seed != self.slot["seed"]:
                        raise ValueError("REF must bind the predeclared task seed")
                    seed_receipt = {"seed": ref_adapter.seed, "scope": "every REF request"}
                write_new(self.root / "seed.json", seed_receipt)
                self.phase = "running"
                self._save()
            except BaseException:
                self.close_dispatch("owner_entry_fault")
                raise

    @contextmanager
    def request(self, kind, *, synthetic_seconds=None):
        with self.lock:
            if self.phase != "running" or self.inflight is not None:
                raise RuntimeError("New work requires an idle running episode")
            if self.clock() >= self.soft_at:
                raise RuntimeError("No new work after the frozen soft deadline")
            limit = 1860 if self.slot["arm"] == "REF" else 660
            if synthetic_seconds is not None:
                if not self.synthetic:
                    raise ValueError("Cannot shorten or extend formal request limits")
                limit = synthetic_seconds
            self.inflight = kind
            self.guard["request_deadline"] = min(self.hard_at, self.clock() + limit)
            self._save()
        try:
            yield
        except BaseException:
            self.close_dispatch("request_exception_unknown_usage_preserved")
            raise
        finally:
            with self.lock:
                self.inflight = None
                # Once timeout was observed it cannot be cleared for another request.
                if (self.clock() >= self.guard["request_deadline"]
                        or self.quiescence_path.exists()):
                    self.phase = "closing"
                    self.guard["stop_requested"] = True
                self.guard["request_deadline"] = None
                self._save()

    def close_dispatch(self, reason):
        with self.lock:
            if self.phase in {"quiescent", "locking", "locked"}:
                raise RuntimeError("Episode closure already completed")
            self.phase, self.guard["stop_requested"] = "closing", True
            path = self.root / "dispatch-closed.json"
            if not path.exists():
                write_new(path, {"claim_id": self.claim_id, "reason": reason})
            self._save()

    def finish_owner(self, entries):
        """Normal close only, before stopping the model scope; no claim after kill."""
        with self.lock:
            if self.phase != "running" or self.inflight is not None:
                raise RuntimeError("RNG/learning guard requires a returned, idle owner")
            # Stop further dispatch first; the independent hard timer remains
            # armed while normal owner/SDK cleanup runs.
            self.phase = "draining"
            self._save()
            if self.owner is None:
                return None
            self.owner.finish_evaluation(entries, self.root / "owner-evaluation")
            guard = self.owner.finish_evaluation_guard(self.snapshot)
            if not guard["learning_unchanged"] or not guard["rng_restored_exactly"]:
                raise RuntimeError("Frozen owner/RNG guard failed")
            return write_new(self.root / "owner-close.json", guard)

    def accept_quiescence(self):
        with self.lock:
            result = json.loads(self.quiescence_path.read_text())
            if (result["claim_id"] != self.claim_id or result["scopes"] != self.scopes
                    or not result["all_quiet"] or result["errors"]):
                raise RuntimeError("No complete bound quiescence evidence")
            for scope in self.scopes:
                assert_quiet(scope)  # Candidate locking needs current, not stale, evidence.
                assert_outer_launcher_exited(scope)
            self.phase, self.guard["stop_requested"] = "quiescent", True
            self._save()
            return reference(self.quiescence_path)

    @contextmanager
    def candidate_boundary(self):
        with self.lock:
            if self.phase != "quiescent":
                raise RuntimeError("Candidate export requires all writers to have exited")
            proof = self.accept_quiescence()
            write_new(self.root / "candidate-claim.json", {
                "claim_id": self.claim_id, "quiescence": proof,
                "selection_after_scoring": False,
            })
            self.phase = "locking"
            self._save()
            try:
                yield proof
            except BaseException:
                self.phase = "candidate_export_technical_unknown"
                self._save()
                raise
            self.phase = "locked"
            self._save()


class EpisodeAdapter:
    """Wrap either shared exact-count adapter, including condenser calls."""

    def __init__(self, episode, adapter):
        if episode.phase != "running":
            raise ValueError("Bind the generation gate after the episode enters")
        timed = getattr(adapter, "bridge", adapter)
        if timed.slot_id != episode.slot["slot_id"]:
            raise ValueError("Adapter belongs to a different planned slot")
        # Preparation time is separate; both existing soft/hard checks use this
        # same declared generation origin, without changing either frozen limit.
        timed.started = episode.started
        self.episode, self.adapter = episode, adapter

    def __getattr__(self, name):
        return getattr(self.adapter, name)

    def count(self, request):
        with self.episode.request("exact_tokenization"):
            return self.adapter.count(request)

    def complete(self, request, usage_id):
        with self.episode.request("model:" + usage_id):
            return self.adapter.complete(request, usage_id)
