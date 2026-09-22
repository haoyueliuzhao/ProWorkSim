"""Transparent rule-based feasibility witness. Uses ONLY the worker tool surface.

This is not an LLM experiment and its actions are not eligible target-model SFT.
"""

import json

from .audience import witness_audience_content


def _call(session, action, **kwargs):
    result = session.call(action, **kwargs)
    if not result["ok"]:
        raise RuntimeError(f"Baseline tool failure: {action}: {result['error']}")
    return result["result"]


def _scope(session, work):
    reference = work.get("required_basis")
    if reference:
        result = session.call("read_file", artifact_id="basis", version_id=reference["version_id"])
        if result["ok"]:
            basis = json.loads(result["result"]["content"])
            if basis["requirement_version"] == work.get(
                "basis_requirement_version", work["requirement_version"]
            ):
                return {**basis, "approved_basis": reference}
    blocker = _call(
        session,
        "block_work",
        work_item_id=work["work_item_id"],
        kind="scope",
        requested_role="manager",
        required_scope_version=work.get("basis_requirement_version", work["requirement_version"]),
        reason="缺少适用于本工作版本的批准依据",
    )
    _call(
        session,
        "mail_send",
        to="manager",
        topic="scope",
        work_item_id=work["work_item_id"],
        blocker_id=blocker["blocker_id"],
        body="请提供适用于本工作和需求版本的批准依据凭据。",
    )
    _call(session, "wait", ticks=2)
    current = next(
        w for w in _call(session, "work_list") if w["work_item_id"] == work["work_item_id"]
    )
    if not current.get("is_current", True) or current["status"] == "blocked":
        return None
    reference = current.get("required_basis")
    if reference:
        result = _call(
            session, "read_file", artifact_id="basis", version_id=reference["version_id"]
        )
        return {**json.loads(result["content"]), "approved_basis": reference}
    return None


def sensitivity_formulas(assumptions, guide=None):
    guide = guide or {
        "layout": {"input_sheet": "Inputs", "sensitivity_sheet": "Sensitivity"},
        "input_cells": {
            "revenue": "B2",
            "operating_margin": "B3",
            "tax_rate": "B6",
            "earnings_multiple": "B7",
            "net_debt": "B8",
            "shares": "B9",
        },
    }
    layout = guide.get("layout", {})
    sheet = layout.get("sensitivity_sheet", "Sensitivity")

    def ref(name):
        return f"{layout.get('input_sheet', 'Inputs')}!{guide['input_cells'][name]}"

    cells = {f"{sheet}!A1": "margin_delta / growth"}
    for col, growth in zip("BC", assumptions["growth_grid"]):
        cells[f"{sheet}!{col}1"] = growth
        for row, delta in zip((2, 3), assumptions["margin_delta_grid"]):
            cells[f"{sheet}!A{row}"] = delta
            cells[f"{sheet}!{col}{row}"] = (
                f"=({ref('revenue')}*(1+{col}$1)*({ref('operating_margin')}+$A{row})"
                f"*(1-{ref('tax_rate')})*{ref('earnings_multiple')}-{ref('net_debt')})/{ref('shares')}"
            )
    return cells


def run_baseline(session, inject_stale_memo=False, max_rounds=32):
    _call(session, "list_files")
    guide = json.loads(_call(session, "read_file", artifact_id="guide")["content"])
    layout = guide.get("layout", {})
    input_sheet = layout.get("input_sheet", "Inputs")
    output_sheet = layout.get("output_sheet", "Outputs")
    sensitivity_sheet = layout.get("sensitivity_sheet", "Sensitivity")
    injected = False
    for _ in range(max_rounds):
        observation = session.observe()
        if observation.get("terminal_reason"):
            return {
                "provider": "rule_based",
                "complete": False,
                "reason": observation["terminal_reason"],
            }
        if observation["complete"]:
            return {
                "provider": "rule_based",
                "complete": True,
                "logical_time": observation["logical_time"],
            }
        work = next(
            (
                w
                for w in _call(session, "work_list")
                if w["status"]
                not in ("accepted", "in_review", "superseded", "cancelled", "waiting_dependencies")
                and w.get("is_current", True)
            ),
            None,
        )
        if work is None:
            _call(session, "wait", ticks=2)
            continue
        source = _call(session, "read_file", artifact_id="financials")
        facts = json.loads(source["content"])["values"]
        if work["deliverables"] == ["answer"]:
            model = _call(session, "sheet_read")
            price = model["sheets"][output_sheet][guide["output_cells"]["share_price"]]["value"]
            pe = _call(
                session,
                "calculate",
                expression="ROUND(price / eps, 2)",
                variables={"price": price, "eps": facts["diluted_eps"]},
            )["value"]
            _call(
                session,
                "submit",
                work_item_id=work["work_item_id"],
                answer={
                    "pe": pe,
                    "citations": [
                        {
                            "artifact_id": "model",
                            "version_id": model["version_id"],
                            "location": f"{output_sheet}!{guide['output_cells']['share_price']}",
                        },
                        {
                            "artifact_id": "financials",
                            "version_id": source["version_id"],
                            "location": "values.diluted_eps",
                        },
                    ],
                },
            )
        else:
            assumptions = None
            mandate = None
            if "model" in work["deliverables"] or "memo" in work["deliverables"]:
                mandate = _scope(session, work)
                if mandate is None:
                    continue
                assumptions = mandate["assumptions"]
            if "model" in work["deliverables"]:
                _call(session, "sheet_read")
                cells = {
                    f"{input_sheet}!{address}": {**facts, **assumptions}[name]
                    for name, address in guide["input_cells"].items()
                }
                cells.update(sensitivity_formulas(assumptions, guide))
                _call(
                    session,
                    "sheet_update",
                    cells=cells,
                    dependencies=[
                        {"artifact_id": "financials", "version_id": source["version_id"]},
                        mandate["approved_basis"],
                    ],
                )
            model = _call(session, "sheet_read")
            current = next(
                w for w in _call(session, "work_list") if w["work_item_id"] == work["work_item_id"]
            )
            if not current.get("is_current", True):
                continue
            if "memo" in work["deliverables"]:
                _call(session, "read_file", artifact_id="memo")
                if inject_stale_memo and not injected:
                    injected = True
                else:
                    memo = {
                        "period": facts["period"],
                        "metrics": {
                            name: model["sheets"][output_sheet][address]["value"]
                            for name, address in guide["output_cells"].items()
                        },
                        "source_versions": {
                            "financials": source["version_id"],
                            "model": model["version_id"],
                        },
                        "citations": [
                            {
                                "artifact_id": "financials",
                                "version_id": source["version_id"],
                                "location": "values.revenue",
                            },
                            {
                                "artifact_id": "financials",
                                "version_id": source["version_id"],
                                "location": "values.operating_margin",
                            },
                            {
                                "artifact_id": "model",
                                "version_id": model["version_id"],
                                "location": f"{output_sheet}!{guide['output_cells']['share_price']}",
                            },
                        ],
                        "explanation": (
                            f"本模型使用 {facts['period']} 合成披露，情景增长率 {assumptions['growth']:.1%}、"
                            f"利润率增量 {assumptions['margin_delta']:.1%} 为获批假设，并非历史事实。"
                            "在其余输入不变时，提高增长或利润率会提高测算股价。"
                            "该结果不代表真实企业估值结论，未来实现程度存在不确定性。"
                        ),
                    }
                    _call(
                        session,
                        "write_file",
                        artifact_id="memo",
                        content=json.dumps(memo, ensure_ascii=False),
                        dependencies=[
                            {"artifact_id": k, "version_id": v}
                            for k, v in memo["source_versions"].items()
                        ],
                    )
            if "note" in work["deliverables"]:
                brief = _call(session, "read_file", artifact_id="brief")
                note = {
                    "audience": json.loads(brief["content"])["audience"],
                    "audience_content": witness_audience_content(
                        json.loads(brief["content"])["audience"]
                    ),
                    "share_price": model["sheets"][output_sheet][
                        guide["output_cells"]["share_price"]
                    ]["value"],
                    "sensitivity": {
                        f"{col}{row}": model["sheets"][sensitivity_sheet][f"{col}{row}"]["value"]
                        for col in "BC"
                        for row in (2, 3)
                    },
                    "source_versions": {"model": model["version_id"], "brief": brief["version_id"]},
                    "explanation": "这是依照当前受众要求编写的合成情景说明，增长和利润率参数均是假设，不构成事实预测。",
                }
                _call(
                    session,
                    "write_file",
                    artifact_id="note",
                    content=json.dumps(note, ensure_ascii=False),
                    dependencies=[
                        {"artifact_id": k, "version_id": v}
                        for k, v in note["source_versions"].items()
                    ],
                )
            _call(session, "submit", work_item_id=work["work_item_id"])
        _call(session, "wait", ticks=2)
    return {"provider": "rule_based", "complete": False, "reason": "round_budget"}
