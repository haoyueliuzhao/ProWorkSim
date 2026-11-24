"""Compare original and projected physical wires offline; join the supplier ledger by physical identity."""

import hashlib
import json
import os
import sqlite3
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

from proworksim.software_context_builder_v230 import (
    build,
    source_parts,
    recover_observations,
    object_text,
    identity,
)
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.software_benchmark_deepseek_contract_v105 import normalize_usage
from proworksim.software_collaboration_observation_v141 import load_official_content_counter
from proworksim.storage import read_json, json_bytes, digest, atomic_write

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "runs/software-benchmark-v230/replay-r1"
REPORT = ROOT / "artifacts/software-benchmark-v230/engineering-r1"
TOKENIZER = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
DB = {
    "v228": ROOT / "runs/software-benchmark-v211/budget700-r1/ledger.sqlite",
    "v229": ROOT / "runs/software-benchmark-v229/dev1-r1/ledger.sqlite",
}
EXT_PREFIX = ROOT / "runs/software-benchmark-v227/development-r1/task-00/PREFIX/api"


def initialize():
    global counter, count
    os.environ["RAYON_NUM_THREADS"] = "1"
    h = digest(TOKENIZER.read_bytes())
    counter = OfficialDeepSeekCounter(TOKENIZER, manifest_sha256=h)
    plain, _ = load_official_content_counter(TOKENIZER, manifest_sha256=h)
    count = lru_cache(maxsize=4096)(plain)


def encode(wire):
    local = {**wire, "model": "DeepSeek-V4.1-Flash"}
    obj = counter.recipe.ChatCompletionRequest(local).convert(counter.recipe.ConversionOptions())
    return counter.encoding.encode(obj.conversation)


def common(a, b):
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def selected_case(path):
    s = str(path.relative_to(ROOT))
    if (
        path == EXT_PREFIX
        or "software-benchmark-v228/supplement-r1/astropy-evidence-r2-launch2/" in s
    ):
        return "Astropy-14182"
    if "software-benchmark-v229/dev1-r1/task-00/" in s:
        return "Sphinx-10449"
    for index, name in [(20, "Sphinx-9591"), (21, "SymPy-19954")]:
        if f"/task-{index}/" in s and "/dev1-balance90-" in s and "software-benchmark-v229/" in s:
            return name
    return None


def validate_projection(wire, new, manifest, reports):
    if wire.get("tools") != new.get("tools") or wire["messages"][0] != new["messages"][0]:
        raise ValueError("Immutable base changed")
    orig = recover_observations(wire)
    if orig != recover_observations(new):
        raise ValueError("Snapshot/ownership/visibility mismatch")
    if len(wire["messages"]) != len(new["messages"]):
        raise ValueError("Lost SDK history position")
    protected = Counter()
    for i, m in enumerate(wire["messages"]):
        shown = new["messages"][i]
        content = m.get("content") or ""
        source = object_text(content) or {}
        if m["role"] == "user" and content.startswith("Work observation: "):
            protected["anomaly_notices"] += 1
            if shown["content"] != content:
                raise ValueError("Original anomaly evidence changed")
        if i == 1 and manifest["role"] == "osa":
            protected["osa_evidence_items"] += len(source["evidence"])
            if object_text(shown["content"]) != source:
                raise ValueError("Original authorized OSA evidence changed")
        if m["role"] == "tool" and source.get("ok") is False:
            protected["tool_errors"] += 1
            if object_text(shown["content"]) != source:
                raise ValueError("Tool rejection lost")
        if m["role"] == "tool" and isinstance(source.get("result"), dict):
            body = source["result"]
            if body.get("report_id") and body.get("source_reference"):
                protected["versioned_reports"] += 1
                result = object_text(shown["content"])["result"]
                if any(
                    result.get(k) != body.get(k)
                    for k in (
                        "report_id",
                        "source_reference",
                        "body_sha256",
                        "passed",
                        "diagnostic_summary",
                    )
                ):
                    raise ValueError("Version-bound result changed")
        if {k: v for k, v in m.items() if k != "content"} != {
            k: v for k, v in shown.items() if k != "content"
        }:
            raise ValueError("Lost tool association")
    for i, j in manifest["duplicate_reads"]:
        a = object_text(wire["messages"][i]["content"])
        b = object_text(new["messages"][j]["content"])
        if a["result"] != b["result"] or j >= i:
            raise ValueError("Read alias cannot be expanded")
    for item in manifest["items"]:
        if item["source_hash"] != identity(wire["messages"][item["index"]]) or item[
            "shown_hash"
        ] != identity(new["messages"][item["index"]]):
            raise ValueError("Unreconstructable history item")
    for item in manifest["worker_graphs"]:
        i = item["index"]
        g = object_text(wire["messages"][i]["content"].rpartition(" Active graph: ")[2])
        shown = object_text(new["messages"][i]["content"].rpartition(" Active graph: ")[2])
        if not all(
            shown["work"].get(t) == work
            for t, work in g["work"].items()
            if manifest["actor"] in (work["owner"], work["reviewer"])
        ):
            raise ValueError("Member responsibility omitted")
    for page in manifest["tool_pages"]:
        i = page["index"]
        a = object_text(wire["messages"][i]["content"])["result"]
        b = object_text(new["messages"][i]["content"])["result"]
        if {k: v for k, v in a.items() if k != "page"} != {
            k: v for k, v in b.items() if k != "page"
        }:
            raise ValueError("Test metadata lost")
        if (
            a["report_id"] != page["retrieve"]["report_id"]
            or a["source_reference"] != page["source_reference"]
        ):
            raise ValueError("Invalid retrieval")
        saved = reports()[a["report_id"]]
        cursor = page["retrieve"].get("cursor")
        resolved = (
            next((entry for entry in saved["pages"] if entry["cursor"] == cursor), None)
            if cursor
            else saved["pages"][0]
        )
        if (
            saved["actor_id"] != manifest["actor"]
            or saved["body_sha256"] != a["body_sha256"]
            or saved["visible_result"]["source_reference"] != a["source_reference"]
            or resolved is None
            or resolved["text"] != a["page"]["text"]
        ):
            raise ValueError("Original test page cannot be retrieved under member identity")
    return len(orig), protected


def analyze(folder):
    case = selected_case(folder)
    previous = {}
    rows = []
    versions = Counter()
    elapsed_start = __import__("time").monotonic()
    scope = str(folder.relative_to(ROOT))
    paths = list(folder.glob("*/request.json"))

    def sequence(path):
        # Sorting is only for consecutive same-actor prefix length, never for causal joins.
        return read_json(path)["time"]

    @lru_cache(maxsize=1)
    def reports():
        state = folder.parent / "prepared/world/control/state.json"
        return read_json(state)["projects"]["SOFTWARE27"]["software"]["test_reports"]

    for path in sorted(paths, key=sequence):
        request = read_json(path)
        payload = request["payload"]
        wire = payload["wire"]
        response = read_json(path.parent / "response.json")
        usage = normalize_usage(response)
        if (
            usage != read_json(path.parent / "usage.json")
            or digest(json_bytes(wire)) != request["count"]["request_sha256"]
        ):
            raise ValueError(scope)
        role = (
            "osa"
            if folder.parent.name in ("draft", "control-1", "control-2")
            else "condenser"
            if payload["usage_id"] == "condenser"
            else "worker"
        )
        buckets = Counter()
        for cat, s in source_parts(wire, role):
            buckets[cat] += count(s)
        local = request["count"]["local_encoded_prompt_tokens"]
        buckets["local_template_and_segmentation_residual"] = local - sum(buckets.values())
        message = response["choices"][0]["message"]
        out_parts = {
            "text": count(message.get("content") or ""),
            "osa_plan" if role == "osa" else "tool_arguments": sum(
                count(c["function"]["arguments"]) for c in message.get("tool_calls") or []
            ),
        }
        rec = {
            "physical_id": request["physical_id"],
            "provider_id": response["id"],
            "actor": payload["member_id"],
            "role": role,
            "request_id": payload["request_id"] if "request_id" in payload else None,
            "usage": usage,
            "local_input": local,
            "source_estimates": dict(buckets),
            "output_estimates": out_parts,
            "time": request["time"],
            "evidence": str(path.relative_to(ROOT)),
            "request_file_sha256": digest(path.read_bytes()),
            "response_file_sha256": digest((path.parent / "response.json").read_bytes()),
        }
        if case:
            transformed, m = build(wire, actor=payload["member_id"], role=role, scope=scope)
            m.update(
                episode_id=case,
                request_id=request["physical_id"],
                reserved_output_tokens=wire.get("max_tokens"),
            )
            nobs, protected = validate_projection(wire, transformed, m, reports)
            base = encode(wire)
            t1 = encode(transformed)
            if len(base) != local:
                raise ValueError("Pinned tokenizer disagrees with frozen local measurement")
            m.update(estimated_input_tokens=len(t1))
            key = (payload["member_id"], role)
            old = previous.get(key)
            rec["comparison"] = {
                "t0": len(base),
                "t1": len(t1),
                "validated_snapshots": nobs,
                **protected,
                "delta_snapshots": len(m["observation_deltas"]),
                "indexed_test_pages": len(m["tool_pages"]),
                "duplicate_reads": len(m["duplicate_reads"]),
                "message_refs": len(m["message_refs"]),
                "prefix0": common(old[0], base) if old else None,
                "prefix1": common(old[1], t1) if old else None,
            }
            previous[key] = (base, t1)
            dest = ARCHIVE / "manifests" / path.parent.name / "context.json"
            atomic_write(dest, json_bytes(m))
            rec["context_manifest"] = str(dest.relative_to(ROOT))
        rows.append(rec)
        versions[request["count"]["tokenizer_sha256"]] += 1
    out = ARCHIVE / "accounting" / (hashlib.sha256(scope.encode()).hexdigest() + ".json")
    atomic_write(
        out, json_bytes({"scope": scope, "case": case, "rows": rows, "tokenizers": dict(versions)})
    )
    return scope, str(out), len(rows), round(__import__("time").monotonic() - elapsed_start, 2)


def run():
    folders = {EXT_PREFIX}
    for v in DB:
        p = ROOT / "runs" / ("software-benchmark-" + v)
        for pattern in ("*/*/*/api", "*/*/*/*/api"):
            folders.update(f for f in p.glob(pattern) if f.is_dir())
    ledger = {}
    for ver, db in DB.items():
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
            for rid, slot, tokens, cost, provider, body, status in c.execute(
                "select id,slot,tokens,cost,provider_id,body,status from requests where slot glob ?",
                (ver + ":*",),
            ):
                if status != "settled":
                    raise ValueError("Unresolved physical request")
                ledger[rid] = (slot, tokens, cost, provider, json.loads(body))
    results = []
    with ProcessPoolExecutor(max_workers=4, initializer=initialize) as pool:
        for record in pool.map(analyze, sorted(folders)):
            results.append(record)
            print(record[0], record[2:], flush=True)
    sources = {}
    totals = {}
    cases = {}
    seen = set()
    for _, file, _, _ in results:
        archive = read_json(Path(file))
        case = archive["case"]
        for row in archive["rows"]:
            u = row["usage"]
            rid = row["physical_id"]
            v = rid.split(":")[0]
            if archive["scope"] != str(EXT_PREFIX.relative_to(ROOT)):
                slot, tokens, cost, provider, body = ledger[rid]
                if rid in seen or (tokens, cost, provider, body) != (
                    u["total_tokens"],
                    u["peak_cost_nanoyuan"],
                    u["provider_response_id"],
                    u,
                ):
                    raise ValueError("Request/settlement mismatch: " + rid)
                seen.add(rid)
                t = totals.setdefault(v, Counter())
                t.update(
                    {
                        k: u[k]
                        for k in (
                            "input_tokens",
                            "output_tokens",
                            "cache_hit_tokens",
                            "cache_miss_tokens",
                            "peak_cost_nanoyuan",
                        )
                    }
                )
                t["requests"] += 1
                t["frozen_local_tokens"] += row["local_input"]
                t["absolute_local_error"] += abs(row["local_input"] - u["input_tokens"])
                t["reasoning_usage_known"] += int(u["reasoning_tokens_known"])
                sources.setdefault(v, Counter()).update(row["source_estimates"])
                sources.setdefault(v + "_output", Counter()).update(row["output_estimates"])
            if case:
                t = cases.setdefault(case, Counter())
                t["requests"] += 1
                t.update({k: n for k, n in row["comparison"].items() if n is not None})
                t["prefix_pairs"] += row["comparison"]["prefix0"] is not None
    if seen != ledger.keys():
        raise ValueError("Missing physical IDs: " + str(len(set(ledger) - seen)))
    summary = {
        "ledger": totals,
        "sources": sources,
        "matched_wires": cases,
        "external_astropy_prefix_separate": True,
        "reasoning_missing_is_unknown": True,
        "new_api_calls": 0,
        "source_method": "pinned tokenizer on disjoint payload fields; signed local template residual is separate",
        "tokenizer_manifest": digest(TOKENIZER.read_bytes()),
        "archives": [
            {
                "file": str(Path(f).relative_to(ROOT)),
                "requests": n,
                "sha256": digest(Path(f).read_bytes()),
            }
            for _, f, n, _ in results
        ],
    }
    atomic_write(REPORT / "token-replay.json", json_bytes(summary))
    print("Reconciled", len(seen), "historical physical requests", flush=True)


if __name__ == "__main__":
    run()
