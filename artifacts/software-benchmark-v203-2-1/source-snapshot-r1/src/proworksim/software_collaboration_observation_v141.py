"""Evaluation-side, append-only collaboration observations for the v141 harness.

This module observes trusted harness receipts. It grants no tool permissions,
performs no model calls, mutates no budget, and exposes no solver-facing tool.
Provider usage, content token counts, tool returns and actual input exposure are
separate measurements. Missing evidence is not converted into a negative fact.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path
import threading
import sys


VERSION = "v141-source-bound-collaboration-observer-r1"
CHANNELS = frozenset({"roles", "tasks", "messages", "reads", "presentations", "artifacts", "usage", "actions"})
KINDS = frozenset({
    "role_state", "task_state", "message_sent", "message_received", "information_read",
    "information_presented", "artifact_published", "artifact_opportunity", "artifact_acquired",
    "artifact_validated", "artifact_review", "artifact_integrated", "version_transition",
    "candidate_locked", "final_delivery", "usage", "action", "coverage",
})
MAX_EVENT_BYTES = 32 * 1024
MAX_TEXT_BYTES = 256 * 1024
MAX_EVENTS = 8192


def load_official_content_counter(manifest_path, *, manifest_sha256):
    """Load only the already-frozen local tokenizer, with no download fallback.

    Counts plain stored content with Tokenizer.encode, not a rendered chat
    request. Billed provider input remains authoritative for whole-request cost.
    """
    from .software_benchmark_deepseek_tokenizer_v055 import _check_file
    path = Path(manifest_path).resolve()
    raw = path.read_bytes()
    if _sha(raw) != manifest_sha256:
        raise ObservationError("Frozen tokenizer manifest changed")
    value = json.loads(raw)
    if (value.get("version") != "software-benchmark-v055-official-tokenizer-preparation-r1"
            or value.get("recipe_version") != "0.2.0"
            or value.get("tokenizer_model") != "deepseek-ai/DeepSeek-V4.1-Flash-1017"):
        raise ObservationError("Unexpected frozen content tokenizer")
    for reference in value["installed_files"]:
        _check_file(reference)
    refs = [item for item in value["tokenizer_files"] if Path(item["path"]).name == "tokenizer.json"]
    if len(refs) != 1:
        raise ObservationError("Exactly one pinned tokenizer vocabulary is required")
    tokenizer_path = _check_file(refs[0])
    overlay = Path(value["overlay_path"]).resolve()
    if str(overlay) not in sys.path:
        sys.path.insert(0, str(overlay))
    recipe = importlib.import_module("deepseek_recipe")
    if not Path(recipe.__file__).resolve().is_relative_to(overlay):
        raise ObservationError("Another tokenizer recipe overlay is active")
    tokenizer = recipe.Tokenizer.from_file(str(tokenizer_path))
    metadata = {"tokenizer_id": "v141-content:" + manifest_sha256,
                "manifest_path": str(path), "manifest_sha256": manifest_sha256,
                "vocabulary_sha256": refs[0]["sha256"],
                "method": "Tokenizer.encode_full_vocabulary_without_chat_template",
                "content_tokens_are_provider_billing": False, "network_requests": 0}

    def count(text):
        return len(tokenizer.encode(text))
    return count, metadata


class ObservationError(ValueError):
    """The observation is inconsistent; preserve the underlying experiment."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _bounded_metadata(value):
    """Reject whole-world payloads before making a JSON/string copy."""
    stack, nodes, characters = [(value, 0)], 0, 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 2048 or depth > 16:
            raise ObservationError("Observation metadata is not a bounded event")
        if isinstance(item, dict):
            if len(item) > 128 or any(not isinstance(key, str) for key in item):
                raise ObservationError("Metadata dictionaries must be small string-keyed mappings")
            stack.extend((part, depth+1) for pair in item.items() for part in pair)
        elif isinstance(item, (list, tuple)):
            if len(item) > 256:
                raise ObservationError("Metadata lists must contain bounded references")
            stack.extend((part, depth+1) for part in item)
        elif isinstance(item, str):
            characters += len(item)
            if len(item) > 8192 or characters > MAX_EVENT_BYTES:
                raise ObservationError("Store original content separately; do not embed a full history/state")
        elif item is not None and type(item) not in {int, float, bool}:
            raise ObservationError("Observation metadata must be JSON data")


def _string(value, label, maximum=512):
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ObservationError(f"{label} must be a bounded nonempty string")
    return value


def _integer(value, label):
    if type(value) is not int or value < 0:
        raise ObservationError(f"{label} must be a nonnegative integer")
    return value


def _ref(value):
    if not isinstance(value, dict) or not value:
        raise ObservationError("A real source receipt reference is required")
    _json(value)
    return value


def _version(value):
    if not isinstance(value, dict):
        raise ObservationError("An exact version reference is required")
    for key in ("object_id", "version_id"):
        _string(value.get(key), key)
    return _json(value)


def _union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _overlap(start, end, intervals):
    return sum(max(0, min(end, right) - max(start, left)) for left, right in _union(intervals))


class ObservationLog:
    """A bounded single-writer sidecar; neither ``root`` nor output is a tool.

    ``token_counter`` must count text with an identified frozen tokenizer. If it
    is absent, direct content token counts remain None. ``members`` is frozen.
    Only a runtime that actually sent the selected input may record presentation.
    Evidence references must be supplied by the trusted runtime, not the model.
    """

    def __init__(self, root, team_id, members, *, token_counter=None, tokenizer_id=None):
        self.root = Path(root)
        self.team_id = _string(team_id, "team_id")
        self.members = tuple(members)
        if not self.members or len(self.members) > 16 or len(set(self.members)) != len(self.members):
            raise ObservationError("Freeze a nonempty, unique, bounded member registry")
        for member in self.members:
            _string(member, "member")
        if (token_counter is None) != (tokenizer_id is None):
            raise ObservationError("A content counter requires its tokenizer identity")
        if token_counter is not None and not callable(token_counter):
            raise ObservationError("token_counter must be callable")
        self.token_counter, self.tokenizer_id = token_counter, tokenizer_id
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "events.jsonl"
        self._lock = (self.root / "writer.lock").open("a+b")
        try:
            fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lock.close()
            raise ObservationError("This observation stream already has a writer") from None
        self._thread_lock = threading.RLock()
        self._closed = False
        self._events = {}
        self._rows = {}
        self._used_requests = {}
        self._request_actors = {}
        self._presented_requests = set()
        self._usage = {}
        self._coverage = {}
        self._size = 0
        self._last_hash = None
        self._meta = {"version": VERSION, "team_id": self.team_id,
                      "members": list(self.members), "tokenizer_id": tokenizer_id,
                      "audience": "evaluation_only", "solver_access": False}
        try:
            if self.path.exists():
                self._replay()
            else:
                self._append_line({"meta": self._meta})
        except Exception:
            self.close()
            raise

    def close(self):
        if not self._closed:
            self._closed = True
            fcntl.flock(self._lock, fcntl.LOCK_UN)
            self._lock.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def solver_view(self, *_args, **_kwargs):
        raise PermissionError("Collaboration observations are evaluation-only")

    def _append_line(self, value):
        raw = (_json(value) + "\n").encode()
        if len(raw) > MAX_EVENT_BYTES:
            raise ObservationError("Observation exceeds the bounded metadata size")
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            if os.fstat(fd).st_size != self._size:
                raise ObservationError("Observation stream changed outside its writer")
            view = memoryview(raw)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("Observation write did not advance")
                view = view[written:]
        finally:
            os.close(fd)
        self._size += len(raw)

    def _replay(self):
        with self.path.open("rb") as stream:
            for index, raw in enumerate(stream):
                if not raw.endswith(b"\n") or len(raw) > MAX_EVENT_BYTES:
                    raise ObservationError("Incomplete or oversized observation record")
                row = json.loads(raw)
                if index == 0:
                    if row != {"meta": self._meta}:
                        raise ObservationError("Observation identity or tokenizer changed")
                else:
                    body = {key: value for key, value in row.items() if key != "sha256"}
                    if (row.get("sequence") != index or row.get("previous_sha256") != self._last_hash
                            or row.get("sha256") != _sha(_json(body).encode())):
                        raise ObservationError("Observation chain changed")
                    fingerprint = self._validate(row["event_id"], row["kind"], row["actor"], row["data"])
                    if row["event_id"] in self._events:
                        raise ObservationError("Duplicated persisted event identity")
                    self._apply(row, fingerprint)
                self._size += len(raw)
        if self._size == 0:
            raise ObservationError("Empty observation file is not an initialized stream")

    def _content(self, text):
        if not isinstance(text, str):
            raise ObservationError("Original content must be text")
        if len(text) > MAX_TEXT_BYTES:
            raise ObservationError("Content exceeds the observation bound; use source-range events")
        raw = text.encode()
        if len(raw) > MAX_TEXT_BYTES:
            raise ObservationError("Content exceeds the observation bound; use source-range events")
        digest = _sha(raw)
        tokens = None if self.token_counter is None else _integer(self.token_counter(text), "content tokens")
        folder = self.root / "content"
        folder.mkdir(mode=0o700, exist_ok=True)
        path = folder / (digest + ".txt")
        if path.exists():
            if _sha(path.read_bytes()) != digest:
                raise ObservationError("Content-addressed observation changed")
        else:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
        return {"path": "content/" + path.name, "sha256": digest, "bytes": len(raw),
                "characters": len(text), "tokens": tokens, "tokenizer_id": self.tokenizer_id}

    def _member(self, actor):
        if actor not in self.members:
            raise ObservationError("Foreign member cannot be observed in this team")

    def _prior(self, event_id, kind):
        row = self._rows.get(event_id)
        if row is None or row["kind"] not in ({kind} if isinstance(kind, str) else kind):
            raise ObservationError("Missing or incorrectly typed source event")
        return row

    def _patch(self, event_id):
        return self._prior(event_id, "artifact_published")

    def _latest_opportunity(self, publication, actor):
        return next((row for row in reversed(self._rows.values())
                     if row["kind"] == "artifact_opportunity" and row["actor"] == actor
                     and row["data"]["publication"] == publication), None)

    def _content_ref(self, content):
        _ref(content)
        digest = content.get("sha256")
        if (not isinstance(digest, str) or len(digest) != 64
                or content.get("path") != "content/" + digest + ".txt"
                or content.get("tokenizer_id") != self.tokenizer_id):
            raise ObservationError("Text metadata must reference its own immutable content blob")
        path = self.root / content["path"]
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_TEXT_BYTES:
            raise ObservationError("Content blob is absent or outside the bounded source")
        raw = path.read_bytes()
        if (_sha(raw) != digest or len(raw) != content.get("bytes")
                or len(raw.decode()) != content.get("characters")):
            raise ObservationError("Content metadata does not match original text")
        if content.get("tokens") is not None:
            _integer(content["tokens"], "content tokens")
        if self.tokenizer_id is None and content.get("tokens") is not None:
            raise ObservationError("A character estimate is not a tokenizer count")

    def _validate(self, event_id, kind, actor, data):
        _string(event_id, "event_id")
        self._member(actor)
        if kind not in KINDS or not isinstance(data, dict):
            raise ObservationError("Unknown observation kind or data shape")
        fingerprint = _sha(_json({"kind": kind, "actor": actor, "data": data}).encode())
        if event_id in self._events:
            if self._events[event_id] != fingerprint:
                raise ObservationError("An event ID cannot change its meaning")
            return fingerprint
        if len(self._events) >= MAX_EVENTS:
            raise ObservationError("Observation event bound reached")
        if kind in {"usage", "action", "information_presented"} and data.get("request_id"):
            owner = self._request_actors.get(data["request_id"])
            if owner is not None and owner != actor:
                raise ObservationError("A provider request cannot cross member identities")
        if kind != "coverage":
            _ref(data.get("evidence"))
        if kind in {"role_state", "task_state"}:
            _string(data.get("state_id"), "state_id")
            _ref(data.get("state"))
        elif kind == "message_sent":
            recipients = data.get("recipients")
            if (not isinstance(recipients, list) or not recipients or actor in recipients
                    or len(set(recipients)) != len(recipients) or not set(recipients) <= set(self.members)):
                raise ObservationError("A directed message needs legal distinct peer recipients")
            self._content_ref(data.get("content"))
        elif kind == "message_received":
            sent = self._prior(data.get("sent_event"), "message_sent")
            if actor not in sent["data"]["recipients"] or data.get("actually_obtained") is not True:
                raise ObservationError("Sending or queueing does not prove receipt")
        elif kind == "information_read":
            if data.get("authorized") is not True:
                raise ObservationError("An unauthorized read cannot establish information acquisition")
            _version(data.get("source_reference"))
            _string(data.get("path"), "path")
            self._content_ref(data.get("content"))
            digest = data.get("full_text_sha256")
            if not isinstance(digest, str) or len(digest) != 64:
                raise ObservationError("The immutable full-text hash is required")
            start, end, total = [_integer(data.get(k), k) for k in ("start", "end", "total")]
            if not 0 <= start <= end <= total or data["content"]["characters"] != end-start:
                raise ObservationError("Returned text does not match the exact source range")
        elif kind == "information_presented":
            _string(data.get("request_id"), "request_id")
            if data["request_id"] in self._presented_requests:
                raise ObservationError("One actual model input can only be presented once")
            ids = data.get("information_events")
            if not isinstance(ids, list) or len(ids) != len(set(ids)):
                raise ObservationError("Actual input information IDs must be unique")
            for key in ids:
                prior = self._prior(key, {"information_read", "message_received"})
                if prior["actor"] != actor:
                    raise ObservationError("Another member's private acquisition is not this member's input")
            _ref(data.get("actual_input"))
        elif kind == "artifact_published":
            _string(data.get("patch_id"), "patch_id")
            _version(data.get("source_reference"))
            _ref(data.get("content_identity"))
            if any(r["kind"] == kind and r["data"]["patch_id"] == data["patch_id"] for r in self._rows.values()):
                raise ObservationError("A fixed patch identity cannot be republished")
        elif kind == "artifact_opportunity":
            patch = self._patch(data.get("publication"))
            if actor == patch["actor"] or type(data.get("eligible")) not in {bool, type(None)}:
                raise ObservationError("Opportunity is a tri-state fact about a peer recipient")
        elif kind == "artifact_acquired":
            opportunity = self._prior(data.get("opportunity"), "artifact_opportunity")
            current = self._latest_opportunity(opportunity["data"]["publication"], actor)
            if (opportunity["actor"] != actor or opportunity["data"]["eligible"] is not True
                    or current is not opportunity):
                raise ObservationError("A partner artifact needs a proven legal opportunity")
            _version(data.get("adopted_reference"))
        elif kind == "artifact_validated":
            acquisition = self._prior(data.get("acquisition"), "artifact_acquired")
            if (acquisition["actor"] != actor
                    or _version(data.get("tested_reference")) != _version(acquisition["data"]["adopted_reference"])
                    or type(data.get("executed")) is not bool
                    or type(data.get("passed")) not in {bool, type(None)}
                    or (data.get("passed") is True and data.get("executed") is not True)):
                raise ObservationError("Partner validation requires actual same-version test evidence")
        elif kind == "artifact_review":
            validation = self._prior(data.get("validation"), "artifact_validated")
            if validation["actor"] != actor or data.get("decision") not in {"accept", "request_changes", "inconclusive"}:
                raise ObservationError("Review identity or explicit decision is invalid")
            if data["decision"] == "accept" and validation["data"].get("passed") is not True:
                raise ObservationError("Acceptance cannot turn failed or missing test evidence into passing")
        elif kind == "artifact_integrated":
            patch = self._patch(data.get("publication"))
            _version(data.get("result_reference"))
            if actor != self.members[0] or data.get("explicit_agent_action") is not True:
                raise ObservationError("Only explicit designated-integrator adoption is a final integration")
            opportunity = self._latest_opportunity(data["publication"], actor)
            if patch["actor"] != actor and (opportunity is None or opportunity["data"]["eligible"] is not True):
                raise ObservationError("Final integrator lacks a proven legal partner-artifact opportunity")
        elif kind == "version_transition":
            _version(data.get("from_reference"))
            _version(data.get("to_reference"))
            if data["from_reference"] == data["to_reference"]:
                raise ObservationError("A version transition must actually identify a changed version")
        elif kind == "candidate_locked":
            if actor != self.members[0] or data.get("generation_closed") is not True:
                raise ObservationError("Only the designated closed final candidate can be locked")
            _version(data.get("reference"))
            if any(r["kind"] == kind for r in self._rows.values()):
                raise ObservationError("The final candidate is unique, not best-of-members")
        elif kind == "final_delivery":
            lock = self._prior(data.get("candidate_lock"), "candidate_locked")
            if actor != lock["actor"] or type(data.get("legal")) is not bool:
                raise ObservationError("Delivery must be explicitly legal or illegal for the designated member")
            _version(data.get("submitted_reference"))
            if any(row["kind"] == "final_delivery" for row in self._rows.values()):
                raise ObservationError("Only the last legal delivery at closure is measured, not a union of old attempts")
            chain = data.get("artifact_chain", [])
            if not isinstance(chain, list) or len({item.get("integration") for item in chain}) != len(chain):
                raise ObservationError("Final delivery provenance cannot duplicate integrations")
            for item in chain:
                integrated = self._prior(item.get("integration"), "artifact_integrated")
                validated = self._prior(item.get("validation"), "artifact_validated")
                acquired = self._prior(validated["data"]["acquisition"], "artifact_acquired")
                opportunity = self._prior(acquired["data"]["opportunity"], "artifact_opportunity")
                if (integrated["actor"] != actor
                        or integrated["data"]["publication"] != opportunity["data"]["publication"]
                        or validated["data"].get("executed") is not True
                        or validated["data"].get("passed") is not True):
                    raise ObservationError("Delivery provenance needs obtained and validated partner work")
                current = integrated["data"]["result_reference"]
                for transition_id in item.get("transitions", []):
                    transition = self._prior(transition_id, "version_transition")
                    if transition["actor"] != actor or transition["data"]["from_reference"] != current:
                        raise ObservationError("Final lineage is discontinuous or belongs to another member")
                    current = transition["data"]["to_reference"]
                if current != data["submitted_reference"]:
                    raise ObservationError("Integrated version does not reach the delivered version")
        elif kind == "usage":
            request = _string(data.get("request_id"), "request_id")
            _string(data.get("purpose"), "purpose")
            if data.get("status") not in {"settled", "uncertain"}:
                raise ObservationError("Only explicit actual or uncertain provider receipts are observable")
            usage = data.get("usage")
            if data["status"] == "settled":
                if not isinstance(usage, dict):
                    raise ObservationError("A settled request requires actual provider token counts")
                prompt = _integer(usage.get("prompt_tokens"), "prompt_tokens")
                output = _integer(usage.get("completion_tokens"), "completion_tokens")
                if usage.get("total_tokens", prompt+output) != prompt+output:
                    raise ObservationError("Provider token counts do not reconcile")
                hit, miss = usage.get("prompt_cache_hit_tokens"), usage.get("prompt_cache_miss_tokens")
                for value in (hit, miss):
                    if value is not None and _integer(value, "cache tokens") > prompt:
                        raise ObservationError("Cache tokens exceed the full input")
                if hit is not None and miss is not None and hit+miss != prompt:
                    raise ObservationError("Cache hits and misses do not reconcile")
            elif usage is not None:
                raise ObservationError("Uncertain usage must remain unknown, not an invented zero")
            cost = data.get("cost_cny")
            if cost is not None:
                try:
                    parsed = Decimal(str(cost))
                except InvalidOperation as error:
                    raise ObservationError("Invalid settled cost") from error
                if not parsed.is_finite() or parsed < 0:
                    raise ObservationError("Cost must be finite and nonnegative")
            old = self._usage.get(request)
            if old and (old["actor"] != actor or old["data"]["purpose"] != data["purpose"]
                        or (old["data"]["status"] == "settled" and old["data"] != data)):
                raise ObservationError("A provider receipt cannot move member or change settled accounting")
        elif kind == "action":
            _string(data.get("tool"), "tool")
            if type(data.get("ok")) not in {bool, type(None)}:
                raise ObservationError("Action result must remain explicitly known or unknown")
            request = data.get("request_id")
            if request is not None:
                _string(request, "request_id")
                if request in self._used_requests:
                    raise ObservationError("A request's whole cost cannot be attributed to two actions")
        elif kind == "coverage":
            if data.get("channel") not in CHANNELS or type(data.get("complete")) is not bool:
                raise ObservationError("Coverage must name a known channel and explicit completion")
            _ref(data.get("evidence"))
        return fingerprint

    def _apply(self, row, fingerprint):
        self._events[row["event_id"]] = fingerprint
        self._rows[row["event_id"]] = row
        self._last_hash = row["sha256"]
        if row["kind"] == "usage":
            self._usage[row["data"]["request_id"]] = row
        elif row["kind"] == "action" and row["data"].get("request_id"):
            self._used_requests[row["data"]["request_id"]] = row["event_id"]
        elif row["kind"] == "coverage":
            self._coverage[row["data"]["channel"]] = row["data"]["complete"]
        if row["kind"] in {"usage", "action", "information_presented"} and row["data"].get("request_id"):
            self._request_actors[row["data"]["request_id"]] = row["actor"]
        if row["kind"] == "information_presented":
            self._presented_requests.add(row["data"]["request_id"])

    def record(self, event_id, kind, actor, **data):
        """Append a typed trusted receipt; an exact duplicate is idempotent."""
        with self._thread_lock:
            if self._closed:
                raise ObservationError("Observation writer is closed")
            _bounded_metadata(data)
            data = json.loads(_json(data))
            fingerprint = self._validate(event_id, kind, actor, data)
            if event_id in self._events:
                return {"event_id": event_id, "duplicate": True, "sha256": self._rows[event_id]["sha256"]}
            body = {"sequence": len(self._events)+1, "event_id": event_id, "kind": kind,
                    "actor": actor, "data": data, "previous_sha256": self._last_hash}
            row = {**body, "sha256": _sha(_json(body).encode())}
            self._append_line(row)
            self._apply(row, fingerprint)
            return {"event_id": event_id, "duplicate": False, "sha256": row["sha256"]}

    def record_message_sent(self, event_id, actor, recipients, text, *, evidence):
        self._member(actor)
        return self.record(event_id, "message_sent", actor, recipients=list(recipients),
                           content=self._content(text), evidence=evidence)

    def record_message_received(self, event_id, actor, sent_event, *, actually_obtained, evidence):
        return self.record(event_id, "message_received", actor, sent_event=sent_event,
                           actually_obtained=actually_obtained, evidence=evidence)

    def record_information_read(self, event_id, actor, *, source_reference, path, full_text_sha256,
                                start, end, total, text, authorized, evidence):
        self._member(actor)
        if authorized is not True:
            raise ObservationError("Denied reads cannot become acquired information")
        return self.record(event_id, "information_read", actor, source_reference=source_reference,
                           path=path, full_text_sha256=full_text_sha256, start=start, end=end, total=total,
                           content=self._content(text), authorized=authorized, evidence=evidence)

    def record_information_presented(self, event_id, actor, request_id, information_events, *, actual_input, evidence):
        return self.record(event_id, "information_presented", actor, request_id=request_id,
                           information_events=list(information_events), actual_input=actual_input, evidence=evidence)

    def record_usage(self, event_id, actor, request_id, purpose, status, usage, *, cost_cny=None, receipt):
        return self.record(event_id, "usage", actor, request_id=request_id, purpose=purpose,
                           status=status, usage=usage, cost_cny=None if cost_cny is None else str(cost_cny),
                           evidence=receipt)

    def record_action(self, event_id, actor, tool, request_id, ok, *, evidence):
        return self.record(event_id, "action", actor, tool=tool, request_id=request_id, ok=ok, evidence=evidence)

    def record_coverage(self, event_id, channel, complete, *, evidence):
        return self.record(event_id, "coverage", self.members[0], channel=channel, complete=complete, evidence=evidence)

    def summary(self):
        """Return evaluation metrics, preserving unobserved/uncertain components."""
        rows = list(self._rows.values())
        totals = Counter(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        by_member, by_purpose = defaultdict(Counter), defaultdict(Counter)
        uncertain, cost_unknown, cache_unknown = 0, 0, 0
        cache_hit, cache_miss = 0, 0
        cost = Decimal(0)
        for row in self._usage.values():
            data = row["data"]
            by_member[row["actor"]]["requests"] += 1
            by_purpose[data["purpose"]]["requests"] += 1
            if data["status"] == "uncertain":
                uncertain += 1
                continue
            usage = data["usage"]
            counts = {"prompt_tokens": usage["prompt_tokens"], "completion_tokens": usage["completion_tokens"],
                      "total_tokens": usage["prompt_tokens"]+usage["completion_tokens"]}
            totals.update(counts)
            by_member[row["actor"]].update(counts)
            by_purpose[data["purpose"]].update(counts)
            hit, miss = usage.get("prompt_cache_hit_tokens"), usage.get("prompt_cache_miss_tokens")
            cache_unknown += hit is None or miss is None
            cache_hit += hit or 0
            cache_miss += miss or 0
            for bucket in (by_member[row["actor"]], by_purpose[data["purpose"]]):
                bucket['known_cache_hit_tokens'] += hit or 0
                bucket['known_cache_miss_tokens'] += miss or 0
                bucket['requests_without_cache_receipt'] += int(hit is None or miss is None)
                bucket['requests_without_cost_receipt'] += int(data['cost_cny'] is None)
            if data["cost_cny"] is None:
                cost_unknown += 1
            else:
                cost += Decimal(data["cost_cny"])
        reads = [row for row in rows if row["kind"] == "information_read"]
        seen_by_member, team_seen = defaultdict(list), defaultdict(list)
        same_member, cross_member, chars = 0, 0, 0
        for row in reads:
            data, member = row["data"], row["actor"]
            key = (data["path"], data["full_text_sha256"])
            start, end = data["start"], data["end"]
            same = _overlap(start, end, seen_by_member[(member, key)])
            any_seen = _overlap(start, end, team_seen[key])
            same_member += same
            cross_member += any_seen-same
            chars += end-start
            seen_by_member[(member, key)].append((start, end))
            team_seen[key].append((start, end))
        presented = Counter()
        for row in rows:
            if row["kind"] == "information_presented":
                for event in row["data"]["information_events"]:
                    presented[(row["actor"], event)] += 1
        publications = [row for row in rows if row["kind"] == "artifact_published"]
        opportunities, ever_eligible = defaultdict(dict), set()
        for row in rows:
            if row["kind"] == "artifact_opportunity":
                opportunities[row["data"]["publication"]][row["actor"]] = row["data"]["eligible"]
                if row["data"]["eligible"] is True:
                    ever_eligible.add(row["data"]["publication"])
        eligible, unknown = set(), set()
        for publication in publications:
            # Partner code use is relative to the predeclared final integrator.
            # The author's candidate being independently reviewed is a separate
            # review measurement, not a failed adoption of one's own code.
            if publication["actor"] == self.members[0]:
                continue
            peers = {self.members[0]}
            observed = opportunities[publication["event_id"]]
            if any(row["kind"] == "artifact_opportunity" and row["actor"] == self.members[0]
                   and row["data"]["publication"] == publication["event_id"]
                   and row["data"]["eligible"] is True for row in rows):
                eligible.add(publication["event_id"])
            elif any(observed.get(member) is None for member in peers):
                unknown.add(publication["event_id"])
        used, obtained, validated = set(), set(), set()
        for row in rows:
            data = row["data"]
            if row["kind"] == "artifact_acquired":
                obtained.add(self._rows[data["opportunity"]]["data"]["publication"])
            elif row["kind"] == "artifact_validated" and data["executed"] and data["passed"] is True:
                acquisition = self._rows[data["acquisition"]]
                validated.add(self._rows[acquisition["data"]["opportunity"]]["data"]["publication"])
            elif row["kind"] == "final_delivery" and data["legal"]:
                for item in data.get("artifact_chain", []):
                    used.add(self._rows[item["integration"]]["data"]["publication"])
        artifacts_complete = self._coverage.get("artifacts") is True and not unknown
        missing_usage = set(self._request_actors)-set(self._usage)
        complete_usage = self._coverage.get("usage") is True and not uncertain and not missing_usage
        messages = [row for row in rows if row["kind"] == "message_sent"]
        direct_tokens_known = sum(row["data"]["content"]["tokens"] or 0 for row in messages)
        direct_unknown = sum(row["data"]["content"]["tokens"] is None for row in messages)
        message_presentations = sum(count for (actor, event), count in presented.items()
                                    if self._rows[event]["kind"] == "message_received")
        read_presentations = sum(count for (actor, event), count in presented.items()
                                 if self._rows[event]["kind"] == "information_read")
        action_tokens = defaultdict(Counter)
        for request_id, event_id in self._used_requests.items():
            action = self._rows[event_id]
            usage = self._usage.get(request_id)
            if usage is None or usage["data"]["status"] != "settled":
                action_tokens[action["data"]["tool"]]["unknown_usage_requests"] += 1
            elif usage["actor"] != action["actor"]:
                raise ObservationError("Action and actual provider receipt belong to different members")
            else:
                counts = usage["data"]["usage"]
                action_tokens[action["data"]["tool"]]["whole_request_tokens"] += counts["prompt_tokens"]+counts["completion_tokens"]
                action_tokens[action["data"]["tool"]]["requests"] += 1
        return {
            "version": VERSION, "team_id": self.team_id, "members": list(self.members),
            "audience": "evaluation_only", "solver_access": False, "event_count": len(rows),
            "last_event_sha256": self._last_hash, "coverage": dict(self._coverage),
            "usage": {"known_actual_tokens": dict(totals), "actual_total_tokens": totals["total_tokens"] if complete_usage else None,
                      "unique_requests": len(self._request_actors), "receipt_requests": len(self._usage),
                      "requests_without_usage": len(missing_usage), "uncertain_requests": uncertain,
                      "known_cache_hit_tokens": cache_hit, "known_cache_miss_tokens": cache_miss,
                      "cache_hit_tokens": cache_hit if complete_usage and not cache_unknown else None,
                      "cache_miss_tokens": cache_miss if complete_usage and not cache_unknown else None,
                      "known_cost_CNY": str(cost), "total_cost_CNY": str(cost) if complete_usage and not cost_unknown else None,
                      "settled_requests_without_cost": cost_unknown,
                      "by_member": dict(by_member), "by_purpose": dict(by_purpose)},
            "messages": {"sent": len(messages), "obtained_receipts": sum(row["kind"] == "message_received" for row in rows),
                         "unique_obtained_pairs": len({(row["actor"], row["data"]["sent_event"])
                                                       for row in rows if row["kind"] == "message_received"}),
                         "observed_model_presentations": message_presentations,
                         "actual_model_presentations": message_presentations
                         if self._coverage.get("presentations") is True else None,
                         "direct_content_tokens_known": direct_tokens_known,
                         "direct_content_tokens": direct_tokens_known
                         if not direct_unknown and self._coverage.get("messages") is True else None,
                         "contents_without_tokenizer_count": direct_unknown,
                         "net_communication_token_cost": None},
            "information": {"returned_read_characters": chars, "same_member_reread_characters": same_member,
                            "returned_content_tokens_known": sum(r['data']['content']['tokens'] or 0 for r in reads),
                            "returned_content_tokens": sum(r['data']['content']['tokens'] or 0 for r in reads)
                            if self._coverage.get('reads') is True and all(r['data']['content']['tokens'] is not None for r in reads) else None,
                            "content_token_measurement_includes_context": False,
                            "cross_member_first_acquisition_overlap_characters": cross_member,
                            "source_bound_overlap_ratio": (same_member+cross_member)/chars
                            if chars and self._coverage.get("reads") is True else None,
                            "waste_or_semantic_duplication_ratio": None,
                            "read_events_presented_to_model": len({event for actor, event in presented
                                                                   if self._rows[event]["kind"] == "information_read"}),
                            "observed_model_presentations": read_presentations,
                            "actual_model_presentations": read_presentations
                            if self._coverage.get("presentations") is True else None,
                            "presentation_coverage_complete": self._coverage.get("presentations") is True},
            "artifacts": {"published": len(publications), "known_eligible_partner_artifacts": len(eligible),
                          "R_use_scope": "partner_code_published_by_other_members_for_designated_final_integrator",
                          "independent_review_events": sum(row["kind"] == "artifact_review" for row in rows),
                          "opportunity_unknown_artifacts": len(unknown), "obtained": len(obtained & eligible),
                          "same_version_public_test_passed": len(validated & eligible),
                          "entered_legal_delivery_chain": len(used & eligible),
                          "R_use": len(used & eligible)/len(eligible) if artifacts_complete and eligible else None,
                          "R_use_denominator_complete": artifacts_complete,
                          "semantic_or_causal_contribution_proven": False},
            "actions": {"count": sum(row["kind"] == "action" for row in rows),
                        "whole_request_attribution": dict(action_tokens), "attribution_is_net_tool_cost": False},
            "role_state_events": sum(row["kind"] == "role_state" for row in rows),
            "task_state_events": sum(row["kind"] == "task_state" for row in rows),
            "changes_to_model_budget": 0,
        }


@contextmanager
def observation_log(*args, **kwargs):
    """Explicit lifetime helper, useful for one controller generation lifecycle."""
    with ObservationLog(*args, **kwargs) as observer:
        yield observer
