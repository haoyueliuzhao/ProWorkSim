"""Stream actual physical captures against a read-only cash-ledger snapshot.

No model/scorer/network call. Large provenance manifests are loaded one at a
time; provider totals and source estimates remain separate. This audit never
reads benchmark scores and cannot modify the frozen communication policy.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from proworksim import software_input_provenance_v156 as p
from proworksim.software_collaboration_observation_v141 import load_official_content_counter

VERSION = "v157-streaming-physical-measurement-audit-r1"
ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_bytes())


def reference(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def checked_json(ref):
    raw = Path(ref["path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref["sha256"] or len(raw) != ref["bytes"]:
        raise ValueError("Immutable captured artifact changed")
    return json.loads(raw)


def ledger_snapshot(path, slots=None):
    with sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        rows = [dict(r) for r in db.execute("SELECT * FROM requests ORDER BY reserved_utc,request_id")]
    return [r for r in rows if slots is None or r["slot_id"] in slots]


def audit(ledger_path, capture_roots, counter, tokenizer_id, *, slots=None, mechanism_gates=None):
    ledger = ledger_snapshot(ledger_path, slots)
    by_id = {row["request_id"]: row for row in ledger}
    rows, response_records, issues, seen, category = [], [], [], set(), Counter()
    purpose_usage, condition_usage = defaultdict(Counter), defaultdict(Counter)
    source_by_purpose = defaultdict(Counter)
    total_fragments = unknown_fragments = 0
    request_unknown_fractions = []
    observer_errors = []
    for root in capture_roots:
        for path in sorted(Path(root).rglob("physical-receipt.json")):
            receipt = read(path)
            request_id = receipt.get("request_id")
            # The caller supplies the wave slot set; unrelated captures are not
            # silently pulled into that wave's denominator.
            capture = receipt.get("request_capture")
            if slots is not None and capture:
                identity = checked_json(capture["manifest"])["identity"]
                if identity["episode_id"] not in slots:
                    continue
            if request_id in seen:
                issues.append({"kind": "duplicate_physical_capture", "request_id": request_id})
                continue
            seen.add(request_id)
            try:
                built = p.load_persisted_request(capture)
                response = checked_json(receipt["response_metadata_ref"])
                if receipt.get("response_metadata") != response:
                    raise ValueError("Receipt response differs from immutable response")
                identity = built.manifest["identity"]
                if identity["request_id"] != request_id:
                    raise ValueError("Physical receipt identity differs")
                if response["request_payload_sha256"] != built.manifest["payload_sha256"]:
                    raise ValueError("Response is bound to another request")
                if response.get("outcome") == "success":
                    body = checked_json(receipt["response_original_ref"])
                    if (body.get("id") != response["response_id"].get("value")
                            or p.normalized_usage(body.get("usage")) != response.get("usage")):
                        raise ValueError("Original response/usage identity differs")
                estimate = p.estimate_fragment_tokens(built, counter, tokenizer_id=tokenizer_id)
                response_records.append(response)
                local = estimate["fragment_count_sum"]
                unknown = estimate["unattributed_fragment_tokens_estimate"]
                total_fragments += local
                unknown_fragments += unknown
                request_unknown_fractions.append(unknown/local if local else 0)
                category.update(estimate["estimated_by_primary_category"])
                purpose = identity.get("usage_id", identity.get("purpose", "unidentified"))
                source_by_purpose[purpose].update(estimate["estimated_by_primary_category"])
                row = by_id.get(request_id)
                if row is None:
                    raise ValueError("Capture is absent from the independent SQLite snapshot")
                if (identity["episode_id"] != row["slot_id"]
                        or identity["member_id"] != row["member_id"]
                        or built.manifest["payload_sha256"] != row["request_sha256"]
                        or purpose != row["usage_id"]
                        or identity.get("logical_id") != row["logical_id"]
                        or identity.get("physical_attempt_index") != row["attempt_index"]
                        or identity.get("condition") != row["condition"]):
                    raise ValueError("Physical identity/purpose/payload does not match the cash ledger")
                if any(response.get(key) != identity[key] for key in p.IDENTITY_FIELDS):
                    raise ValueError("Response identity differs from the actual captured request")
                if response.get("usage"):
                    for key in ("input_tokens", "output_tokens", "total_tokens"):
                        purpose_usage[purpose][key] += response["usage"][key]
                        condition_usage[row["condition"]][key] += response["usage"][key]
                observer_errors.extend(receipt.get("observer_errors", []))
                rows.append({"request_id": request_id, "episode_id": identity["episode_id"],
                             "condition": row["condition"], "purpose": purpose,
                             "capture": reference(path), "known_actual_usage": response.get("usage"),
                             "estimated_by_primary_category": estimate["estimated_by_primary_category"],
                             "local_fragment_tokens": local, "local_unknown_tokens": unknown,
                             "provider_model": response.get("provider_model"),
                             "provider_fingerprint": response.get("provider_fingerprint")})
            except (KeyError, TypeError, ValueError, OSError) as error:
                issues.append({"kind": "capture_integrity", "request_id": request_id,
                               "exception": type(error).__name__, "reason": str(error)})
    entries = [{"request_id": r["request_id"], "status": r["status"],
                "usage": json.loads(r["usage_json"]) if r.get("usage_json") else None}
               for r in ledger]
    reconciled = p.reconcile_ledgers(response_records, entries)
    unknown_rate = unknown_fragments/total_fragments if total_fragments else None
    p95 = (sorted(request_unknown_fractions)[max(0, math.ceil(.95*len(request_unknown_fractions))-1)]
           if request_unknown_fractions else None)
    complete = len(rows) == len(ledger) and bool(rows) and not issues and not observer_errors
    gates = {"G0-1": complete,
             "G0-2-payload-local-estimate": complete and unknown_rate <= .02 and p95 <= .05,
             "G0-2-provider-exact": False,
             "G0-3": reconciled["passed"],
             "G0-7": complete and all(
                 isinstance(r.get(field), dict) and r[field].get("status") in {"available", "unavailable"}
                 for r in response_records for field in ("provider_model", "provider_fingerprint")),
             "G0-8": complete}
    for name in ("G0-4", "G0-5", "G0-6"):
        gates[name] = (mechanism_gates or {}).get(name) is True
    return {"version": VERSION, "scores_consulted": False, "model_calls": 0,
            "ledger_path": str(Path(ledger_path).resolve()), "ledger_rows": len(ledger),
            "captured_requests": len(rows), "issues": issues, "observer_errors": observer_errors,
            "gates": gates, "payload_local_estimated_unattributed_fraction": unknown_rate,
            "payload_local_estimated_request_p95": p95,
            "provider_exact_attribution_available": False,
            "provider_exact_source_claim": False, "strict_weight_freeze_claim": False,
            "local_source_token_estimates": dict(category),
            "local_source_token_estimates_by_purpose": dict(source_by_purpose),
            "compressor_source_inputs_are_not_receiver_agent_peer_exposure": True,
            "source_estimates_are_not_provider_decomposition": True,
            "API_usage_by_purpose": dict(purpose_usage), "API_usage_by_condition": dict(condition_usage),
            "reconciliation": reconciled, "requests": rows}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--captures", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--slots", type=Path, help="JSON list of exact wave episode IDs")
    parser.add_argument("--mechanism-gates", type=Path,
                        help="Current independent evidence for G0-4/5/6; absent remains false")
    args = parser.parse_args()
    manifest = ROOT/"runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    counter, meta = load_official_content_counter(manifest, manifest_sha256=reference(manifest)["sha256"])
    slots = None if args.slots is None else set(read(args.slots))
    result = audit(args.ledger, args.captures, lru_cache(maxsize=16384)(counter), meta["tokenizer_id"],
                   slots=slots, mechanism_gates=read(args.mechanism_gates) if args.mechanism_gates else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as out:
        json.dump(result, out, ensure_ascii=False, indent=2)
        out.write("\n")
    print(json.dumps({"requests": result["captured_requests"], "gates": result["gates"]}))


if __name__ == "__main__":
    main()
