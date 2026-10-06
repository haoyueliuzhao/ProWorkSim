#!/usr/bin/env python3
"""One read-only v035 shadow diagnostic under the separately frozen v036 rule."""
from __future__ import annotations

import argparse
import copy
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from proworksim import software_mapper_v036 as mapper
from proworksim import software_method_evidence_v036 as evidence_module
from proworksim.software_method_evidence_v035 import _file, _sha
from proworksim.storage import atomic_write, json_bytes, read_json

ROOT = Path(__file__).resolve().parents[1]


def analyze_slot(job):
    collection, output, index, completed_slot_root = job
    slot = Path(collection) / f"slot-{index}"
    entry_path = slot / "entry.json"
    entry = read_json(entry_path)
    rollout = entry["rollout"]
    original_mapping = entry["mapping"]
    if rollout.get("online_scope", {}).get("method_mapper_spec_sha256") is not None:
        raise ValueError("Shadow input must be an original pre-v036 collection, not a new support window")
    original_refs = {name: _file(slot / name) for name in ("entry.json", "assessment.json", "software-evidence.json")}
    if completed_slot_root:
        cached_root = Path(completed_slot_root)
        cache = read_json(cached_root / "completed-slot-cache.json")
        if cache["method_source_refs"] != [_file(Path(mapper.__file__)), _file(Path(evidence_module.__file__))]:
            raise ValueError("Completed-slot reuse requires identical method source bytes")
        cached = cache["completed_slots"][str(index)]
        if _file(cached["path"]) != cached:
            raise ValueError("Completed-slot evidence bytes changed")
        evidence = read_json(Path(cached["path"]))
    else:
        evidence = evidence_module.build_software_evidence(slot, rollout=rollout)
    mapping = mapper.map_software_method(rollout, evidence)
    if mapping["composition_support_eligible"] or any(p["support_eligible"] for p in mapping["member_projections"].values()):
        raise ValueError("An old shadow label must never be admitted to new method support")
    if original_refs != {name: _file(slot / name) for name in original_refs}:
        raise ValueError("Original entry, assessment or v035 evidence changed during read-only analysis")
    folder = Path(output) / f"slot-{index:02d}"
    atomic_write(folder / "evidence.json", json_bytes(evidence))
    atomic_write(folder / "mapping.json", json_bytes(mapping))
    chain = evidence["delivery_chain"]
    return {"slot_index": index, "rollout_id": rollout["rollout_id"], "window": rollout["window"],
        "original_R": evidence["original_assessment"]["R"],
        "original_mapping_status": original_mapping["status"], "original_class_id": original_mapping.get("class_id"),
        "shadow_mapping_status": mapping["status"], "shadow_class_id": mapping.get("class_id"),
        "shadow_reason": mapping["reason"], "shadow_support_eligible": False,
        "complete_actual_input_binding": evidence["actual_visibility_complete"],
        "exact_delivery_chain_verified": chain["verified"],
        "current_test_feedback_seen_before_submit": chain["current_test_feedback_seen_before_submit"],
        "process_attributes": chain["process_attributes"],
        "unexplained_critical_dependencies": chain["unexplained_critical_dependencies"],
        "imports": [{"patch_id": p["patch_id"], "producer": p["producer"], "recipient": p["recipient"],
            "historical_import_status": p["status"], "route_state": p["route_state"],
            "explanation_complete": p["explanation_complete"],
            "qualifying_fixed_product_consumption": p["qualifying_fixed_product_consumption"],
            "retained_units": [{"path": u["path"], "symbol": u["symbol"], "mode": u["mode"],
                "producing_event": u["producing_event"], "producing_input_sequence": u["producing_input_sequence"],
                "continuous_retained_versions": u["continuous_retained_versions"],
                "final_file_equal_incoming": u["final_file_equal_incoming"]} for u in p["retained_production_units"]],
            "comparisons": p["production_unit_comparisons"],
            "discarded_unit_resets": p["discarded_unit_resets"],
            "information_timing_failures": p["information_timing_failures"],
            "dependency_issues": p["dependency_issues"],
            "actual_source_fragment_presentations": len(p["source_text_presentations"])} for p in chain["peer_integrations"]],
        "old_files_unchanged": original_refs, "new_evidence": _file(folder / "evidence.json"),
        "new_shadow_mapping": _file(folder / "mapping.json")}


def reuse_with_dependency_delta(row):
    """Recheck changed lexical dependency logic without rereading model inputs."""
    row = copy.deepcopy(row)
    evidence_path = Path(row["new_evidence"]["path"])
    if _file(evidence_path) != row["new_evidence"]:
        raise ValueError("Prior bound shadow evidence changed")
    evidence = read_json(evidence_path)
    if evidence["mapper_spec_sha256"] != _sha(mapper.mapping_spec()):
        raise ValueError("Cannot reuse evidence across different frozen method specifications")
    chain = evidence["delivery_chain"]
    if row["shadow_mapping_status"] != "mapped" and evidence["original_complete_validity"] is True:
        raise ValueError("A previously valid-but-unmapped slot must be explicitly rebuilt")
    proofs = {_sha(p["source_reference"]): p for p in evidence["immutable_version_proofs"]}
    bundles = {}
    def bundle(reference):
        key = _sha(reference)
        if key not in bundles:
            proof = proofs[key]
            if _file(proof["path"])["file_sha256"] != proof["file_sha256"]:
                raise ValueError("Immutable original production bytes changed")
            bundles[key] = read_json(Path(proof["path"]))
        return bundles[key]
    checks = []
    for peer in chain["peer_integrations"]:
        for unit in peer["retained_production_units"]:
            if not unit["dependency_explanation"]["explained"]:
                raise ValueError("Prior accepted unit lacks its original dependency witness")
            proof = evidence_module._unit_dependencies(unit["path"], unit["symbol"],
                bundle(peer["fixed_source_reference"]), bundle(chain["delivery"]["source_reference"]),
                chain["contract_symbols"], chain["ancestors"])
            if not proof["explained"]:
                raise ValueError("Dependency delta changed a retained witness; explicitly rebuild this slot")
            checks.append({"patch_id": peer["patch_id"], "path": unit["path"], "symbol": unit["symbol"],
                           "prior_explained": True, "updated_dependency_explanation": proof})
    row["analysis_origin"] = "prior_native_input_and_version_evidence_reused_with_pure_lexical_dependency_delta"
    row["dependency_scope_delta_checks"] = checks
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path,
                        default=ROOT / "runs/software-support-v035/qwen3.5-9b/actual/collection")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/v036-controls/methods/shadow-v035")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--baseline-report", type=Path,
                        help="Prior completed shadow; reuse bound inputs and recheck only the dependency-scope delta")
    parser.add_argument("--rebuild-slots", type=int, nargs="+", default=None)
    parser.add_argument("--reuse-completed-slot-root", type=Path,
                        help="Reuse a completed per-slot build after an aggregation-only error; identical method source required")
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        raise ValueError("Use a bounded 1..8 read-only CPU worker pool")
    if bool(args.baseline_report) != bool(args.rebuild_slots):
        raise ValueError("A partial delta requires both --baseline-report and --rebuild-slots")
    if args.reuse_completed_slot_root and not args.baseline_report:
        raise ValueError("Completed per-slot reuse is only for an explicit partial diagnostic")
    collection, output = args.collection.resolve(), args.output.resolve()
    if output.exists():
        raise ValueError("Use a new shadow output directory; never overwrite a diagnostic")
    source_paths = [Path(__file__), Path(mapper.__file__), Path(evidence_module.__file__),
                    ROOT / "src/proworksim/software_method_evidence_v035.py",
                    ROOT / "src/proworksim/member_views.py", ROOT / "src/proworksim/team_rollout.py",
                    ROOT / "src/proworksim/storage.py"]
    source_refs = [_file(path) for path in source_paths]
    support_path = collection.parent / "support-gate.json"
    original_support = _file(support_path)
    output.mkdir(parents=True)
    atomic_write(output / "mapping-spec.json", json_bytes(mapper.mapping_spec()))
    baseline = read_json(args.baseline_report) if args.baseline_report else None
    indices = sorted(set(args.rebuild_slots)) if baseline else list(range(16))
    if not indices or any(index not in range(16) for index in indices):
        raise ValueError("Shadow slot inventory is exactly the original 0..15")
    if baseline and (baseline["mapper_spec_sha256"] != _sha(mapper.mapping_spec())
                     or baseline["original_collection"] != str(collection)
                     or [r["slot_index"] for r in baseline["rows"]] != list(range(16))):
        raise ValueError("Delta baseline is not the same original window and method spec")
    cached_root = str(args.reuse_completed_slot_root.resolve()) if args.reuse_completed_slot_root else None
    jobs = [(str(collection), str(output), index, cached_root) for index in indices]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(analyze_slot, jobs))
    for row in rows:
        row["analysis_origin"] = ("completed_slot_build_reused_after_aggregation_only_error" if cached_root
                                  else "full_original_slot_read_only_evidence_build")
    if baseline:
        rows.extend(reuse_with_dependency_delta(row) for row in baseline["rows"] if row["slot_index"] not in indices)
        rows.sort(key=lambda row: row["slot_index"])
    if source_refs != [_file(path) for path in source_paths] or original_support != _file(support_path):
        raise ValueError("Frozen source or original support changed during the diagnostic")
    counts = {category: sum(r["shadow_class_id"] == category for r in rows) for category in mapper.CLASS_ORDER}
    counts["unmapped"] = sum(r["shadow_mapping_status"] != "mapped" for r in rows)
    report = {"version": "software-method-shadow-v0.36-on-v035", "mapper_spec_sha256": _sha(mapper.mapping_spec()),
        "source_refs": source_refs, "original_support_unchanged": original_support,
        "original_collection": str(collection), "rows": rows, "shadow_counts": counts,
        "preceding_shadow": _file(args.baseline_report) if args.baseline_report else None,
        "fully_rebuilt_slots": indices, "reused_slots": [i for i in range(16) if i not in indices],
        "pure_dependency_delta_checks": sum(len(row.get("dependency_scope_delta_checks", [])) for row in rows),
        "completed_slot_build_reuse": _file(Path(cached_root) / "completed-slot-cache.json") if cached_root else None,
        "original_episodes": 16, "original_complete_successes": sum(r["original_R"] == 1 for r in rows),
        "old_scores_changed": False, "old_mapping_changed": False, "old_support_changed": False,
        "new_support_contribution": 0, "P3_material": False,
        "target_model_calls": 0, "gpu_used": False, "new_world_executions": 0,
        "new_test_or_acceptance_executions": 0, "new_native_tokenizations": 0,
        "passed": len(rows) == 16 and all(not r["shadow_support_eligible"] for r in rows),
        "scope": "Development-only shadow diagnostic. These are old observations under a new finite representation, not a new sample, regraded validity, current-policy support, causal credit, contribution feedback or parameter-learning evidence."}
    atomic_write(output / "report.json", json_bytes(report))
    lines = ["# v0.36 表示对旧 v0.35 窗口的影子诊断", "",
        "本文件只读分析原16槽。旧评分、Mapper输出、支持门和停止决定均保持；所有新影子标签的支持资格为false，不进入新窗口或P3。", "",
        "| 槽 | 原R | 原类别 | v0.36影子类别 | 导入状态 |", "|---|---:|---|---|---|"]
    for row in rows:
        state = "; ".join(p["patch_id"] + ":" + p["route_state"] for p in row["imports"]) or "无最终链伙伴导入"
        lines.append(f"| {row['slot_index']} | {row['original_R']} | {row['original_class_id'] or 'unmapped'} | {row['shadow_class_id'] or 'unmapped'} | {state} |")
    lines += ["", "影子计数：" + str(counts), "",
        "计数不是表示的优化目标，不能直接作为新类产出率或正式支持。公开生产单元结构、实际呈现时序、同路径变换、静态依赖和最终测试/固定交付共同构成有限证据；AST相同不独立证明语义等价或因果采用。", "",
        "未调用模型/GPU，未重新分词、运行世界、测试或验收。逐槽细节与所有源/原件摘要见report.json及slot-XX/evidence.json。"]
    if baseline:
        lines += ["", "本次为作用域检查修复的增量诊断：只完整重建槽" + str(indices)
                  + "；其余槽复用前次已绑定原输入/版本证据，并对所有已接纳生产单元执行新的纯静态依赖检查。原始完整影子及其源码快照均保留。"]
    atomic_write(output / "report.md", ("\n".join(lines) + "\n").encode())
    print(str(output / "report.json"))
    print("shadow_counts=" + str(counts) + "; new_support_contribution=0")


if __name__ == "__main__":
    main()
