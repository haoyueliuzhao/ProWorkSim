"""Additional narrow extraction of already selected managed rejection shapes."""

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path("/data0/zhuxinrui/projects/ProWorkSim")
OUT = ROOT / "runs/software-benchmark-v055/score-gap-evidence-r1"
rows = json.loads((OUT / "normal-closed-slot-metadata.json").read_bytes())
groups = defaultdict(
    lambda: {
        "episodes": 0,
        "rejection_count": 0,
        "reasons": Counter(),
        "stages": Counter(),
        "usage_matched": 0,
        "completion_at_2048": 0,
        "reasoning_tokens": 0,
        "completion_tokens": 0,
        "empty_or_missing_original_usage": 0,
    }
)
samples = {}
volume = 0
for row in rows:
    if not row.get("other_format_errors"):
        continue
    p = Path(row["controller"]["path"]).parent / "managed-boundary.json"
    raw = p.read_bytes()
    volume += len(raw)
    v = json.loads(raw)
    g = groups[row["group"]]
    g["episodes"] += 1
    records = v["team_budget"]["model"]["records"]
    for item in v["action_error_policy"].get("other_format_rejections", []):
        reason = item.get("parser_failure", {}).get("reason", item.get("reason", "unknown"))
        g["rejection_count"] += 1
        g["reasons"][reason] += 1
        g["stages"][item.get("parser_failure", {}).get("stage", "unknown")] += 1
        charge = records.get(item["call_id"], {}).get("charge", {})
        usage = charge.get("reported_usage", {})
        if usage:
            g["usage_matched"] += 1
            g["completion_at_2048"] += usage.get("completion_tokens") == 2048
            g["reasoning_tokens"] += usage.get("completion_tokens_details", {}).get(
                "reasoning_tokens", 0
            )
            g["completion_tokens"] += usage.get("completion_tokens", 0)
        else:
            g["empty_or_missing_original_usage"] += 1
        key = row["group"] + ":" + reason
        if key not in samples:
            samples[key] = {
                "selection": "first rejected call in frozen primary slot order",
                "slot_id": row["slot_id"],
                "boundary": {
                    "path": str(p),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "bytes": len(raw),
                },
                "experience_sequence": item["experience_sequence"],
                "call_id": item["call_id"],
                "parser_failure": item.get("parser_failure"),
                "reported_usage": usage,
                "model_message_or_reasoning_text_exported": False,
            }
value = {
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "scope": "Only normal-closed PROJECT episodes with already observed other_format_errors; additional reason and same-call usage fields, no repeat controller audit",
    "groups": dict(groups),
    "samples": samples,
    "read_bytes": volume,
    "model_calls": 0,
    "test_executions": 0,
    "scoring_calls": 0,
    "original_status_changed": False,
}
for root in [OUT, ROOT / "artifacts/software-benchmark-v055/score-gap-evidence-r1"]:
    with (root / "project-format-shapes.json").open("x") as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
print(json.dumps(value["groups"], ensure_ascii=False, indent=2))
