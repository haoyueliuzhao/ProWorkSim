"""Render the one read-only 9B P1 method audit; never execute archived work."""
import argparse
import json
from pathlib import Path

from proworksim.software_mapper_v035 import map_software_method, mapping_spec
from proworksim.software_method_evidence_v035 import build_software_evidence
from proworksim.storage import digest, json_bytes, read_json

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "runs/software-local-feasibility-v034/qwen3.5-9b/actual/diagnostics"
OUTPUT = ROOT / "runs/v035-controls/mapper"


def reference(path):
    return {"path": str(Path(path).resolve()), "file_sha256": digest(Path(path).read_bytes())}


def review(source=SOURCE, output=OUTPUT, *, collect_evidence=False):
    source, output = Path(source), Path(output)
    details = output / "p1-review"
    details.mkdir(parents=True, exist_ok=True)
    if collect_evidence:
        for index in range(4):
            folder = source / f"slot-{index}"
            entry = read_json(folder / "entry.json")
            evidence = build_software_evidence(folder, rollout=entry["rollout"])
            mapping = map_software_method(entry["rollout"], evidence)
            (details / f"slot-{index}-evidence.json").write_bytes(json_bytes(evidence))
            (details / f"slot-{index}-mapping.json").write_bytes(json_bytes(mapping))
    (details / "mapping-spec.json").write_bytes(json_bytes(mapping_spec()))
    rows = []
    for index in range(4):
        ep, mp = details / f"slot-{index}-evidence.json", details / f"slot-{index}-mapping.json"
        e, m = read_json(ep), read_json(mp)
        if e["evidence_sha256"] != digest(json_bytes({k: v for k, v in e.items() if k != "evidence_sha256"})):
            raise ValueError("Saved evidence seal changed")
        if m["evidence_sha256"] != e["evidence_sha256"] or m["mapper_spec_sha256"] != digest(json_bytes(mapping_spec())):
            raise ValueError("Saved mapping differs from current frozen evidence/specification")
        chain = e["delivery_chain"]
        side = [item for item in e["organization_and_fixed_products"]
                if item["kind"] == "integrate" and not item["on_delivered_version_ancestry"]]
        rows.append({"slot_index": index, "case_id": e["case_binding"]["case_id"],
            "first_member": e["case_binding"]["first_member"], "window": e["window"],
            "original_assessment": e["original_assessment"], "mapping_status": m["status"],
            "class_id": m["class_id"], "mapping_reason": m["reason"],
            "composition_support_eligible": m["composition_support_eligible"],
            "actual_calls": len(e["actual_calls"]),
            "actual_prompt_tokens": sum(c["input_tokens"] for c in e["actual_calls"]),
            "actual_own_output_tokens": sum(c["own_output_tokens"] for c in e["actual_calls"]),
            "actual_input_binding_complete": e["actual_visibility_complete"],
            "members": {key: {k: v[k] for k in ["own_action_count", "own_action_tokens", "complete_actor_trajectory",
                "actual_input_bindings_complete", "own_targets_sha256"]} for key, v in e["members"].items()},
            "organization": [{k: event[k] for k in ["world_sequence", "experience_sequence", "kind", "actor_id", "facts"]}
                             for event in e["organization_and_fixed_products"]],
            "delivery": chain["delivery"], "delivered_version_ancestry": chain["ancestors"],
            "current_version_test": chain.get("current_version_test"),
            "test_feedback_seen_before_submit": chain["current_test_feedback_seen_before_submit"],
            "test_feedback_presentations": [{k: p[k] for k in ["member_id", "call_id", "input_sequence", "message_index", "selected_request_sha256"]}
                                            for p in chain.get("test_feedback_presentations", [])],
            "peer_integrations_in_delivery_chain": chain["peer_integrations"],
            "side_branch_imports": [{"event": {k: item[k] for k in ["world_sequence", "experience_sequence", "actor_id", "facts"]},
                "actual_import_receipt_presentations": len(item["real_response_presentations"]),
                "later_same_member_tests": [t["world_test"] | {"source_reference": t["source_reference"],
                    "backend_passed": t["backend_passed"], "actual_feedback_presentations": len(t["actual_public_feedback_presentations"])}
                    for t in e["test_information_boundary"] if t["world_test"]["actor_id"] == item["actor_id"]
                    and t["world_test"]["world_sequence"] > item["world_sequence"]]} for item in side],
            "actual_tests": len(e["test_information_boundary"]),
            "test_returns_seen_in_later_actual_input": sum(bool(t["actual_public_feedback_presentations"])
                                                           for t in e["test_information_boundary"]),
            "evidence": reference(ep), "mapping": reference(mp)})
    totals = {"episodes": 4, "complete_successes": sum(r["original_assessment"]["R"] == 1 for r in rows),
              "distinct_exact_xi": len({r["window"]["xi_fingerprint"] for r in rows}),
              **{key: sum(r[key] for r in rows) for key in ["actual_calls", "actual_prompt_tokens", "actual_own_output_tokens",
                                                           "actual_tests", "test_returns_seen_in_later_actual_input"]},
              "diagnostic_mapped": sum(r["mapping_status"] == "mapped" for r in rows),
              "diagnostic_unmapped": sum(r["mapping_status"] != "mapped" for r in rows)}
    report = {"version": "p1-readonly-method-review-v0.35", "passed": True,
        "source": str(source.resolve()), "scope": "Only the selected 9B's four closed v034 P1 development slots",
        "model_calls": 0, "gpu_used": False, "new_test_or_acceptance_executions": 0,
        "p1_training_or_support_admission": False, "repeated_p1_execution": False,
        "report_render_used_saved_evidence": not collect_evidence,
        "mapping_spec": mapping_spec(), "rows": rows, "totals": totals,
        "conclusions": [
            "Two complete successes exhibit one delivered-tree mechanism, own_tree_delivery, in different root/first-member xi contexts. They do not supply two method classes or same-xi repetitions.",
            "Real peer conflict imports and visible receipts exist on non-delivered branches; these do not establish peer product consumption in the accepted delivery.",
            "Twenty-seven public tests occurred; only twenty-six returns are proved present in later actual selected inputs. Backend execution is not presentation.",
            "All four records remain model_interface_development and are barred from P2 support, actor optimization and independent confirmation.",
            "P2 second-class production rate remains unknown. No M planning rate is inferred from P1 2/4.",
            "Materialized artifacts, visible import receipts and presented source text are separate evidence relations.",
            "Continuous whole-file preservation and public contract definition change are conservative recognizability boundaries, not claims about causal necessity or absence of cooperation in legitimate unmapped rewrites."],
        "coverage_scope": "One read-only evidence pass plus targeted synthetic CPU controls. Native preparation seals and actual IDs checked without new tokenization, model, world test, acceptance or gradient. A later narrow public-definition check reuses the sealed input evidence and reads initial/fixed production files only."}
    (output / "p1-method-review.json").write_bytes(json_bytes(report))
    lines = ["# v0.35 P2准备：9B P1方法与实际可见信息复核", "",
        "仅读取已选9B的四条已关闭P1经历。没有重跑模型、公开检查、独立验收、训练或原生分词；原业务评分与开发用途不变。", "",
        "两个完整成功属于同一可观察交付机制own_tree_delivery，但位于不同根目标/先手的精确情境。不能将2/4成功改称两类支持或合并四个ξ计频，P2次类有效产出率仍未知。", "",
        "| 槽 | 根目标/先手 | 原R | 类别 | 调用 | 输入token | 本人输出token |", "|---|---|---:|---|---:|---:|---:|"]
    for r in rows:
        lines.append(f"| {r['slot_index']} | {r['case_id']} / {r['first_member']} | {r['original_assessment']['R']} | {r['class_id'] or 'unmapped'} | {r['actual_calls']} | {r['actual_prompt_tokens']} | {r['actual_own_output_tokens']} |")
    lines += ["", "191次实际调用逐一绑定原attempt、实际selected-request、原生request/render摘要、input_ids/usage及同成员原始目标。输入1,946,157、本人输出35,670，合计1,981,827 tokens。SDK裁剪前请求不替代实际选中输入；后台完整测试记录与独立验收不补入actor信息/目标。", "",
        "27次实际测试中26次返回可证出现在后续实际输入。names成功槽member_b最后一次测试没有后续呈现证明。通过项被投影删去的值/stdout/API细迹不因后台保存而被认定已见。", "",
        "目录成功槽：A自有v7测试（experience序号521），公开返回首见A实际输入549；B创建任务538，A领取555、固定patch-1于589、提交自己的v7于623。B在606导入A补丁并出现冲突，之后在自己副本继续工作；该支线不在最终交付祖先链。", "",
        "名称成功槽：A自有v7测试463，反馈首见输入491；A创建发布任务497，未领取即发布被拒后，领取559、固定593、提交627。B于610导入A补丁并发生冲突，该支线也不是交付链。不由工具次数或模型自称推断贡献。", "",
        "另两槽unmapped：names/先手A无固定交付，内容与过程未知；directory/先手B有提交，过程及其观测通过但内容失败。失败、未映射和低频经历仍按基础规则处理，不删除P2原始分母；P1本身始终禁入P2。", "",
        "Mapper仅两类：可证的自有交付链；真实伙伴固定产物导入交付祖先，其元数据/回执实际呈现，至少一个完整生产文件规范内容发生变化且原字节持续保留至当前版本测试与固定交付。仅支线导入、冲突、完全撤销、手工借鉴、不确定重写不能制造第二类。", "",
        "非平凡变化绑定case/source_contract中公开合同入口function/class名单。只比较这些定义的去注释、空白、docstring规范AST，排除新增无关顶层helper；不做AST作者归属或语义等价/因果价值推断。动态alias或定义不可判留unmapped。旧P1仅使用其已公开RecordSchema/catalog、NameSchema/find_matches/export_names名单。", "",
        "伙伴类不要求接收者再编辑代码或逐字读取全部源码。file_materialized、import_receipt_presented与source_text_presented分列；前两者不能冒称第三者，也不证明理解或信息独立性。", "",
        "精确ξ绑定window_id、xi_id、xi_fingerprint、gamma_fingerprint、team_policy_fingerprint；来源/用途、根目标、初始状态、成员、先手、调度和信息条件不能后验合并，seed只作为同ξ重复。成员继续用原member_view的本人output IDs、行为概率、labels、loss_mask，不按最终代码署名删伙伴自身动作。", "",
        "API：build_software_evidence(slot_dir, rollout=..., assessment=..., expected_window=...)在entry写入前可用；map_software_method(rollout,evidence,spec=...)返回标准online_support映射及成员投影；mapping_spec()供采集前冻结。版本software-fixed-product-method-v0.35。", "",
        "完整文件字节持续性和公开定义变化只是保守可识别边界，不能否定合法重写中的协作。低频门由后续精确ξ/成员统计执行；Mapper不删轨迹、不改Validity或基础actor/critic分母。"]
    (output / "p1-method-review.md").write_text("\n".join(lines) + "\n")
    return totals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--collect-evidence", action="store_true")
    args = parser.parse_args()
    print(json.dumps(review(args.source, args.output, collect_evidence=args.collect_evidence)))


if __name__ == "__main__":
    main()
