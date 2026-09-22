"""Fixed environment staff policies with limited, public business checks.

The reviewer uses visible artifacts, never hidden synthesis facts or evaluator specs.
Business acceptance and independent correctness are intentionally separate signals.
"""

import json
import math

from .compiler import OUTPUT_CELLS
from .layouts import SemanticSpreadsheet, LayoutMap


def review_submission(read_version, submission: dict, item: dict, layout=None) -> list[str]:
    defects = []
    if item["deliverables"] == ["answer"]:
        answer = submission.get("answer")
        if not isinstance(answer, dict) or type(answer.get("pe")) not in (int, float):
            defects.append("请提交包含数值 pe 和指定来源引用 citations 的结构化回复。")
        elif not answer.get("citations"):
            defects.append("请补充隐含股价与披露 EPS 的来源、版本和位置。")
        return defects
    try:
        model_version = submission["artifact_versions"].get(
            "model", submission["context_versions"]["model"]
        )
        model = SemanticSpreadsheet(
            read_version("model", model_version), LayoutMap(**(layout or {"layout_id": "standard"}))
        )
        cells = model.read()
        errors = [
            f"{sheet}!{cell}"
            for sheet, values in cells.items()
            for cell, value in values.items()
            if "error" in value
        ]
        if errors:
            defects.append("工作簿有不可计算的公式：" + ", ".join(errors[:8]))
        if model.layout.sensitivity_sheet not in cells:
            defects.append("缺少要求的 Sensitivity 敏感性分析表。")
        if "memo" in item["deliverables"]:
            memo = json.loads(read_version("memo", submission["artifact_versions"]["memo"]))
            if memo.get("source_versions", {}).get("model") != model_version:
                defects.append("备忘录仍引用旧模型版本，请同步本次提交的 model 版本。")
            for name, address in OUTPUT_CELLS.items():
                observed = memo.get("metrics", {}).get(name)
                actual = model.value(f"Outputs!{address}")
                if type(observed) not in (int, float) or not math.isclose(
                    observed, actual, rel_tol=1e-6
                ):
                    defects.append(f"备忘录指标 {name} 与所提交工作簿不一致，请重算后同步。")
            if not memo.get("explanation"):
                defects.append("请说明情景假设及变化原因。")
        if "note" in item["deliverables"]:
            note = json.loads(read_version("note", submission["artifact_versions"]["note"]))
            if note.get("source_versions", {}).get("model") != model_version:
                defects.append("情景说明仍引用旧模型版本。")
            if not math.isclose(
                float(note.get("share_price", float("nan"))),
                model.value("Outputs!B6"),
                rel_tol=1e-6,
            ):
                defects.append("情景说明的股价与提交模型不一致。")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        defects.append(f"交付文件无法完成审阅：{exc}")
    return defects
