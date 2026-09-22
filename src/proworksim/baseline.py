"""Transparent rule-based feasibility witness. Uses ONLY the worker tool surface.

This is not an LLM experiment and its actions are not eligible target-model SFT.
"""

import json


def _call(session, action, **kwargs):
    result = session.call(action, **kwargs)
    if not result["ok"]:
        raise RuntimeError(f"Baseline tool failure: {action}: {result['error']}")
    return result["result"]


def _scope(session, revision):
    headers = _call(session, "mail_list")
    for header in reversed(headers):
        message = _call(session, "mail_read", message_id=header["message_id"])
        body = message["body"]
        if (
            isinstance(body, dict)
            and body.get("requirement_version") == revision
            and "assumptions" in body
        ):
            return body
    _call(session, "mail_send", to="manager", topic="scope", body="请确认当前期间和情景假设。")
    _call(session, "wait", ticks=2)
    headers = _call(session, "mail_list")
    for header in reversed(headers):
        body = _call(session, "mail_read", message_id=header["message_id"])["body"]
        if (
            isinstance(body, dict)
            and body.get("requirement_version") == revision
            and "assumptions" in body
        ):
            return body
    raise RuntimeError("No feasible scope response")


def sensitivity_formulas(assumptions):
    cells = {"Sensitivity!A1": "margin_delta / growth"}
    for col, growth in zip("BC", assumptions["growth_grid"]):
        cells[f"Sensitivity!{col}1"] = growth
        for row, delta in zip((2, 3), assumptions["margin_delta_grid"]):
            cells[f"Sensitivity!A{row}"] = delta
            cells[f"Sensitivity!{col}{row}"] = (
                f"=(Inputs!B2*(1+{col}$1)*(Inputs!B3+$A{row})*(1-Inputs!B6)"
                "*Inputs!B7-Inputs!B8)/Inputs!B9"
            )
    return cells


def run_baseline(session, inject_stale_memo=False, max_rounds=12):
    _call(session, "list_files")
    guide = json.loads(_call(session, "read_file", artifact_id="guide")["content"])
    injected = False
    for _ in range(max_rounds):
        observation = session.observe()
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
                if w["status"] not in ("accepted", "in_review")
            ),
            None,
        )
        if work is None:
            _call(session, "wait", ticks=2)
            continue
        revision = work["requirement_version"]
        source = _call(session, "read_file", artifact_id="financials")
        facts = json.loads(source["content"])["values"]
        if work["deliverables"] == ["answer"]:
            model = _call(session, "sheet_read")
            price = model["sheets"]["Outputs"]["B6"]["value"]
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
                            "location": "Outputs!B6",
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
            mandate = _scope(session, revision)
            assumptions = mandate["assumptions"]
            _call(session, "sheet_read")
            cells = {
                f"Inputs!{address}": {**facts, **assumptions}[name]
                for name, address in guide["input_cells"].items()
            }
            cells.update(sensitivity_formulas(assumptions))
            _call(
                session,
                "sheet_update",
                cells=cells,
                dependencies=[{"artifact_id": "financials", "version_id": source["version_id"]}],
            )
            model = _call(session, "sheet_read")
            if "memo" in work["deliverables"]:
                _call(session, "read_file", artifact_id="memo")
                if inject_stale_memo and not injected:
                    injected = True
                else:
                    memo = {
                        "period": facts["period"],
                        "metrics": {
                            name: model["sheets"]["Outputs"][address]["value"]
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
                                "location": "Outputs!B6",
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
            _call(session, "submit", work_item_id=work["work_item_id"])
        _call(session, "wait", ticks=2)
    return {"provider": "rule_based", "complete": False, "reason": "round_budget"}
