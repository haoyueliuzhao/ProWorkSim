#!/usr/bin/env python3
"""One direct, non-generating official models/balance inspection; no key logging."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from proworksim.software_benchmark_deepseek_api_v055 import (  # noqa: E402
    DOCUMENTED_MODEL_VERSION, DirectHTTPS, HOST, MODEL, VERSION, cny_balance, load_api_key,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite prior metadata evidence")
    transport = DirectHTTPS(load_api_key(args.env_file), timeout_seconds=60)
    started = datetime.now(timezone.utc).isoformat()

    def inspect(path):
        try:
            return {"path": path, "ok": True, "body": transport.request("GET", path)}
        except Exception as error:
            return {"path": path, "ok": False, "error_type": type(error).__name__,
                    "http_status": getattr(error, "http_status", None)}

    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(inspect, ["/models", "/user/balance"]))
    models = [item.get("id") for item in records[0].get("body", {}).get("data", [])]
    balance = cny_balance(records[1].get("body", {}))
    evidence = {
        "version": VERSION, "started_utc": started,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "official_host": HOST, "tls_certificate_verification": True,
        "environment_proxy_used": False, "reverse_proxy_used": False,
        "automatic_redirect": False, "automatic_retry": False,
        "generation_requests": 0, "generation_tokens": 0, "metadata_requests": 2,
        "requested_model": MODEL, "documented_model_version": DOCUMENTED_MODEL_VERSION,
        "model_alias_present": MODEL in models, "observed_model_ids": models,
        "available_balance_cny": str(balance) if balance is not None else None,
        "model_version_not_immutably_pinned_by_alias": True,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x") as output:
        json.dump(evidence, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({key: evidence[key] for key in (
        "official_host", "model_alias_present", "observed_model_ids", "available_balance_cny",
        "generation_requests", "metadata_requests")}, ensure_ascii=False))
    return 0 if all(record["ok"] for record in records) and MODEL in models else 1


if __name__ == "__main__":
    raise SystemExit(main())
