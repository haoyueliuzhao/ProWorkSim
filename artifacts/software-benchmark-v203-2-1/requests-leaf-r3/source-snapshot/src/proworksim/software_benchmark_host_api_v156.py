"""Inject provenance capture at v145 physical HTTP boundaries, with no new client.

This adapter neither calls a model nor reads credentials when installed. It
keeps the original ledger authoritative, the original transport retry policy,
and the transport class (including its timeout/fork behavior). Source producers
must supply explicit annotations; missing annotations remain unattributed.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import threading

from . import software_input_provenance_v156 as provenance
from .software_benchmark_deepseek_api_v145 import canonical as transport_canonical

VERSION = "v156-physical-http-provenance-adapter-r1"


class CaptureBeforeDispatchError(RuntimeError):
    """No HTTP was performed by this physical capture boundary."""

    # This proves only the current physical boundary. An earlier retry attempt
    # of this logical call may already have executed, so expose no logical
    # "before_dispatch_proven" shortcut to a recovery scheduler.
    physical_dispatch_not_started = True


def _now():
    return datetime.now(timezone.utc).isoformat()


def _error(error):
    value = {
        "exception_type": type(error).__name__,
        "exception_message_sha256": provenance.digest(str(error).encode()),
    }
    evidence = getattr(error, "evidence", None)
    if isinstance(evidence, dict):
        value["transport_evidence"] = copy.deepcopy(evidence)
    return value


def _write(path, value):
    raw = provenance.canonical(value).encode()
    with path.open("xb") as stream:
        stream.write(raw)
    path.chmod(0o600)
    return {"path": str(path.resolve()), "sha256": provenance.digest(raw), "bytes": len(raw)}


class CaptureStore:
    """Shared diagnostics, but never shared active requests, across explicit forks."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.lock = threading.RLock()
        self._receipts = {}
        self._errors = []

    def put(self, physical_id, receipt):
        with self.lock:
            self._receipts[physical_id] = copy.deepcopy(receipt)

    def error(self, physical_id, phase, error):
        entry = {"request_id": physical_id, "phase": phase, "observed_utc": _now(), **_error(error)}
        with self.lock:
            self._errors.append(entry)

    def receipts(self):
        with self.lock:
            return copy.deepcopy(list(self._receipts.values()))

    def errors(self):
        with self.lock:
            return copy.deepcopy(self._errors)


class PhysicalCapture:
    def __init__(self, store, annotate_payload, identity_for_attempt):
        self.store = store
        self.annotate_payload = annotate_payload
        self.identity_for_attempt = identity_for_attempt
        self.active = None
        self.lock = threading.RLock()

    def begin(self, physical_id, context):
        with self.lock:
            if self.active is not None:
                raise CaptureBeforeDispatchError("Unfinished physical request identity")
            self.active = {
                "context": {**copy.deepcopy(context), "physical_request_id": physical_id},
                "receipt": {
                    "version": VERSION,
                    "request_id": physical_id,
                    "logical_id": context["logical_id"],
                    "attempt_index": context["attempt_index"],
                    "actual_http_dispatch_started": False,
                    "api_response_received": False,
                    "request_capture": None,
                    "response_metadata": None,
                    "observer_errors": [],
                },
                "built": None,
            }

    def _observer_error(self, phase, error):
        current = self.active
        physical_id = current["receipt"]["request_id"] if current else None
        self.store.error(physical_id, phase, error)
        if current:
            current["receipt"]["observer_errors"].append({"phase": phase, **_error(error)})

    def _prepare(self, wire):
        if self.active is None:
            raise CaptureBeforeDispatchError(
                "Physical HTTP requires a successful original reservation"
            )
        current = self.active
        if current["built"] is not None:
            raise CaptureBeforeDispatchError("A physical HTTP identity cannot be dispatched twice")
        context = current["context"]
        identity = {
            "request_id": context["physical_request_id"],
            "episode_id": context["slot_id"],
            "member_id": context["member_id"],
            "decision_id": context["logical_id"],
            "attempt_id": context["physical_request_id"],
            "model_alias": wire["model"],
            "request_time": _now(),
            "usage_id": context["usage_id"],
            "logical_id": context["logical_id"],
            "physical_attempt_index": context["attempt_index"],
        }
        if self.identity_for_attempt:
            extra = self.identity_for_attempt(copy.deepcopy(context), copy.deepcopy(wire))
            if not isinstance(extra, dict):
                raise ValueError("Identity callback must return explicit metadata")
            immutable = set(identity) - {"decision_id"}
            if any(k in extra and extra[k] != identity[k] for k in immutable):
                raise ValueError("Source callback cannot change physical ledger identity")
            identity.update(extra)
        annotated = {"payload": copy.deepcopy(wire), "template_source": None}
        if self.annotate_payload:
            annotated = self.annotate_payload(copy.deepcopy(wire), copy.deepcopy(context))
            if not isinstance(annotated, dict) or set(annotated) - {"payload", "template_source"}:
                raise ValueError("Source callback must return payload and optional template_source")
        built = provenance.build_request(
            annotated["payload"], identity, template_source=annotated.get("template_source")
        )
        raw = transport_canonical(wire).encode()
        if built.payload_bytes != raw or provenance.digest(raw) != context["request_sha256"]:
            raise ValueError("Annotated payload differs from the exact reserved transport bytes")
        capture = provenance.persist_request(self.store.root / "requests", built)
        current["built"] = built
        current["receipt"]["request_capture"] = capture
        self.store.put(context["physical_request_id"], current["receipt"])

    def request(self, original, method, path, payload):
        if (method, path) != ("POST", "/chat/completions") or not isinstance(payload, dict):
            raise CaptureBeforeDispatchError("Capture only accepts the fixed generation endpoint")
        # Freeze the same complete object for capture and the original sender;
        # outside mutation must not race the bytes recorded before dispatch.
        wire = copy.deepcopy(payload)
        try:
            self._prepare(wire)
        except Exception as error:
            self._observer_error("before_dispatch_capture", error)
            raise CaptureBeforeDispatchError(
                "Unable to preserve exact request before dispatch"
            ) from error
        current = self.active
        current["receipt"]["actual_http_dispatch_started"] = True
        try:
            body = original(method, path, wire)
        except BaseException as error:
            # Recording errors must not replace the original exception/retry classification.
            try:
                evidence = _error(error)
                transport_evidence = getattr(error, "evidence", None)
                status = (
                    transport_evidence.get("http_status")
                    if isinstance(transport_evidence, dict)
                    else None
                )
                outcome = (
                    "http_error" if status is not None and status != 200 else "transport_unknown"
                )
                meta = provenance.capture_response(
                    current["built"],
                    None,
                    outcome=outcome,
                    http_status=status,
                    response_time=_now(),
                    error=evidence,
                )
                current["receipt"]["response_metadata"] = meta
                folder = Path(current["receipt"]["request_capture"]["payload"]["path"]).parent
                current["receipt"]["response_metadata_ref"] = _write(
                    folder / "response-metadata.json", meta
                )
            except Exception as observation_error:
                self._observer_error("transport_exception_capture", observation_error)
            raise
        else:
            current["receipt"]["api_response_received"] = True
            # Persist the untouched decoded response before interpreting its usage.
            # Any observer failure is isolated: original settlement still sees body.
            try:
                folder = Path(current["receipt"]["request_capture"]["payload"]["path"]).parent
                current["receipt"]["response_original_ref"] = _write(
                    folder / "response-original.json", body
                )
            except Exception as error:
                self._observer_error("response_original_capture", error)
            try:
                meta = provenance.capture_response(
                    current["built"],
                    body,
                    outcome="success",
                    http_status=200,
                    response_time=_now(),
                )
                current["receipt"]["response_metadata"] = meta
                current["receipt"]["response_metadata_ref"] = _write(
                    folder / "response-metadata.json", meta
                )
            except Exception as error:
                self._observer_error("response_metadata_capture", error)
            return body

    def finish(self, physical_id, ledger, boundary, accounting_error=None):
        """Observe after original settlement, never turn observer failure into replay."""
        current = self.active
        if current is None or current["receipt"]["request_id"] != physical_id:
            self.store.error(
                physical_id, "ledger_capture_binding", ValueError("Active identity mismatch")
            )
            return
        receipt = current["receipt"]
        receipt["accounting_boundary"] = boundary
        if accounting_error is not None:
            receipt["accounting_exception"] = _error(accounting_error)
        try:
            # Read-only targeted receipt; no ledger transaction or policy mutation.
            with sqlite3.connect(Path(ledger.path).resolve().as_uri() + "?mode=ro", uri=True) as db:
                db.row_factory = sqlite3.Row
                row = db.execute(
                    "SELECT * FROM requests WHERE request_id=?", (physical_id,)
                ).fetchone()
            if row is None:
                raise ValueError("Original authoritative ledger lacks its physical reservation")
            receipt["ledger_record"] = dict(row)
            receipt["ledger_entry_for_reconciliation"] = {
                "request_id": physical_id,
                "status": row["status"],
                "usage": json.loads(row["usage_json"]) if row["usage_json"] is not None else None,
            }
        except Exception as error:
            self._observer_error("post_accounting_observation", error)
        try:
            capture = receipt["request_capture"]
            if capture:
                folder = Path(capture["payload"]["path"]).parent
                receipt["final_receipt_ref"] = _write(folder / "physical-receipt.json", receipt)
            self.store.put(physical_id, receipt)
        except Exception as error:
            self._observer_error("final_receipt_capture", error)
            self.store.put(physical_id, receipt)
        finally:
            self.active = None

    def receipts(self):
        return self.store.receipts()

    def errors(self):
        return self.store.errors()


class _LedgerCapture:
    def __init__(self, original, capture):
        self.original, self.capture = original, capture

    def __getattr__(self, name):
        return getattr(self.original, name)

    def reserve(self, **kwargs):
        if self.capture.active is not None:
            raise CaptureBeforeDispatchError("Previous physical capture did not reach accounting")
        physical = self.original.reserve(**kwargs)
        self.capture.begin(physical, kwargs)
        return physical

    def failed(self, physical_id, error):
        accounting_error = None
        try:
            return self.original.failed(physical_id, error)
        except BaseException as failure:
            accounting_error = failure
            raise
        finally:
            self.capture.finish(physical_id, self.original, "failed", accounting_error)

    def settle(self, physical_id, body):
        accounting_error = None
        try:
            return self.original.settle(physical_id, body)
        except BaseException as failure:
            accounting_error = failure
            raise
        finally:
            self.capture.finish(physical_id, self.original, "settle", accounting_error)


def instrument_client(
    client, *, capture_root, annotate_payload=None, identity_for_attempt=None, _store=None
):
    """Install on one already-created v145 client; explicit forks inherit capture.

    Installation sends nothing and accesses no key. The caller supplies an idle,
    exclusively owned client. The original bound fork method remains responsible
    for creating the fork on an explicit subsequent caller request.
    """
    if hasattr(client, "provenance_capture"):
        raise ValueError("A client may be instrumented only once")
    if hasattr(client.transport, "_proworksim_v156_capture_installed"):
        raise ValueError("Different clients must not share an instrumented transport")
    store = _store or CaptureStore(capture_root)
    capture = PhysicalCapture(store, annotate_payload, identity_for_attempt)
    original_request = client.transport.request
    original_fork = client.fork_for_episode

    def request(method, path, payload=None):
        return capture.request(original_request, method, path, payload)

    def fork():
        child = original_fork()
        return instrument_client(
            child,
            capture_root=store.root,
            annotate_payload=annotate_payload,
            identity_for_attempt=identity_for_attempt,
            _store=store,
        )

    client.ledger = _LedgerCapture(client.ledger, capture)
    client.transport.request = request
    client.transport._proworksim_v156_capture_installed = True
    client.fork_for_episode = fork
    client.provenance_capture = capture
    return client
