"""Bounded CPU public-port/native/tokenizer qualification of the v0.26 carrier.

These explicit programs are existence controls, never model samples, allocation
support, teacher labels, or evidence of learning. Programs see only their own
actual request/returned tools; frozen case values are not passed to the owner.
"""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

from proworksim.audit import code_identity as source_identity
from proworksim.episode import begin_episode, finish_episode
from proworksim.online_collection import run_fragment
from proworksim.reciprocal_runtime_v026 import runtime
from proworksim.reciprocal_interface_v026 import SINGLE_PACKET_BODY
from proworksim.storage import atomic_write, digest, json_bytes
from proworksim.templates import reciprocal_data_v026 as carrier
from scripts.retail_work_controls_v025 import ProgramOwner

VERSION = "reciprocal-carrier-cpu-controls-v0.26"
TOKENIZER = "runs/assets/models/Qwen3.5-9B-c20223623576"
ROUTES = ("constraint_first", "query_first")
WORKS = carrier.WORKS


def ref(reference):
    return {key: reference[key] for key in ("object_id", "version_id")}


def request_role(request):
    return json.loads(request["messages"][-1]["content"])["observation"]["actor_id"]


class CarrierProgramOwner(ProgramOwner):
    """A role-local CPU witness; no prepared/world/case/expected answers stored."""

    def __init__(
        self, tokenizer=None, *, route="constraint_first", condition="normal", negative=None
    ):
        if route not in ROUTES or condition not in ("normal", "single_pass"):
            raise ValueError("Unknown predeclared program route or communication condition")
        super().__init__("reciprocal_data", tokenizer, control="carrier_v026")
        self.route, self.condition, self.negative = route, condition, negative
        self.visible_choices = []

    def freeze_identity(self):
        return {"policy_version": "explicit-role-local-cpu-witness-v026-not-model"}

    def ingest(self, role, request):
        state = super().ingest(role, request)
        associations = {}
        for message in request["messages"]:
            if message.get("role") == "assistant":
                associations.update(
                    {call["id"]: call["function"]["name"] for call in message.get("tool_calls", [])}
                )
            if (
                message.get("role") == "tool"
                and associations.get(message["tool_call_id"]) == "sql_query"
            ):
                body = json.loads(message["content"])
                if body.get("ok") and body.get("result", {}).get("execution_status") == "success":
                    state["raw_sample_query"] = body["result"]
        return state

    def choose(self, role, obs, state):
        aliases = obs["workspaces"]["TEAM"]
        work = WORKS[role]
        own_code, own_result, own_query = carrier.OWN_ALIASES[role]
        done = (
            "staff_done",
            {"reason": "Explicit CPU reachability witness ended; not model evidence."},
        )
        wait = ("staff_wait", {"reason": "Await the actual partner version."})
        phase = state.setdefault("phase", 0)
        if self.route == "query_first" and role == "consumer" and not state.get("queried"):
            state["queried"] = True
            return "sql_query", {
                "work_id": work,
                "source_alias": "raw",
                "output_alias": own_query,
                "sql": "SELECT InvoiceNo,CustomerID,Quantity,UnitPrice FROM retail ORDER BY SourceRow LIMIT 4",
            }

        def material(alias):
            return state["materials"][aliases[alias]]

        def read_alias(alias):
            # Alias and exact-version reads share public permission checks. No
            # optional work_id is needed for a local readable object.
            return "read_alias", {"alias": alias}

        def adopt(alias):
            return "adopt", {
                "alias": alias,
                **ref(material(alias)["reference"]),
                "policy": "current_applicable" if alias == "m_result" else "fixed",
                "work_ids": [work],
            }

        def next_action(action):
            state["phase"] += 1
            return action

        if role == "maintainer":
            if phase == 0:
                return next_action(read_alias("raw"))
            if phase == 1:
                return next_action(read_alias("source_contract"))
            if phase == 2:
                # No unused optional source-contract packet is required. The
                # actual fixed interface_meta later carries the export unit.
                state["phase"] += 1
                phase += 1
            if phase == 3:
                handed = [
                    h
                    for h in obs.get("handoffs", {}).values()
                    if h.get("route_id") == "demand" and h.get("status") == "delivered"
                ]
                if not handed:
                    return wait
                return next_action(read_alias("demand"))
            if phase in (4, 5, 6):
                return next_action(adopt(carrier.SOURCE_ALIASES[role][phase - 4]))
            if phase == 7:
                code = carrier.witness_code(None, role)
                if self.negative == "ignore_demand_distinction":
                    code["models"][0]["sql"] = code["models"][0]["sql"].replace(
                        "d.invoice_mode='net_signed'", "FALSE"
                    )
                return next_action(
                    (
                        "write_object",
                        {
                            "work_id": work,
                            "alias": own_code,
                            "data": code,
                            "dependencies": [
                                ref(material(a)["reference"]) for a in carrier.SOURCE_ALIASES[role]
                            ],
                        },
                    )
                )
            if phase == 8:
                return next_action(
                    (
                        "sql_build",
                        {
                            "work_id": work,
                            "code_alias": own_code,
                            "output_alias": own_result,
                            "input_aliases": list(carrier.SOURCE_ALIASES[role]),
                        },
                    )
                )
            if phase == 9:
                if state["last"].get("execution_status") != "success":
                    raise ValueError({"cpu_source_build_failed": state["last"]})
                return next_action(
                    ("submit", {"work_id": work, "artifacts": [own_code, own_result]})
                )
            if phase == 10:
                pending = obs["work_items"][WORKS["consumer"]]["pending_submission_id"]
                if not pending:
                    return wait
                state["review_sid"] = pending
                return next_action(
                    (
                        "inspect_submission",
                        {
                            "work_id": WORKS["consumer"],
                            "submission_id": pending,
                            "include_contract": False,
                        },
                    )
                )
            if phase in (11, 12):
                alias = "c_code" if phase == 11 else "c_result"
                inspected = state["inspects"][state["review_sid"]]
                return next_action(
                    (
                        "read_version",
                        {
                            "reference": {
                                "object_id": aliases[alias],
                                "version_id": inspected["artifact_versions"][aliases[alias]],
                            }
                        },
                    )
                )
            if phase == 13:
                # Independent arithmetic uses only this role's actually read
                # raw/demand/source contract and the actual fixed final result.
                expected = carrier.expected_products(
                    **{a: material(a)["data"] for a in ("raw", "demand", "source_contract")}
                )
                if not carrier._matches(material("c_result")["data"], expected["consumer"]):
                    if self.negative:
                        state["negative_observed_wrong_product"] = True
                        return done
                    raise ValueError("Visible fixed consumer product failed CPU independent review")
                return next_action(
                    (
                        "approve",
                        {"work_id": WORKS["consumer"], "submission_id": state["review_sid"]},
                    )
                )
            return done

        if phase == 0:
            return next_action(read_alias("demand"))
        if phase == 1:
            arguments = {
                "work_id": WORKS["maintainer"],
                "route_id": "demand",
                "handoff_key": "current-consumer-demand",
                "reference": ref(material("demand")["reference"]),
            }
            if self.condition == "normal":
                demand = carrier._records(material("demand")["data"]["tables"]["demand_meta"])[0]
                arguments["body"] = (
                    "Use " + demand["invoice_mode"] + " under this exact demand version."
                )
                if self.route == "query_first":
                    query = state["raw_sample_query"]
                    rows = [
                        row for table in query["tables"].values() for row in carrier._records(table)
                    ]
                    negative = sum(
                        row["Quantity"] < 0 or row["InvoiceNo"].upper().startswith("C")
                        for row in rows
                    )
                    explanation = f"The actual raw sample contains {negative} cancellation/negative rows in {len(rows)} rows. "
                    explanation += (
                        "Exclude those rows for this demand."
                        if demand["invoice_mode"] == "sales_only"
                        else "Retain their signed quantities for this demand."
                    )
                    arguments["body"] += " " + explanation
                    self.visible_choices.append(
                        {
                            "role": role,
                            "actual_query_reference": query["reference"],
                            "sample_rows": len(rows),
                            "cancellation_or_negative_rows": negative,
                            "selected_explanation": explanation,
                            "use": "query result conditions actual demand handoff explanation",
                        }
                    )
            if self.condition == "single_pass":
                arguments["body"] = SINGLE_PACKET_BODY
            return next_action(("handoff_information", arguments))
        if phase == 2:
            # Perform this already-available source adoption while the partner
            # builds. A consumer need not read the maintainer's private source
            # contract: its required executed input is the fixed interface_meta.
            return next_action(adopt("demand"))
        if phase == 3:
            pending = obs["work_items"][WORKS["maintainer"]]["latest_submission_id"]
            if not pending:
                return wait
            state["source_sid"] = pending
            return next_action(
                (
                    "inspect_submission",
                    {
                        "work_id": WORKS["maintainer"],
                        "submission_id": pending,
                        "include_contract": False,
                    },
                )
            )
        if phase in (4, 5):
            alias = "m_code" if phase == 4 else "m_result"
            inspected = state["inspects"][state["source_sid"]]
            return next_action(
                (
                    "read_version",
                    {
                        "reference": {
                            "object_id": aliases[alias],
                            "version_id": inspected["artifact_versions"][aliases[alias]],
                        }
                    },
                )
            )
        if phase == 6:
            return next_action(adopt("m_result"))
        if phase == 7:
            state["phase"] += 1
            phase += 1
        if phase == 8:
            code = carrier.witness_code(None, role)
            if self.negative == "ignore_unit_distinction":
                code["models"][0]["sql"] = code["models"][0]["sql"].replace(
                    "(CASE WHEN m.amount_unit='GBP' THEN 100 ELSE 1 END)", "1"
                )
            return next_action(
                (
                    "write_object",
                    {
                        "work_id": work,
                        "alias": own_code,
                        "data": code,
                        "dependencies": [
                            ref(material(a)["reference"]) for a in carrier.SOURCE_ALIASES[role]
                        ],
                    },
                )
            )
        if phase == 9:
            return next_action(
                (
                    "sql_build",
                    {
                        "work_id": work,
                        "code_alias": own_code,
                        "output_alias": own_result,
                        "input_aliases": list(carrier.SOURCE_ALIASES[role]),
                    },
                )
            )
        if phase == 10:
            if state["last"].get("execution_status") != "success":
                raise ValueError({"cpu_consumer_build_failed": state["last"]})
            return next_action(("submit", {"work_id": work, "artifacts": [own_code, own_result]}))
        return done


def code_identity():
    paths = [
        Path("scripts/reciprocal_carrier_controls_v026.py"),
        Path("src/proworksim/templates/reciprocal_data_v026.py"),
        Path("src/proworksim/reciprocal_runtime_v026.py"),
        Path("src/proworksim/reciprocal_interface_v026.py"),
        Path("src/proworksim/work_interface.py"),
        Path("src/proworksim/world_core.py"),
        Path("src/proworksim/presentations.py"),
        Path("scripts/retail_work_controls_v025.py"),
    ]
    return {str(path): digest(path.read_bytes()) for path in paths}


def first_requests(requests):
    result = {}
    for request in requests:
        role = request_role(request)
        result.setdefault(
            role, {"sha256": digest(json_bytes(request)), "bytes": len(json_bytes(request))}
        )
    return result


def run_control(
    case,
    output,
    tokenizer=None,
    *,
    route="constraint_first",
    condition="normal",
    negative=None,
    seed=202610040000,
):
    output = Path(output)
    prepared = carrier.build_case(case, output)
    owner = CarrierProgramOwner(tokenizer, route=route, condition=condition, negative=negative)
    runner, captures, _ = runtime(owner, prepared, output, condition, episode_key=str(seed))
    episode = output / "episode"
    begin_episode(
        prepared.world,
        episode,
        experience=runner.recorder.snapshot(),
        work_ids=list(WORKS.values()),
        scenario=prepared.scenario,
        policies=runner.policy_identities,
    )
    termination = run_fragment(prepared, runner)
    finish_episode(
        prepared.world, episode, experience=runner.recorder.snapshot(), termination=termination
    )
    assessment = carrier.assess_episode(episode)
    attempts = dict(Counter(request_role(r) for r in owner.requests))
    token_failures = [
        t
        for t in owner.tokens
        if not t["fits_prompt_and_reserved_output"] or not t["program_output_within_limit"]
    ]
    events = runner.recorder.snapshot()["events"]
    calls = [e for e in events if e["kind"] == "tool_call"]
    communication = [
        e for e in calls if e["payload"]["action"] in {"request_information", "handoff_information"}
    ]
    refusals = [e for e in calls if e["payload"]["response"].get("ok") is False]
    source_state = json.loads((episode / "end/control/state.json").read_text())
    # Post-hoc reporting only; these values are never passed to choose().
    products = {}
    for role in carrier.ROLES:
        artifact = next(
            a
            for a in source_state["artifacts"].values()
            if a["alias"] == carrier.OWN_ALIASES[role][1]
        )
        version = artifact["current_version"]
        manifest = json.loads((episode / "manifest.json").read_text())
        file = next(
            f
            for f in manifest["end"]["files"]
            if f["object_id"] == artifact["object_id"] and f["version_id"] == version
        )
        data = json.loads((episode / manifest["end"]["path"] / file["path"]).read_text())
        products[role] = {
            "reference": {"object_id": artifact["object_id"], "version_id": version},
            "tables": data.get("tables"),
            "table_sha256": digest(json_bytes(data.get("tables"))),
        }
    row = {
        "case_id": case["case_id"],
        "case_index": int(case["case_id"].rsplit("-", 1)[-1]),
        "prototype": case["prototype"],
        "target_role": case["counterfactual_member"],
        "seed": seed,
        "route": route,
        "condition": condition,
        "negative_control": negative,
        "scope": "Explicit role-local CPU program through actual native parser, compact public interface and WorldCore; never model support or learning evidence",
        "model_calls": 0,
        "parameter_updates": 0,
        "program_requests": attempts,
        "role_limits": case["role_decision_limits"],
        "within_role_budgets": all(n <= 24 for n in attempts.values()),
        "tokenizer_checked": tokenizer is not None,
        "tokens": owner.tokens,
        "maximum_prompt_tokens": max((t["prompt_tokens"] for t in owner.tokens), default=None),
        "maximum_program_output_tokens": max(
            (t["program_output_tokens"] for t in owner.tokens), default=None
        ),
        "token_failures": token_failures,
        "context_limit": 16384,
        "reserved_output": 2048,
        "first_requests": first_requests(owner.requests),
        "first_tool_definitions": {
            role: next((r["tools"] for r in owner.requests if request_role(r) == role), None)
            for role in carrier.ROLES
        },
        "communication_actions": communication,
        "query_evidence_uses": owner.visible_choices,
        "tool_refusals": refusals,
        "assessment": assessment,
        "termination": termination,
        "products": products,
        "episode_manifest": {
            "path": str((episode / "manifest.json").resolve()),
            "sha256": digest((episode / "manifest.json").read_bytes()),
        },
        "requests_reference": {
            "path": str((output / "requests.json").resolve()),
            "sha256": digest(json_bytes(owner.requests)),
        },
    }
    row["passed"] = bool(
        assessment["eligible"]
        and assessment["completed"]
        and not refusals
        and row["within_role_budgets"]
        and tokenizer is not None
        and not token_failures
    )
    atomic_write(output / "control.json", json_bytes(row))
    atomic_write(output / "requests.json", json_bytes(owner.requests))
    atomic_write(output / "capture.json", json_bytes(captures))
    return row


def paired_checks(controls):
    checks = []
    for condition, route in [("normal", r) for r in ROUTES] + [("single_pass", "constraint_first")]:
        for left_index in (0, 2):
            pair = [
                next(
                    (
                        r
                        for r in controls
                        if r["case_index"] == i
                        and r["condition"] == condition
                        and r["route"] == route
                        and not r["negative_control"]
                    ),
                    None,
                )
                for i in (left_index, left_index + 1)
            ]
            if not all(pair):
                continue
            a, b = pair
            role = a["target_role"]
            initial_equal = a["first_requests"][role] == b["first_requests"][role]
            source_changed = (
                a["products"]["maintainer"]["tables"] != b["products"]["maintainer"]["tables"]
            )
            consumer_changed = (
                a["products"]["consumer"]["tables"] != b["products"]["consumer"]["tables"]
            )
            unit_evidence = None
            if (
                left_index == 2
                and a["products"]["maintainer"]["tables"]
                and b["products"]["maintainer"]["tables"]
            ):
                left_tables, right_tables = (r["products"]["maintainer"]["tables"] for r in pair)
                left_rows = {
                    (r["CustomerID"], r["InvoiceNo"]): Decimal(str(r["amount"]))
                    for r in carrier._records(left_tables["invoice_view"])
                }
                right_rows = {
                    (r["CustomerID"], r["InvoiceNo"]): Decimal(str(r["amount"]))
                    for r in carrier._records(right_tables["invoice_view"])
                }
                units = [
                    carrier._records(t["interface_meta"])[0]["amount_unit"]
                    for t in (left_tables, right_tables)
                ]
                unit_evidence = {
                    "interface_units": units,
                    "invoice_keys_equal": left_rows.keys() == right_rows.keys(),
                    "amounts_changed_by_exact_factor_100": bool(left_rows)
                    and left_rows.keys() == right_rows.keys()
                    and all(right_rows[k] == 100 * v for k, v in left_rows.items()),
                }
            checks.append(
                {
                    "case_indices": [left_index, left_index + 1],
                    "condition": condition,
                    "route": route,
                    "target_role": role,
                    "first_request_bytes_identical": initial_equal,
                    "first_request_sha256": [r["first_requests"][role]["sha256"] for r in pair],
                    "actual_source_product_changed": source_changed,
                    "actual_final_metric_changed": consumer_changed,
                    "expected_final_metric_change": left_index == 0,
                    "unit_pair_evidence": unit_evidence,
                    "passed": initial_equal
                    and source_changed
                    and consumer_changed == (left_index == 0)
                    and all(r["assessment"]["completed"] for r in pair)
                    and (
                        left_index == 0
                        or bool(
                            unit_evidence
                            and unit_evidence["interface_units"] == ["GBP", "pence"]
                            and unit_evidence["amounts_changed_by_exact_factor_100"]
                        )
                    ),
                }
            )
    return checks


def business_tools(definitions):
    return {
        d["function"]["name"]: d
        for d in definitions
        if d["function"]["name"] not in {"request_information", "handoff_information"}
    }


def fairness_checks(controls):
    checks = []
    for index in range(4):
        normal = next(
            (
                r
                for r in controls
                if r["case_index"] == index
                and r["condition"] == "normal"
                and r["route"] == "constraint_first"
                and not r["negative_control"]
            ),
            None,
        )
        single = next(
            (
                r
                for r in controls
                if r["case_index"] == index
                and r["condition"] == "single_pass"
                and not r["negative_control"]
            ),
            None,
        )
        if not normal or not single:
            continue
        tools_equal = all(
            business_tools(normal["first_tool_definitions"][role])
            == business_tools(single["first_tool_definitions"][role])
            for role in carrier.ROLES
        )
        actions = single["communication_actions"]
        one_legal = (
            len(actions) == 1
            and actions[0]["worker_id"] == "consumer"
            and actions[0]["payload"]["action"] == "handoff_information"
        )
        if one_legal:
            arguments = actions[0]["payload"]["arguments"]
            one_legal = (
                arguments.get("route_id") == "demand"
                and arguments.get("reference", {}).get("version_id") == "v1"
                and arguments.get("body") == SINGLE_PACKET_BODY
            )
        checks.append(
            {
                "case_index": index,
                "business_tool_definitions_equal": tools_equal,
                "same_decision_context_output_budgets": all(
                    normal[k] == single[k]
                    for k in ("role_limits", "context_limit", "reserved_output")
                ),
                "exactly_one_legal_demand_forward": one_legal,
                "both_conditions_reachable": normal["passed"] and single["passed"],
                "passed": bool(tools_equal and one_legal and normal["passed"] and single["passed"]),
            }
        )
    return checks


def render_markdown(report):
    lines = [
        "# v0.26 协作载体 CPU 资格验证",
        "",
        "这是公开端口上的显式程序可达性检验。没有模型推理、GPU 计算、参数更新、教师轨迹或有效方法支持；它只回答指定工具、调度和预算下是否存在完整路线。",
        "",
        f"资格结果：**{'通过' if report['passed'] else '未通过'}**。GPU 启动资格：`{report['gpu_launch_qualified']}`。",
        "",
        "每成员最多 24 次决定，实际官方 tokenizer 上下文 16,384，固定预留输出 2,048；程序工具正文也须不超过 2,048。没有为见证放宽预算。",
        "",
        "程序仅从各成员实际 observation 与自己的工具返回选择动作。maintainer 的复核算术只用它已合法读取的 raw/demand/source_contract；generic witness SQL 不读取 case ID 或隐藏事实。正常条件保留先交换约束、先合法查询两种可行执行顺序（不据此预认定两种可重配方法）；query_first消费者用实际样例返回中的取消/负量行形成随后需求解释；单转发条件全 episode 只有 consumer 发出一次精确 demand v1，仅附固定非业务头部 Original demand document.，其他业务工具保持同样权限与额度。",
        "",
        "| case | 条件 | 程序路线 / 对照 | 决定次数 M/C | 峰值输入 token | 完整职责 | 资格 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in report["controls"]:
        lines.append(
            f"| {r['case_id']} | {r['condition']} | {r['negative_control'] or r['route']} | {r['program_requests']} | {r['maximum_prompt_tokens']} | {r['assessment']['completed']} | {r['passed']} |"
        )
    lines += [
        "",
        "## 反事实与公平性",
        "",
        "首个真实模型格式请求直接比较保存的完整 JSON 字节摘要；配对共用 seed namespace，不删去业务字段，也不把随机世界 ID 的删除当作检验。demand_pair 必须出现来源与最终指标变化；unit_pair 必须出现来源金额/单位变化，正确消费者换算后的最终指标可以相同。",
        "",
    ]
    for p in report["counterfactual_checks"]:
        lines.append(
            f"- {p['case_indices']} / {p['condition']} / {p['route']}：首请求相同={p['first_request_bytes_identical']}；来源产物变化={p['actual_source_product_changed']}；最终指标变化={p['actual_final_metric_changed']}；通过={p['passed']}。"
        )
    for p in report["fairness_checks"]:
        lines.append(
            f"- case {p['case_index']}：业务工具定义相同={p['business_tool_definitions_equal']}；单次合法转发={p['exactly_one_legal_demand_forward']}；两条件均完整可达={p['both_conditions_reachable']}。"
        )
    lines += [
        "",
        "错误逻辑对照只忽略已读取的需求/单位区别，不伪称模型从未见到它；原工具、源数据与执行路径保留。期待独立 checker 拒绝完整职责，不能将该 CPU 对照当成通信有效性或学习收益。未读、伪造产物等底层负例由 `tests/test_reciprocal_data_v026.py` 独立核验。",
        "",
        "## 失败和限制",
        "",
    ]
    failures = [r for r in report["controls"] if not r["negative_control"] and not r["passed"]]
    if not failures:
        lines.append(
            "预定 12 条正向 CPU 路线均在原预算内闭合。这仍不证明当前模型能找到这些路线，也不证明单转发一定劣于自由合作。后续 C1 必须报告两条件真实行为和工作结果。"
        )
    for r in failures:
        lines += [
            f"- {r['case_id']} / {r['condition']} / {r['route']}：原评估 `{json.dumps({k: r['assessment'].get(k) for k in ('eligible', 'reward', 'completed', 'exclusions')}, ensure_ascii=False)}`；停止 `{r['termination']['role_stops']}`。"
        ]
        for failure in r["token_failures"]:
            lines.append(
                f"  - 超限位置：{failure['role']} 第 {failure['decision']} 次 `{failure['action']}`；输入 {failure['prompt_tokens']} + 保留 2048，输出 {failure['program_output_tokens']}。"
            )
    lines += [
        "",
        "见证程序采用公开合法的节省步骤：固定提交查看显式 include_contract=False（完整合同仍在当前公开观察，必要时可显式取回）；consumer在等待上游时先采用自己已读的demand；maintainer不额外转交未用于消费者构建的source_contract，consumer也不额外读取它。消费侧真正使用的是固定m_result里的interface_meta。以上只改变CPU程序动作选择，没有修改模型策略、工具合同或预算。",
    ]
    for batch in report.get("interrupted_development_batches", []):
        lines += [
            "",
            f"中止开发批次：`{batch['path']}`，已完成 {batch['completed_control_rows']} 条；中止原因：{batch['reason']}；不能作为最终资格。",
        ]
    for earlier in report.get("preliminary_attempts", []):
        lines += [
            "",
            f"前置开发记录保留：`{earlier['path']}`，严格门={earlier['passed']}，输入峰={earlier['maximum_prompt_tokens']}。",
        ]
    lines += [
        "",
        f"原始资格目录：`{report['run_directory']}`。各子目录保留请求、公开端口记录、完整不可变 episode、逐调用 token 测量与评分。",
        "",
        "[机器可核对结果](collaboration-v026-qualification.json)",
        "",
    ]
    return "\n".join(lines)


def main(output, tokenizer_path=TOKENIZER, *, selected=None, publish=True):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    tokenizer = None
    if tokenizer_path:
        from transformers import AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
    cases = carrier.registry()["cases"]
    declarations = [
        (i, condition, route, None)
        for i in range(4)
        for condition, route in [
            ("normal", "constraint_first"),
            ("normal", "query_first"),
            ("single_pass", "constraint_first"),
        ]
    ]
    declarations += [
        (1, "normal", "constraint_first", "ignore_demand_distinction"),
        (2, "single_pass", "constraint_first", "ignore_unit_distinction"),
    ]
    if selected is not None:
        declarations = [d for d in declarations if d[0] in selected]
    initial_code = code_identity()
    initial_source_tree = source_identity()["source_tree_sha256"]
    catalog_path = Path("examples/reciprocal-data-v026/catalog.json")
    if json.loads(catalog_path.read_text()) != carrier.registry():
        raise ValueError("Catalog file differs from current frozen registry")
    report = {
        "version": VERSION,
        "run_directory": str(output.resolve()),
        "tokenizer_path": str(Path(tokenizer_path).resolve()) if tokenizer_path else None,
        "model_calls": 0,
        "gpu_calls": 0,
        "parameter_updates": 0,
        "model_training_eligible": False,
        "source_manifest_sha256": digest(carrier.PIN_PATH.read_bytes()),
        "code_identity": initial_code,
        "source_tree_sha256": initial_source_tree,
        "catalog_reference": {
            "path": str(catalog_path.resolve()),
            "sha256": digest(catalog_path.read_bytes()),
        },
        "catalog_sha256": digest(json_bytes(carrier.registry())),
        "limits": {
            "max_context_tokens": 16384,
            "max_output_tokens": 2048,
            "role_decision_limits": {"maintainer": 24, "consumer": 24},
        },
        "cpu_world_workers": 2,
        "preliminary_attempts": [
            {
                "path": str(path.resolve()),
                "sha256": digest(path.read_bytes()),
                "passed": json.loads(path.read_text())["passed"],
                "maximum_prompt_tokens": json.loads(path.read_text())["maximum_prompt_tokens"],
                "token_failures": json.loads(path.read_text())["token_failures"],
            }
            for path in sorted(
                Path("runs/v026-controls/qualification").glob("native-*-check-*/control.json")
            )
        ],
        "interrupted_development_batches": [
            {
                "path": str(path.resolve()),
                "sha256": digest(path.read_bytes()),
                "reason": (
                    "Source/checker changed during batch"
                    if "native-complete-05" in str(path)
                    else "Business completed but terminal staff_done exceeded context; optional unused packet removed in next CPU witness"
                ),
                "completed_control_rows": len(json.loads(path.read_text()).get("controls", [])),
            }
            for path in [
                Path("runs/v026-controls/qualification/native-complete-05/report.json"),
                Path("runs/v026-controls/qualification/native-complete-06/report.json"),
            ]
            if path.exists()
        ],
        "declarations": declarations,
        "controls": [],
        "passed": False,
        "gpu_launch_qualified": False,
    }
    atomic_write(output / "declaration.json", json_bytes(report))

    def execute(declaration):
        index, condition, route, negative = declaration
        name = f"case-{index:02d}-{condition}-{negative or route}"
        row = run_control(
            cases[index],
            output / name,
            tokenizer,
            condition=condition,
            route=route,
            negative=negative,
            seed=202610040000 + 100 * (index // 2),
        )
        return name, row

    # Independent immutable worlds and directories; tokenizer is a read-only
    # official CPU tokenizer shared by two bounded workers, no model weights.
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = {executor.submit(execute, d): i for i, d in enumerate(declarations)}
        ordered = {}
        for future in as_completed(pending):
            name, row = future.result()
            ordered[pending[future]] = row
            report["controls"] = [ordered[i] for i in sorted(ordered)]
            atomic_write(output / "report.json", json_bytes(report))
            print(
                name,
                row["passed"],
                row["assessment"]["reward"],
                row["program_requests"],
                row["maximum_prompt_tokens"],
                flush=True,
            )
    report["counterfactual_checks"] = paired_checks(report["controls"])
    report["fairness_checks"] = fairness_checks(report["controls"])
    negatives = [r for r in report["controls"] if r["negative_control"]]
    report["negative_controls_passed"] = len(negatives) == 2 and all(
        r["assessment"]["eligible"]
        and not r["assessment"]["completed"]
        and not r["token_failures"]
        and not r["tool_refusals"]
        for r in negatives
    )
    report["code_unchanged_during_qualification"] = initial_code == code_identity()
    report["source_tree_unchanged_during_qualification"] = (
        initial_source_tree == source_identity()["source_tree_sha256"]
    )
    positives = [r for r in report["controls"] if not r["negative_control"]]
    report["passed"] = (
        len(positives) == 12
        and all(r["passed"] for r in positives)
        and len(report["counterfactual_checks"]) == 6
        and all(p["passed"] for p in report["counterfactual_checks"])
        and len(report["fairness_checks"]) == 4
        and all(p["passed"] for p in report["fairness_checks"])
        and report["negative_controls_passed"]
        and report["code_unchanged_during_qualification"]
        and report["source_tree_unchanged_during_qualification"]
    )
    report["gpu_launch_qualified"] = report["passed"]
    atomic_write(output / "report.json", json_bytes(report))
    if publish:
        dest = Path("docs/experiments/collaboration-v026-qualification")
        atomic_write(dest.with_suffix(".json"), json_bytes(report))
        dest.with_suffix(".md").write_text(render_markdown(report))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="runs/v026-controls/qualification/"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    )
    parser.add_argument("--tokenizer", default=TOKENIZER)
    parser.add_argument("--case-indices", nargs="+", type=int)
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args()
    result = main(
        args.output, args.tokenizer or None, selected=args.case_indices, publish=not args.no_publish
    )
    raise SystemExit(0 if result["passed"] else 1)
