"""Paired T1/T2 encodings of every v231 physical request, joined by actual request identity."""

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import os
import sqlite3

from proworksim.software_context_builder_v230 import build, identity, recover_observations
from proworksim.software_context_fields_v231_1 import transform
from proworksim.software_context_panel_v231 import ROOT, RUN
from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
from proworksim.storage import read_json, digest, json_bytes, atomic_write

ART = ROOT / "artifacts/software-benchmark-v231-1/context-r1"


def analyze(folder):
    os.environ["RAYON_NUM_THREADS"] = "1"
    path = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    tok = OfficialDeepSeekCounter(path, manifest_sha256=digest(path.read_bytes()))
    ids = {}
    fields = Counter()
    stats = Counter()
    pairs = []
    for req in (folder / "api").glob("*/request.json"):
        r = read_json(req)
        u = read_json(req.with_name("usage.json"))
        ids[r["payload"]["request_id"]] = (r, u)
    for mpath in (folder / "telemetry/worker").glob("*/manifest.json"):
        m = read_json(mpath)
        raw = read_json(mpath.with_name("original.json"))
        r, u = ids.pop(m["request_id"])
        shown = read_json(mpath.with_name("shown.json"))
        if (
            r["payload"]["wire"] != shown
            or identity(raw) != m["original_wire"]
            or identity(shown) != m["shown_wire"]
        ):
            raise ValueError("Archived wire or request association differs")
        t1 = (
            shown
            if folder.name == "T1"
            else build(raw, actor=m["actor"], role=m["role"], condition="T1")[0]
        )
        t2, events = transform(t1, m["actor"])
        restored, _ = transform(t2, m["actor"], restore=True)
        if identity(t1) != identity(restored) or recover_observations(raw) != recover_observations(
            restored
        ):
            raise ValueError("Loss of evidence, order or role-visible observation")
        n1 = tok.measure(t1)["local_encoded_prompt_tokens"]
        n2 = tok.measure(t2)["local_encoded_prompt_tokens"]
        fields.update(e["field"] for e in events)
        stats.update(
            requests=1,
            t1=n1,
            t2=n2,
            snapshots=len(recover_observations(t1)),
            edited_fields=len(events),
            regressions=int(n2 > n1),
        )
        pairs.append(
            dict(
                request_id=m["request_id"],
                physical_id=r["physical_id"],
                provider_id=u["provider_response_id"],
                input_usage=u["input_tokens"],
                t1=n1,
                t2=n2,
                restored_t1_sha256=identity(restored),
                shown_t2_sha256=identity(t2),
            )
        )
    if ids:
        raise ValueError("Missing archival manifest")
    return dict(
        case=folder.parent.name,
        source_condition=folder.name,
        stats=stats,
        fields=fields,
        requests=sorted(pairs, key=lambda x: x["request_id"]),
    )


def main():
    dirs = sorted(p for p in RUN.glob("*/*") if p.name in ("T0", "T1"))
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(analyze, dirs))
    physical = [r for b in rows for r in b["requests"]]
    db = Path(read_json(RUN / "authority.json")["ledger"])
    with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as conn:
        settled = {
            rid: pid
            for rid, pid in conn.execute(
                "select id,provider_id from requests where slot glob 'v231:*:T[01]' and status='settled'"
            )
        }
    if (
        len(rows) != 6
        or len(physical) != len(settled)
        or {r["physical_id"]: r["provider_id"] for r in physical} != settled
    ):
        raise ValueError("Incomplete paid request coverage")
    for row in rows:
        if row["stats"]["regressions"] or row["stats"]["t2"] >= row["stats"]["t1"]:
            raise ValueError("No all-branch input saving")
    atomic_write(
        ART / "offline.json",
        json_bytes(
            {
                "passed": True,
                "api_calls": 0,
                "cases": rows,
                "tokenizer_manifest_sha256": digest(
                    (ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json").read_bytes()
                ),
            }
        ),
    )


if __name__ == "__main__":
    main()
