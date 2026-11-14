"""Occurrence-based input provenance for Communication Pilot V1 (CPU only).

Offsets refer to the actual canonical JSON UTF-8 request, not a text-search
reconstruction. JSON byte coverage, local-token estimates and provider-exact
prompt attribution are separate. Unknown inputs never become self-history.
This module creates no client, network connection, model, container or trainer.
"""

from __future__ import annotations

from collections import Counter
from bisect import bisect_right
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re

from .software_benchmark_usage_metrics_v064 import normalize_usage_call

VERSION = "v156-occurrence-bound-input-provenance-r1"
PRIMARY_CATEGORIES = (
    "Base/Template",
    "Task",
    "Self-history",
    "Peer-message",
    "Artifact",
    "Tool-feedback",
    "Summary",
    "Retrieved",
)
TRANSFORMATIONS = frozenset(
    {
        "raw",
        "template",
        "condensed",
        "structured",
        "compressed",
        "diff",
        "index",
        "summary",
        "excerpt",
        "full",
    }
)
IDENTITY_FIELDS = (
    "request_id",
    "episode_id",
    "member_id",
    "decision_id",
    "attempt_id",
    "model_alias",
    "request_time",
)


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _text(value, field):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError(field + " must be an explicit bounded nonempty string")
    return value


def _integer(value, field):
    if type(value) is not int or value < 0:
        raise ValueError(field + " must be a nonnegative integer")
    return value


def _hash(value, field):
    if value is not None and (
        not isinstance(value, str) or not re.fullmatch("[a-f0-9]{64}", value)
    ):
        raise ValueError(field + " must be a SHA256 or explicitly unavailable")
    return value


@dataclass(frozen=True)
class SourceFragment:
    category: str
    source_id: str
    origin_event_id: str
    origin_member_id: str
    transformation: str = "raw"
    artifact_sha256: str | None = None
    version_sha256: str | None = None
    parent_source_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if self.category not in PRIMARY_CATEGORIES or self.transformation not in TRANSFORMATIONS:
            raise ValueError(
                "One of eight primary categories and a separate known transform are required"
            )
        for key in ("source_id", "origin_event_id", "origin_member_id"):
            _text(getattr(self, key), key)
        _hash(self.artifact_sha256, "artifact_sha256")
        _hash(self.version_sha256, "version_sha256")
        if self.category == "Artifact" and not (self.artifact_sha256 or self.version_sha256):
            raise ValueError("Artifact provenance needs an immutable artifact/version hash")
        if not isinstance(self.parent_source_ids, tuple):
            raise ValueError("Summary/source lineage must be an immutable tuple")
        for item in self.parent_source_ids:
            _text(item, "parent_source_id")


@dataclass(frozen=True)
class TextSegment:
    text: str
    source: SourceFragment | None

    def __post_init__(self):
        if not isinstance(self.text, str) or (
            self.source is not None and not isinstance(self.source, SourceFragment)
        ):
            raise ValueError("A text segment must carry explicit provenance or None")
        self.text.encode("utf-8")


@dataclass(frozen=True)
class AnnotatedText:
    segments: tuple[TextSegment, ...]

    def __post_init__(self):
        if not isinstance(self.segments, tuple) or any(
            not isinstance(x, TextSegment) for x in self.segments
        ):
            raise ValueError("AnnotatedText must retain its ordered explicit segment boundaries")


@dataclass(frozen=True)
class BuiltRequest:
    payload_bytes: bytes
    manifest: dict


def annotate_tree(value, source):
    """Explicit producer annotation, useful for known immutable tool-schema trees."""
    if not isinstance(source, SourceFragment):
        raise ValueError("Explicit source required; no guessed category")
    if isinstance(value, str):
        return AnnotatedText((TextSegment(value, source),))
    if isinstance(value, list):
        return [annotate_tree(v, source) for v in value]
    if isinstance(value, dict):
        return {k: annotate_tree(v, source) for k, v in value.items()}
    return value


def _plain(value):
    if isinstance(value, AnnotatedText):
        return "".join(x.text for x in value.segments)
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def build_request(payload, identity, *, template_source=None):
    """Serialize once with direct offsets; never identify origins by text equality.

    A template_source labels JSON syntax/keys/scalars only. Unannotated string
    values remain unattributed even when a template source was supplied.
    """
    if not isinstance(payload, dict):
        raise ValueError("A complete request object is required")
    required = set(IDENTITY_FIELDS)
    if not isinstance(identity, dict) or not required <= set(identity):
        raise ValueError(
            "Every physical request needs episode/member/decision/attempt/model/time identity"
        )
    for key in required:
        _text(identity[key], key)
    if template_source is not None and (
        not isinstance(template_source, SourceFragment)
        or template_source.category != "Base/Template"
    ):
        raise ValueError("Only explicitly declared template provenance may label JSON structure")
    chunks, spans, offset = [], [], 0

    def semantic(pointer):
        return (
            pointer == "/messages"
            or pointer.startswith("/messages/")
            or pointer == "/tools"
            or pointer.startswith("/tools/")
        )

    def emit(raw, pointer, kind, source=None, text=None, *, semantic_input=None):
        nonlocal offset
        if not raw:
            return
        if source is not None:
            if (
                source.category == "Self-history"
                and source.origin_member_id != identity["member_id"]
            ):
                raise ValueError("Another member history cannot be relabeled as self-history")
            if (
                source.category == "Peer-message"
                and source.origin_member_id == identity["member_id"]
            ):
                raise ValueError("Own content cannot be relabeled as peer exposure")
        end = offset + len(raw)
        spans.append(
            {
                "occurrence_id": identity["request_id"] + ":span:" + str(len(spans)),
                "request_id": identity["request_id"],
                "json_pointer": pointer,
                "kind": kind,
                "semantic_input": semantic(pointer) if semantic_input is None else semantic_input,
                "payload_start": offset,
                "payload_end": end,
                "payload_slice_sha256": digest(raw),
                "source": json.loads(canonical(asdict(source))) if source is not None else None,
                "decoded_text_sha256": digest(text.encode()) if text is not None else None,
                "decoded_characters": len(text) if text is not None else None,
            }
        )
        chunks.append(raw)
        offset = end

    def pointer_child(pointer, key):
        return pointer + "/" + str(key).replace("~", "~0").replace("/", "~1")

    def walk(value, pointer):
        if isinstance(value, AnnotatedText):
            emit(b'"', pointer, "json_syntax", template_source)
            for segment in value.segments:
                encoded = canonical(segment.text)[1:-1].encode()
                emit(encoded, pointer, "text_fragment", segment.source, segment.text)
            emit(b'"', pointer, "json_syntax", template_source)
        elif isinstance(value, str):
            emit(b'"', pointer, "json_syntax", template_source)
            emit(canonical(value)[1:-1].encode(), pointer, "unannotated_text", None, value)
            emit(b'"', pointer, "json_syntax", template_source)
        elif isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise ValueError("Canonical JSON object keys must be strings")
            emit(b"{", pointer, "json_syntax", template_source)
            for index, key in enumerate(sorted(value)):
                if index:
                    emit(b",", pointer, "json_syntax", template_source)
                child = pointer_child(pointer, key)
                emit(
                    canonical(key).encode(),
                    child,
                    "json_key",
                    template_source,
                    semantic_input=semantic(pointer),
                )
                emit(b":", child, "json_syntax", template_source, semantic_input=semantic(pointer))
                walk(value[key], child)
            emit(b"}", pointer, "json_syntax", template_source)
        elif isinstance(value, list):
            emit(b"[", pointer, "json_syntax", template_source)
            for index, item in enumerate(value):
                if index:
                    emit(b",", pointer, "json_syntax", template_source)
                walk(item, pointer_child(pointer, index))
            emit(b"]", pointer, "json_syntax", template_source)
        elif value is None or type(value) in {bool, int, float}:
            emit(canonical(value).encode(), pointer, "json_scalar", template_source)
        else:
            raise ValueError("Only JSON values and explicitly annotated strings may form a request")

    walk(payload, "")
    raw = b"".join(chunks)
    if raw != canonical(_plain(payload)).encode():
        raise ValueError("Provenance serialization changed the actual canonical request")
    known = sum(s["payload_end"] - s["payload_start"] for s in spans if s["source"] is not None)
    semantic_bytes = sum(
        s["payload_end"] - s["payload_start"] for s in spans if s["semantic_input"]
    )
    semantic_known = sum(
        s["payload_end"] - s["payload_start"]
        for s in spans
        if s["semantic_input"] and s["source"] is not None
    )
    manifest = {
        "version": VERSION,
        "identity": dict(identity),
        "payload_sha256": digest(raw),
        "payload_bytes": len(raw),
        "canonical_json": "UTF8/ensure_ascii_false/sorted_keys/compact/no_NaN",
        "spans": spans,
        "attributed_payload_bytes": known,
        "unattributed_payload_bytes": len(raw) - known,
        "payload_byte_source_coverage": known / len(raw),
        "semantic_input_roots": ["messages", "tools"],
        "semantic_payload_bytes": semantic_bytes,
        "semantic_attributed_payload_bytes": semantic_known,
        "semantic_payload_byte_source_coverage": semantic_known / semantic_bytes
        if semantic_bytes
        else None,
        "wire_transport_fields_are_prompt_input": False,
        "byte_coverage_is_provider_token_coverage": False,
    }
    built = BuiltRequest(raw, manifest)
    verify_request(built)
    return built


def verify_request(built):
    """Pure verification against the actual request bytes, not rendered text search."""
    raw, manifest = built.payload_bytes, built.manifest
    if digest(raw) != manifest["payload_sha256"] or len(raw) != manifest["payload_bytes"]:
        raise ValueError("Actual request bytes no longer match their captured provenance")
    if canonical(json.loads(raw)).encode() != raw:
        raise ValueError("Request is not the declared canonical serialization")
    if manifest.get("version") != VERSION:
        raise ValueError("Unexpected provenance contract version")
    for key in IDENTITY_FIELDS:
        _text(manifest["identity"].get(key), key)
    cursor, ids = 0, set()
    for span in manifest["spans"]:
        start, end = span["payload_start"], span["payload_end"]
        if (
            type(start) is not int
            or type(end) is not int
            or start != cursor
            or not start < end <= len(raw)
            or span["request_id"] != manifest["identity"]["request_id"]
            or span["occurrence_id"] in ids
            or digest(raw[start:end]) != span["payload_slice_sha256"]
        ):
            raise ValueError(
                "Spans must exactly partition the retained request without overlap or guessed matches"
            )
        if span["source"] is not None:
            value = dict(span["source"])
            value["parent_source_ids"] = tuple(value["parent_source_ids"])
            source = SourceFragment(**value)
            if (
                source.category == "Self-history"
                and source.origin_member_id != manifest["identity"]["member_id"]
            ):
                raise ValueError("Self-history attribution changed owner")
            if (
                source.category == "Peer-message"
                and source.origin_member_id == manifest["identity"]["member_id"]
            ):
                raise ValueError("Own content cannot become peer exposure")
        pointer = span["json_pointer"]
        if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
            raise ValueError("Explicit canonical JSON tree position required")
        scope = (
            pointer.rsplit("/", 1)[0]
            if span["kind"] == "json_key" or raw[start:end] == b":"
            else pointer
        )
        semantic = any(
            scope == "/" + k or scope.startswith("/" + k + "/") for k in ("messages", "tools")
        )
        if type(span["semantic_input"]) is not bool or span["semantic_input"] != semantic:
            raise ValueError("Wire configuration cannot be relabeled as semantic prompt input")
        if span["kind"] in {"text_fragment", "unannotated_text"}:
            text = json.loads('"' + raw[start:end].decode("utf-8") + '"')
            if (
                digest(text.encode()) != span["decoded_text_sha256"]
                or len(text) != span["decoded_characters"]
            ):
                raise ValueError("Decoded source fragment differs from actual JSON bytes")
        cursor = end
        ids.add(span["occurrence_id"])
    if cursor != len(raw):
        raise ValueError("Provenance did not preserve every actual request byte")
    known = sum(
        s["payload_end"] - s["payload_start"] for s in manifest["spans"] if s["source"] is not None
    )
    semantic_bytes = sum(
        s["payload_end"] - s["payload_start"] for s in manifest["spans"] if s["semantic_input"]
    )
    semantic_known = sum(
        s["payload_end"] - s["payload_start"]
        for s in manifest["spans"]
        if s["semantic_input"] and s["source"] is not None
    )
    expected = {
        "attributed_payload_bytes": known,
        "unattributed_payload_bytes": len(raw) - known,
        "payload_byte_source_coverage": known / len(raw),
        "semantic_payload_bytes": semantic_bytes,
        "semantic_attributed_payload_bytes": semantic_known,
        "semantic_payload_byte_source_coverage": semantic_known / semantic_bytes
        if semantic_bytes
        else None,
    }
    if any(manifest.get(k) != v for k, v in expected.items()):
        raise ValueError("Source-coverage metadata differs from actual byte spans")
    return True


def persist_request(directory, built):
    """Exclusive per-request capture. No overwrite or implicit retry/replay."""
    verify_request(built)
    root = Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    key = digest(built.manifest["identity"]["request_id"].encode())
    folder = root / key
    folder.mkdir(exist_ok=False, mode=0o700)
    payload_path, manifest_path = folder / "payload.json", folder / "provenance.json"
    for path, raw in (
        (payload_path, built.payload_bytes),
        (manifest_path, canonical(built.manifest).encode()),
    ):
        with path.open("xb") as stream:
            stream.write(raw)
        path.chmod(0o600)
    return {
        "request_id": built.manifest["identity"]["request_id"],
        "payload_sha256": built.manifest["payload_sha256"],
        "payload": {
            "path": str(payload_path),
            "sha256": digest(built.payload_bytes),
            "bytes": len(built.payload_bytes),
        },
        "manifest": {
            "path": str(manifest_path),
            "sha256": digest(canonical(built.manifest).encode()),
            "bytes": len(canonical(built.manifest).encode()),
        },
        "exclusive_capture": True,
    }


def load_persisted_request(capture):
    payload, manifest = capture["payload"], capture["manifest"]
    raw, data = Path(payload["path"]).read_bytes(), Path(manifest["path"]).read_bytes()
    for reference, content in ((payload, raw), (manifest, data)):
        if digest(content) != reference["sha256"] or len(content) != reference["bytes"]:
            raise ValueError("Persisted request original or provenance changed")
    built = BuiltRequest(raw, json.loads(data))
    verify_request(built)
    if capture["request_id"] != built.manifest["identity"]["request_id"]:
        raise ValueError("Captured request identity changed")
    return built


def _availability(value, field):
    if isinstance(value, str) and value:
        return {"status": "available", "value": value}
    return {"status": "unavailable", "value": None, "reason": field + "_not_returned"}


def normalized_usage(usage):
    if not isinstance(usage, dict):
        return None
    value = dict(usage)
    if "prompt_tokens" not in value and "input_tokens" in value:
        value["prompt_tokens"] = value["input_tokens"]
    if "completion_tokens" not in value and "output_tokens" in value:
        value["completion_tokens"] = value["output_tokens"]
    nested = value.get("prompt_tokens_details") or value.get("input_tokens_details") or {}
    if "prompt_cache_hit_tokens" not in value and "cached_tokens" in nested:
        value["prompt_cache_hit_tokens"] = nested["cached_tokens"]
    normalized = normalize_usage_call("validation-only", "agent", value)
    return {
        "input_tokens": normalized["prompt_tokens"],
        "output_tokens": normalized["completion_tokens"],
        "total_tokens": normalized["prompt_tokens"] + normalized["completion_tokens"],
        "cached_input_tokens": normalized["prompt_cache_hit_tokens"],
        "cache_miss_input_tokens": normalized["prompt_cache_miss_tokens"],
        "cache_is_subset_not_extra": True,
    }


def capture_response(built, body, *, outcome, http_status=None, response_time=None, error=None):
    verify_request(built)
    if outcome not in {"success", "http_error", "transport_unknown", "cancelled_before_dispatch"}:
        raise ValueError("Explicit response/exception state required")
    if body is not None and not isinstance(body, dict):
        raise ValueError("Response metadata requires a decoded object or None")
    body = body or {}
    usage = normalized_usage(body.get("usage"))
    if outcome == "success" and (http_status != 200 or usage is None):
        raise ValueError("A successful accounting record requires actual provider usage")
    choices = body.get("choices") if isinstance(body.get("choices"), list) else []
    # Current DeepSeek returns no input IDs. Only an explicitly returned sequence,
    # never a locally reconstructed sequence, can create this future-facing receipt.
    returned_ids = body.get("input_token_ids")
    ids_receipt = {"status": "unavailable", "reason": "input_token_ids_not_returned"}
    if returned_ids is not None:
        if not isinstance(returned_ids, list) or any(
            type(t) is not int or t < 0 for t in returned_ids
        ):
            raise ValueError("Provider input_token_ids is not an explicit token sequence")
        if usage is None or len(returned_ids) != usage["input_tokens"]:
            raise ValueError("Provider input-token IDs do not match authoritative prompt usage")
        ids_receipt = {
            "status": "available",
            "count": len(returned_ids),
            "sha256": digest(canonical(returned_ids).encode()),
            "source": "response_object.input_token_ids",
        }
    tool_calls = []
    for choice in choices:
        if not isinstance(choice, dict) or not isinstance(choice.get("message"), dict):
            continue
        for tool in choice["message"].get("tool_calls") or []:
            if isinstance(tool, dict):
                function = tool.get("function")
                tool_calls.append(
                    {
                        "id": tool.get("id"),
                        "name": function.get("name") if isinstance(function, dict) else None,
                    }
                )
    return {
        "version": VERSION,
        **built.manifest["identity"],
        "request_payload_sha256": built.manifest["payload_sha256"],
        "outcome": outcome,
        "http_status": http_status,
        "response_time": response_time,
        "response_id": _availability(body.get("id"), "response_id"),
        "provider_model": _availability(body.get("model"), "model"),
        "provider_fingerprint": _availability(body.get("system_fingerprint"), "fingerprint"),
        "provider_input_token_ids_receipt": ids_receipt,
        "response_canonical_object_sha256": digest(canonical(body).encode()) if body else None,
        "usage": usage,
        "usage_status": "reported" if usage is not None else "unavailable",
        "finish_reasons": [c.get("finish_reason") for c in choices if isinstance(c, dict)],
        "tool_calls": tool_calls,
        "error": error,
        "strict_weight_freeze_claim": False,
    }


def _assign_range(built, ranges, starts):
    if not ranges:
        return None, [], [], "no_payload_mapping_or_hidden_wrapper", True
    categories, sources, occurrences = set(), {}, set()
    semantic_seen, wire_seen, unannotated = False, False, False
    for item in ranges:
        if (
            not isinstance(item, (tuple, list))
            or len(item) != 2
            or any(type(x) is not int for x in item)
            or not 0 <= item[0] < item[1] <= len(built.payload_bytes)
        ):
            raise ValueError("Token mapping range is outside its exact canonical payload")
        start, end = item
        first = max(0, bisect_right(starts, start) - 1)
        for span in built.manifest["spans"][first:]:
            if span["payload_start"] >= end:
                break
            semantic_seen |= span["semantic_input"]
            wire_seen |= not span["semantic_input"]
            source = span["source"]
            if source is None:
                unannotated = True
            else:
                categories.add(source["category"])
                sources[canonical(source)] = source
            occurrences.add(span["occurrence_id"])
    if not semantic_seen:
        return None, [], list(occurrences), "transport_configuration_not_prompt_input", False
    if wire_seen:
        return None, [], list(occurrences), "token_crosses_wire_semantic_boundary", True
    if unannotated:
        return None, [], list(occurrences), "unannotated_payload_bytes", True
    if len(categories) != 1:
        return None, [], list(occurrences), "token_crosses_primary_source_boundary", True
    return next(iter(categories)), list(sources.values()), list(occurrences), None, True


def attribute_input_tokens(built, response, token_occurrences, evidence):
    """Map each supplied token occurrence once; never prorate API usage.

    Local rendered/canonical token maps may estimate source exposure but do not
    prove provider exactness. Exactness needs request-bound direct provider IDs
    or independently verified official rendering/tokenizer/wrapper compatibility.
    A matching local count alone is insufficient for either route.
    """
    verify_request(built)
    if (
        response["request_id"] != built.manifest["identity"]["request_id"]
        or response["request_payload_sha256"] != built.manifest["payload_sha256"]
    ):
        raise ValueError("Provider usage and attribution belong to different requests")
    if evidence.get("payload_sha256") != built.manifest["payload_sha256"]:
        raise ValueError("Token mapping must bind the actual canonical request bytes")
    if evidence.get("domain") not in {
        "canonical_payload_local",
        "rendered_chat_local",
        "provider_prompt_exact",
        "synthetic_control",
    }:
        raise ValueError("Explicit tokenization domain required")
    primary = Counter({key: 0 for key in PRIMARY_CATEGORIES})
    unknown = Counter()
    attributed = []
    token_ids = []
    excluded_wire = 0
    starts = [s["payload_start"] for s in built.manifest["spans"]]
    for index, token in enumerate(token_occurrences):
        if token.get("index") != index:
            raise ValueError("Each token occurrence needs one unique contiguous position")
        token_ids.append(_integer(token.get("token_id"), "token_id"))
        category, sources, source_occurrences, reason, semantic = _assign_range(
            built, token.get("payload_ranges"), starts
        )
        if not semantic:
            excluded_wire += 1
        elif category is None:
            unknown[reason] += 1
        else:
            primary[category] += 1
        attributed.append(
            {
                "index": index,
                "primary_category": category,
                "source_ids": [s["source_id"] for s in sources],
                "source_occurrence_ids": source_occurrences,
                "semantic_input": semantic,
                "payload_ranges": token.get("payload_ranges") or [],
                "unattributed_reason": reason,
            }
        )
    observed_ids_hash = digest(canonical(token_ids).encode())
    if evidence.get("token_ids_sha256") != observed_ids_hash:
        raise ValueError("Observed token sequence differs from its tokenizer evidence")
    local_count = len(attributed) - excluded_wire
    known = sum(primary.values())
    unattributed = local_count - known
    usage = response.get("usage")
    prompt = usage["input_tokens"] if usage is not None else None
    proof = evidence.get("compatibility_evidence") or {}
    binding = {
        "request_id": response["request_id"],
        "response_id": response.get("response_id", {}).get("value"),
        "payload_sha256": evidence["payload_sha256"],
        "token_ids_sha256": observed_ids_hash,
        "response_object_sha256": response.get("response_canonical_object_sha256"),
        "provider_model": response.get("provider_model", {}).get("value"),
    }
    bound = isinstance(proof, dict) and all(
        v is not None and proof.get(k) == v for k, v in binding.items()
    )
    direct_ids = response.get("provider_input_token_ids_receipt", {})
    direct_verified = (
        bound
        and proof.get("method") == "provider_returned_input_ids"
        and direct_ids.get("status") == "available"
        and direct_ids.get("sha256") == observed_ids_hash
        and direct_ids.get("count") == prompt
    )
    recipe_verified = (
        bound
        and proof.get("method") == "official_recipe_compatibility"
        and proof.get("validation_status") == "exact_verified"
        and proof.get("provider_wrapper_included") is True
        and all(
            isinstance(proof.get(k), str) and re.fullmatch("[a-f0-9]{64}", proof[k])
            for k in ("renderer_sha256", "tokenizer_sha256", "validation_record_sha256")
        )
        and isinstance(proof.get("official_recipe_reference"), str)
        and bool(proof["official_recipe_reference"])
    )
    exact = (
        evidence.get("domain") == "provider_prompt_exact"
        and evidence.get("tokenizer_and_rendering_verified") is True
        and evidence.get("hidden_wrapper_accounted") is True
        and (direct_verified or recipe_verified)
        and prompt is not None
        and local_count == prompt
        and excluded_wire == 0
        and not unknown.get("token_crosses_wire_semantic_boundary")
    )
    return {
        "version": VERSION,
        "request_id": response["request_id"],
        "payload_sha256": evidence["payload_sha256"],
        "precision": "provider_exact" if exact else "local_estimate_not_provider_exact",
        "evidence": dict(evidence),
        "local_token_count": local_count,
        "all_supplied_token_positions": len(attributed),
        "excluded_transport_configuration_tokens": excluded_wire,
        "local_token_denominator": "messages_tools_semantic_input_only",
        "local_by_primary_category": dict(primary),
        "local_unattributed_tokens": unattributed,
        "local_unattributed_reasons": dict(unknown),
        "payload_local_estimated_token_coverage": known / local_count if local_count else None,
        "payload_byte_source_coverage": built.manifest["payload_byte_source_coverage"],
        "provider_input_tokens": prompt,
        "provider_exact_mapping_available": exact,
        "provider_exact_evidence_method": proof.get("method") if exact else None,
        "provider_exact_source_coverage": known / prompt if exact and prompt else None,
        "provider_exact_unattributed_tokens": unattributed if exact else None,
        "provider_exact_by_primary_category": dict(primary) if exact else None,
        "provider_unmatched_token_difference": prompt - local_count if prompt is not None else None,
        "attributed_occurrences": attributed,
        "no_proportional_usage_allocation": True,
    }


def estimate_fragment_tokens(built, counter, *, tokenizer_id):
    """Standalone fragment encoding: explicit nonadditive proxy, never exact billing."""
    verify_request(built)
    _text(tokenizer_id, "tokenizer_id")
    counts = Counter({key: 0 for key in PRIMARY_CATEGORIES})
    unknown = 0
    pieces = []
    for span in built.manifest["spans"]:
        if not span["semantic_input"] or span["kind"] == "json_syntax":
            continue
        raw = built.payload_bytes[span["payload_start"] : span["payload_end"]]
        if span["kind"] in {"text_fragment", "unannotated_text"}:
            text = json.loads('"' + raw.decode("utf-8") + '"')
        elif span["kind"] == "json_key":
            text = json.loads(raw)
        else:
            text = raw.decode("utf-8")
        number = _integer(counter(text), "local fragment count")
        category = span["source"]["category"] if span["source"] else None
        if category is None:
            unknown += number
        else:
            counts[category] += number
        pieces.append(
            {
                "occurrence_id": span["occurrence_id"],
                "estimated_tokens": number,
                "primary_category": category,
            }
        )
    semantic_payload = {
        k: v for k, v in json.loads(built.payload_bytes).items() if k in {"messages", "tools"}
    }
    whole = _integer(counter(canonical(semantic_payload)), "whole local semantic JSON count")
    total = sum(counts.values()) + unknown
    return {
        "request_id": built.manifest["identity"]["request_id"],
        "precision": "fragment_local_estimate",
        "payload_sha256": built.manifest["payload_sha256"],
        "tokenizer_id": tokenizer_id,
        "estimated_by_primary_category": dict(counts),
        "unattributed_fragment_tokens_estimate": unknown,
        "fragment_count_sum": total,
        "whole_semantic_json_local_count": whole,
        "local_token_denominator": "messages_tools_text_keys_scalars_excluding_wire_parameters_and_JSON_punctuation",
        "wire_configuration_and_syntax_excluded": True,
        "fragment_boundaries_may_change_tokenization": True,
        "payload_local_estimated_token_coverage": sum(counts.values()) / total if total else None,
        "provider_exact_mapping_available": False,
        "provider_exact_source_coverage": None,
        "provider_exact_unattributed_tokens": None,
        "provider_exact_by_primary_category": None,
        "no_proportional_usage_allocation": True,
        "pieces": pieces,
    }


def _unique(records, identity_key):
    found, duplicates, conflicts = {}, [], []
    for row in records:
        key = _text(row.get(identity_key), identity_key)
        if key in found:
            (duplicates if canonical(found[key]) == canonical(row) else conflicts).append(key)
        else:
            found[key] = row
    return found, duplicates, conflicts


def reconcile_ledgers(responses, ledger_entries):
    """Pure authoritative usage reconciliation; analysis subtotals are never re-added."""
    observed, duplicates, conflicts = _unique(responses, "request_id")
    ledger, ledger_duplicates, ledger_conflicts = _unique(ledger_entries, "request_id")
    issues = [
        {"kind": "conflicting_duplicate_request", "request_id": x}
        for x in conflicts + ledger_conflicts
    ]
    if set(observed) != set(ledger):
        issues.append(
            {
                "kind": "request_identity_set_mismatch",
                "response_only": sorted(set(observed) - set(ledger)),
                "ledger_only": sorted(set(ledger) - set(observed)),
            }
        )
    totals = Counter(input_tokens=0, output_tokens=0, cached_input_tokens_known=0)
    unresolved = []
    cache_unknown = []
    for request, row in observed.items():
        usage = row.get("usage")
        if usage is None:
            unresolved.append(request)
        else:
            totals["input_tokens"] += usage["input_tokens"]
            totals["output_tokens"] += usage["output_tokens"]
            if usage["cached_input_tokens"] is None:
                cache_unknown.append(request)
            else:
                totals["cached_input_tokens_known"] += usage["cached_input_tokens"]
            if not 0 <= (usage["cached_input_tokens"] or 0) <= usage["input_tokens"]:
                issues.append({"kind": "cache_not_input_subset", "request_id": request})
        if request in ledger:
            reported = ledger[request].get("usage")
            normalized = normalized_usage(reported) if reported is not None else None
            if usage != normalized:
                issues.append({"kind": "usage_disagrees", "request_id": request})
            if usage is not None and ledger[request].get("status") != "settled":
                issues.append({"kind": "known_usage_not_settled", "request_id": request})
            if usage is None and ledger[request].get("status") == "settled":
                issues.append({"kind": "unknown_usage_called_settled", "request_id": request})
    return {
        "passed": not issues,
        "issues": issues,
        "physical_request_count": len(observed),
        "request_ids": sorted(observed),
        "duplicate_observations_not_recounted": duplicates,
        "duplicate_ledger_entries_not_recounted": ledger_duplicates,
        "known_actual_input_tokens": totals["input_tokens"],
        "known_actual_output_tokens": totals["output_tokens"],
        "known_actual_total_tokens": totals["input_tokens"] + totals["output_tokens"],
        "cached_input_tokens_known": totals["cached_input_tokens_known"],
        "cached_input_is_subset": True,
        "uncertain_request_ids": unresolved,
        "usage_complete": not unresolved,
        "cache_receipt_unknown_request_ids": cache_unknown,
        "analysis_subledgers_added_to_team_total": False,
    }


def _p95(values):
    return sorted(values)[max(0, math.ceil(0.95 * len(values)) - 1)] if values else None


def evaluate_g0(records, attributions, reconciliation, *, other_gates=None):
    """Pure gate assessment of verified captures; no real-provider claims from CPU fixtures.

    records contain request:BuiltRequest,response:capture_response,capture:
    persist_request receipt. Disk verification is load_persisted_request's job;
    this function only evaluates its provided verified snapshot.
    """
    originals_ok = True
    request_ids = set()
    request_signatures = {}
    attempt_ids = {}
    identity_conflicts = []
    duplicate_observations = []
    responses = []
    identity_ok = True
    for item in records:
        built, response, capture = item["request"], item["response"], item.get("capture")
        try:
            verify_request(built)
        except ValueError:
            originals_ok = False
        request_id = built.manifest["identity"]["request_id"]
        attempt = built.manifest["identity"]["attempt_id"]
        signature = digest(
            canonical(
                {"manifest": built.manifest, "response": response, "capture": capture}
            ).encode()
        )
        if request_id in request_signatures:
            if request_signatures[request_id] == signature:
                duplicate_observations.append(request_id)
                continue
            identity_conflicts.append(request_id)
        if attempt in attempt_ids and attempt_ids[attempt] != request_id:
            identity_conflicts.append(request_id)
        request_signatures[request_id] = signature
        request_ids.add(request_id)
        attempt_ids[attempt] = request_id
        responses.append(response)
        if (
            not capture
            or capture.get("request_id") != request_id
            or capture.get("payload", {}).get("sha256") != built.manifest["payload_sha256"]
            or capture.get("manifest", {}).get("sha256")
            != digest(canonical(built.manifest).encode())
            or response.get("request_id") != request_id
            or response.get("request_payload_sha256") != built.manifest["payload_sha256"]
            or any(response.get(k) != built.manifest["identity"][k] for k in IDENTITY_FIELDS)
            or (response.get("usage") is None and response.get("outcome") == "success")
            or (
                response.get("outcome") == "success"
                and (
                    response.get("response_id", {}).get("status") != "available"
                    or not response.get("response_id", {}).get("value")
                )
            )
        ):
            originals_ok = False
        for field in ("provider_model", "provider_fingerprint"):
            value = response.get(field, {})
            if (
                value.get("status") not in {"available", "unavailable"}
                or (value.get("status") == "unavailable" and not value.get("reason"))
                or (value.get("status") == "available" and not value.get("value"))
            ):
                identity_ok = False
    attribution_map, duplicate_attributions, conflicting_attributions = _unique(
        attributions, "request_id"
    )
    all_attributed = not conflicting_attributions and set(attribution_map) == request_ids
    local_counts = local_unknown = 0
    local_rates = []
    exact_counts = exact_unknown = 0
    exact_rates = []
    exact_available = all_attributed
    for item in attribution_map.values():
        matched_response = next(
            (r for r in responses if r["request_id"] == item["request_id"]), None
        )
        if (
            matched_response is None
            or item.get("payload_sha256") != matched_response["request_payload_sha256"]
        ):
            all_attributed = exact_available = False
        count = item.get("local_token_count", item.get("fragment_count_sum"))
        unknown = item.get(
            "local_unattributed_tokens", item.get("unattributed_fragment_tokens_estimate")
        )
        if count is not None and unknown is not None:
            local_counts += count
            local_unknown += unknown
            local_rates.append(unknown / count if count else 0)
        else:
            all_attributed = False
        if (
            item.get("provider_exact_mapping_available") is True
            and item.get("provider_input_tokens") is not None
        ):
            exact_counts += item["provider_input_tokens"]
            exact_unknown += item["provider_exact_unattributed_tokens"]
            exact_rates.append(
                item["provider_exact_unattributed_tokens"] / item["provider_input_tokens"]
                if item["provider_input_tokens"]
                else 0
            )
        else:
            exact_available = False
    local_rate = local_unknown / local_counts if local_counts else None
    exact_rate = exact_unknown / exact_counts if exact_counts else None
    source_gate = (
        all_attributed
        and local_rate is not None
        and local_rate <= 0.02
        and _p95(local_rates) <= 0.05
    )
    exact_gate = (
        exact_available
        and exact_rate is not None
        and exact_rate <= 0.02
        and _p95(exact_rates) <= 0.05
    )
    gates = {
        "G0-1": originals_ok and bool(records),
        "G0-2-payload-local-estimate": source_gate,
        "G0-2-provider-exact": exact_gate,
        "G0-3": reconciliation.get("passed") is True
        and set(reconciliation.get("request_ids", [])) == request_ids,
        "G0-7": identity_ok and bool(records),
        "G0-8": not identity_conflicts and bool(records),
    }
    for key in ("G0-4", "G0-5", "G0-6"):
        gates[key] = (other_gates or {}).get(key) is True
    return {
        "version": VERSION,
        "gates": gates,
        "p1_ready": all(gates.values()),
        "payload_local_estimated_unattributed_fraction": local_rate,
        "payload_local_estimated_request_p95": _p95(local_rates),
        "provider_exact_attribution_available": exact_available,
        "provider_exact_unattributed_fraction": exact_rate if exact_available else None,
        "provider_exact_request_p95": _p95(exact_rates) if exact_available else None,
        "request_or_attempt_identity_conflicts": identity_conflicts,
        "duplicate_observations_not_recounted": duplicate_observations,
        "duplicate_attributions_not_recounted": duplicate_attributions,
        "conflicting_attributions": conflicting_attributions,
        "provider_fields_unavailable_requests": [
            r["request_id"]
            for r in responses
            if any(
                r.get(f, {}).get("status") == "unavailable"
                for f in ("provider_model", "provider_fingerprint")
            )
        ],
        "strict_weight_freeze_claim": False,
        "byte_coverage_never_substituted_for_provider_token_coverage": True,
        "thresholds": {"aggregate_unattributed_max": 0.02, "request_p95_unattributed_max": 0.05},
    }
