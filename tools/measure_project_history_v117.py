#!/usr/bin/env python3
"""Offline fixed-tokenizer comparison on one prespecified middle request/task.

This is a counterfactual input measurement, not a replay, provider usage update,
or new score. Runtime provenance still comes from each live worker registry;
here the frozen original model-input records are the explicit evidence source.
"""
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]


def run():
    os.environ.update(LITELLM_LOCAL_MODEL_COST_MAP="True", OPENHANDS_SUPPRESS_BANNER="1",
                      HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    forbidden = {"network": 0, "subprocess": 0}
    def audit(event, args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
            forbidden["network"] += 1
            raise RuntimeError("Offline token measurement cannot use the network")
        if event in {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"}:
            forbidden["subprocess"] += 1
            raise RuntimeError("Offline token measurement cannot launch a subprocess")
    sys.addaudithook(audit)
    from proworksim.software_benchmark_history_v117 import project_observation_history, VERSION
    from proworksim.software_benchmark_deepseek_tokenizer_v055 import OfficialDeepSeekCounter
    from proworksim.storage import digest, json_bytes
    manifest = ROOT / "runs/software-benchmark-v055/tokenizer-r1/manifest.json"
    counter = OfficialDeepSeekCounter(manifest, manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(), reservation_margin_tokens=0)
    evidence_path = ROOT / "artifacts/software-benchmark-v114/gap-evidence-r1/episodes.json"
    episodes = json.loads(evidence_path.read_bytes())
    results = []
    for row in episodes:
        if row["arm"] != "PROJECT" or not row.get("requests"):
            continue
        samples = row.get("request_structure_samples", [])
        if len(samples) != 3:
            raise ValueError("The outcome-independent first/middle/last sample inventory changed")
        source = Path(samples[1]["evidence"])
        body = source.read_bytes()
        saved = json.loads(body)
        if saved.get("usage_id") != "agent":
            raise ValueError("Only actual frozen agent request samples are admitted")
        original = saved["request"]
        registered = []
        for message in original["messages"]:
            content = message.get("content")
            if message.get("role") != "user" or not isinstance(content, str):
                continue
            try:
                value = json.loads(content)
            except ValueError:
                continue
            if (isinstance(value, dict) and isinstance(value.get("role_task"), str)
                    and isinstance(value.get("observation"), dict)
                    and value["observation"].get("actor_id") == "member_001"):
                registered.append(content)
        projected, projection = project_observation_history(original, member_id="member_001", registered_observations=registered)
        before, after = counter.measure(original), counter.measure(projected)
        results.append({"slot_id": row["slot_id"], "instance_id": row["instance_id"],
            "agent_request_ordinal": samples[1]["agent_request_ordinal"],
            "source": {"path": str(source), "sha256": digest(body), "bytes": len(body)},
            "old_local_encoded_tokens": before["local_encoded_prompt_tokens"],
            "new_local_encoded_tokens": after["local_encoded_prompt_tokens"],
            "token_reduction": before["local_encoded_prompt_tokens"]-after["local_encoded_prompt_tokens"],
            "fraction_reduction": 1-after["local_encoded_prompt_tokens"]/before["local_encoded_prompt_tokens"],
            "original_request_sha256": before["request_sha256"], "projected_request_sha256": after["request_sha256"],
            "projection": projection, "actual_server_token_usage_rewritten": False})
    before = sum(r["old_local_encoded_tokens"] for r in results)
    after = sum(r["new_local_encoded_tokens"] for r in results)
    report = {"version": "v117-frozen-request-offline-token-measurement-r1", "history_policy": VERSION,
        "history_source_sha256": digest((ROOT/"src/proworksim/software_benchmark_history_v117.py").read_bytes()),
        "measurement_tool_sha256": digest(Path(__file__).read_bytes()),
        "sample_rule": "one middle actual agent request for every one of the 48 previously called PROJECT tasks, independent of outcome",
        "samples": len(results), "input_inventory": {"path": str(evidence_path), "sha256": digest(evidence_path.read_bytes())},
        "tokenizer_manifest": {"path": str(manifest), "sha256": counter.manifest_sha256},
        "tokenizer_sha256": counter.tokenizer_sha256, "exact_local_recipe_encoding": True,
        "reservation_margin_tokens": 0, "exact_provider_token_count": False,
        "sum_original_local_tokens": before, "sum_projected_local_tokens": after,
        "mean_original_local_tokens": before/len(results), "mean_projected_local_tokens": after/len(results),
        "aggregate_fraction_reduction": 1-after/before,
        "median_sample_fraction_reduction": statistics.median(r["fraction_reduction"] for r in results),
        "all_reconstructions_passed": all(r["projection"]["validation"]["passed"] for r in results),
        "runtime_registry_reconstruction_claimed": False,
        "offline_provenance_scope": "Already generated frozen model-input requests; live dispatch must use the actual worker observation registry",
        "complete_episode_savings_or_score_improvement_measured": False,
        "historical_usage_or_scores_modified": False, "API_calls": 0, "Docker_operations": 0,
        "GPU_operations": 0, "forbidden_operation_counts": forbidden, "requests": results}
    output = ROOT / "artifacts/software-benchmark-v117/history-controls-r1"
    output.mkdir(parents=True, exist_ok=True)
    (output / "offline-token-measurement.json").write_bytes(json_bytes(report))
    print(json.dumps({k:v for k,v in report.items() if k != "requests"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
