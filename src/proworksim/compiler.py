"""Compile shared project history and a task overlay into real files and state."""

import io
import uuid
from dataclasses import asdict
from pathlib import Path

from openpyxl import Workbook

from .contracts import CONTRACT_VERSION, ArtifactContract, artifact_contracts, citation_contract
from .layouts import SemanticSpreadsheet, layout_for
from .basis import issue_basis
from .audience import audience_requirement, public_audience_requirements
from .renderers.xlsx import relocate
from .workflow import configure, activate_ready, validate_workflow, make_workflow
from .lifecycle import validate_lifecycle_policies
from .schema import SCHEMA_VERSION, WorkItem, WorldSpec
from .spreadsheet import Spreadsheet
from .storage import Store, atomic_write, json_bytes

INPUT_CELLS = {
    "revenue": "B2",
    "operating_margin": "B3",
    "growth": "B4",
    "margin_delta": "B5",
    "tax_rate": "B6",
    "earnings_multiple": "B7",
    "net_debt": "B8",
    "shares": "B9",
}
OUTPUT_CELLS = {
    "forecast_revenue": "B2",
    "operating_profit": "B3",
    "net_income": "B4",
    "equity_value": "B5",
    "share_price": "B6",
    "model_eps": "B7",
    "model_pe": "B8",
}
BASE_FORMULAS = {
    "B2": "=Inputs!B2*(1+Inputs!B4)",
    "B3": "=B2*(Inputs!B3+Inputs!B5)",
    "B4": "=B3*(1-Inputs!B6)",
    "B5": "=B4*Inputs!B7-Inputs!B8",
    "B6": "=B5/Inputs!B9",
    "B7": "=B4/Inputs!B9",
    "B8": "=B6/B7",
}


def disclosure(spec: dict, stage: str, released_at: int) -> dict:
    fact = spec["facts"][stage]
    return {
        "source_id": "financials",
        "source_type": "synthetic_disclosure",
        "synthetic": True,
        "company": spec["project"]["company"],
        "period": fact["period"],
        "public_available_at": released_at,
        "unit": "USD million, except diluted_eps (USD/share) and margins (fraction)",
        "definition": "reported operating profit / reported revenue; diluted EPS as disclosed",
        "values": fact,
        "locations": {k: f"values.{k}" for k in fact},
    }


def scope(spec: dict, revision: int = 1) -> dict:
    assumptions = dict(spec["assumptions"])
    if revision > 1:
        assumptions["growth"] = round(assumptions["growth"] + 0.02, 4)
    return {
        "requirement_version": revision,
        "assumptions": assumptions,
        "assumption_status": "approved_synthetic_scenario_not_historical_fact",
        "source_period": spec["facts"]["current" if revision == 1 else "future"]["period"],
    }


def work_item(spec: dict, revision: int, origin: str) -> dict:
    project = spec["project"]
    delivery = project["delivery"]
    requirements = ["资料均为合成材料。按指定来源、期间、单位和版本工作；请先阅读 guide。"]
    if delivery == "short":
        goal = (
            "用已有模型 Outputs!B6 的隐含股价除以最新版披露的 diluted_eps，回复 P/E（两位小数）。"
        )
        requirements += [
            "只需结构化回复 {pe: 数值, citations: [...]}；不要改写模型。",
            "citations 每项包含 artifact_id、version_id、location。",
        ]
        deliverables = ["answer"]
    else:
        goal = "更新已有经营估值模型，按确认口径制作增长率×利润率增量的 2×2 股价敏感性表。"
        requirements += [
            "从 financials 获取本期收入和经营利润率，从历史邮件或负责人澄清获取 scope。",
            "更新 model 的 Inputs 并保留可重算公式；Sensitivity!B2:C3 为股价结果公式。",
            "Sensitivity!B1:C1 为 growth_grid，A2:A3 为 margin_delta_grid；所有结果引用模型输入。",
            "写入时用 dependencies 记录 financials 和适用的 basis 版本；有可用确认可直接采用，不必重复请求。",
        ]
        deliverables = ["model"]
        if delivery == "continuous":
            goal += " 同步备忘录并完成项目后续修订。"
            requirements += [
                "memo 是 JSON 备忘录；schema 见 guide。更新关键指标、情景解释、证据引用。",
                "memo 的 source_versions 必须绑定 financials 和 model 的实际版本。",
                "接受第一轮后会收到修订披露与假设变化；继续处理新产生的工作义务。",
            ]
            deliverables.append("memo")
    layout = layout_for(spec)
    goal = goal.replace("Outputs!B6", layout.address("Outputs!B6"))
    requirements = [
        r.replace("Sensitivity", layout.sensitivity_sheet).replace("Inputs", layout.input_sheet)
        for r in requirements
    ]
    return asdict(
        WorkItem(
            project_id=project["project_id"],
            work_item_id=f"work-{revision}",
            origin_event=origin,
            owner_role="analyst",
            goal=goal,
            visible_requirements=requirements,
            inputs=["financials", "model", "guide"],
            dependencies=[f"work-{revision - 1}"] if revision > 1 else [],
            deliverables=deliverables,
            acceptance_spec_ref=f"finance-v0.1/requirement-{revision}",
            requirement_version=revision,
        )
    )


def create_workbook(spec: dict) -> bytes:
    book = Workbook()
    inputs = book.active
    inputs.title = "Inputs"
    outputs = book.create_sheet("Outputs")
    inputs.append(["Input (USD million / fraction)", "Value"])
    initial = {**spec["facts"]["old"], **spec["assumptions"], "growth": 0.02, "margin_delta": 0}
    for name, cell in INPUT_CELLS.items():
        inputs[f"A{cell[1:]}"] = name
        inputs[cell] = initial[name]
    for name, cell in OUTPUT_CELLS.items():
        outputs[f"A{cell[1:]}"] = name
        outputs[cell] = BASE_FORMULAS[cell]
    for sheet in book:
        sheet.column_dimensions["A"].width = 36
        sheet.column_dimensions["B"].width = 22
        sheet.freeze_panes = "B2"
    book = relocate(book, layout_for(spec))
    stream = io.BytesIO()
    book.save(stream)
    return Spreadsheet(stream.getvalue()).serialize()


def compile_world(spec: WorldSpec, destination: str | Path) -> Path:
    workflow = spec.workflow or make_workflow(spec.project.delivery).public_spec()
    validate_workflow(workflow)
    validate_lifecycle_policies(spec.lifecycle_events, workflow)
    root = Path(destination).resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"Destination must be empty: {root}")
    store = Store(root)
    store.control.mkdir(parents=True, exist_ok=True)
    store.workspace.mkdir(parents=True, exist_ok=True)
    raw_spec = spec.to_dict()
    raw_spec["contract_version"] = CONTRACT_VERSION
    layout = layout_for(raw_spec)
    state = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "artifact_contracts": artifact_contracts(),
        "instance_id": uuid.uuid4().hex,
        "branch_id": uuid.uuid4().hex,
        "parent_branch_id": None,
        "clock": -5,
        "project": raw_spec["project"],
        "roles": raw_spec["roles"],
        "artifacts": {},
        "messages": [],
        "events": [],
        "event_history": [],
        "work_items": {},
        "interactions": [],
        "evaluations": [],
        "calls": [],
        "blockers": {},
        "requests": {},
        "work_replacements": {},
        "basis_by_scenario": {},
        "basis_approvals": [],
        "lifecycle_events": raw_spec.get("lifecycle_events", []),
        "unavailable_topics": raw_spec.get("unavailable_topics", []),
        "knowledge": {r.role_id: {"read_artifacts": [], "read_messages": []} for r in spec.roles},
        "staff_policies": {r.role_id: r.policy for r in spec.roles if not r.trainable},
    }

    configure(state, raw_spec)
    state["layout"] = layout.public()

    def add(artifact_id, filename, data, owner="analyst", readers=None, deps=None):
        state["artifacts"][artifact_id] = {
            "artifact_id": artifact_id,
            "filename": filename,
            "owner": owner,
            "readers": readers or list(dict.fromkeys([owner, "analyst", "manager", "reviewer"])),
            "writers": [owner],
            "current_version": None,
            "versions": {},
            "possibly_stale": False,
        }
        store.put(state, artifact_id, data, owner, deps)

    add(
        "financials",
        "evidence/financials.json",
        json_bytes(disclosure(raw_spec, "old", -5)),
        "client",
    )
    state["artifacts"]["basis"] = {
        "artifact_id": "basis",
        "filename": "approvals/analytical_basis.json",
        "owner": "manager",
        "readers": ["manager", "reviewer"],
        "writers": [],
        "versions": {},
        "version_readers": {},
        "current_version": None,
        "possibly_stale": False,
    }
    issue_basis(
        store,
        state,
        {**spec.assumptions, "growth": 0.02, "margin_delta": 0},
        spec.facts["old"]["period"],
        0,
        ["historical"],
        0,
        public=True,
    )
    add(
        "model",
        "artifacts/operating_model.xlsx",
        create_workbook(raw_spec),
        deps=[
            {"artifact_id": "financials", "version_id": "v1"},
            {"artifact_id": "basis", "version_id": "v1"},
        ],
    )
    initial_sheet = SemanticSpreadsheet(store.content(state["artifacts"]["model"]), layout)
    add(
        "memo",
        "artifacts/research_memo.json",
        json_bytes(
            {
                "period": spec.facts["old"]["period"],
                "metrics": {
                    k: initial_sheet.value(f"Outputs!{v}") for k, v in OUTPUT_CELLS.items()
                },
                "source_versions": {"financials": "v1", "model": "v1"},
                "citations": [
                    {"artifact_id": "financials", "version_id": "v1", "location": "values.revenue"}
                ],
                "explanation": "合成旧研究；情景假设不代表已发生事实。",
            }
        ),
        deps=[
            {"artifact_id": "model", "version_id": "v1"},
            {"artifact_id": "financials", "version_id": "v1"},
        ],
    )
    add(
        "scope",
        "private/manager_scope.json",
        json_bytes(scope(raw_spec)),
        "manager",
        readers=["manager", "reviewer"],
    )
    if any("note" in node["deliverables"] for node in state["workflow"]["nodes"]):
        state["artifact_contracts"]["note"] = ArtifactContract(
            "note", ("model", "brief"), "source_versions"
        ).public()
        add(
            "brief",
            "policies/audience_brief.json",
            json_bytes(
                {
                    "audience": "internal_management",
                    "synthetic": True,
                    "audience_requirement": audience_requirement("internal_management").public(),
                }
            ),
            "client",
        )
        add(
            "note",
            "artifacts/scenario_note.json",
            json_bytes(
                {
                    "audience": "internal_management",
                    "share_price": initial_sheet.value("Outputs!B6"),
                    "sensitivity": {},
                    "source_versions": {"model": "v1", "brief": "v1"},
                    "explanation": "旧情景说明，尚待更新。",
                }
            ),
            deps=[
                {"artifact_id": "model", "version_id": "v1"},
                {"artifact_id": "brief", "version_id": "v1"},
            ],
        )
    guide = {
        "synthetic": True,
        "layout": layout.public(),
        "input_cells": {
            k: layout.address(f"Inputs!{v}").split("!")[1] for k, v in INPUT_CELLS.items()
        },
        "output_cells": {
            k: layout.address(f"Outputs!{v}").split("!")[1] for k, v in OUTPUT_CELLS.items()
        },
        "sensitivity": {
            "columns": "B1:C1 = growth_grid",
            "rows": "A2:A3 = margin_delta_grid",
            "results": "B2:C3 = share_price under the corresponding row/column assumptions",
        },
        "citation_requirements": {
            kind: citation_contract(
                kind, [layout.address(f"Outputs!{v}") for v in OUTPUT_CELLS.values()]
            ).public()
            for kind in ("short", "memo")
        },
        "artifact_contracts": state["artifact_contracts"],
        "audience_requirements": public_audience_requirements(),
        "approved_basis": {
            "artifact_id": "basis",
            "adoption": "model dependencies must explicitly bind the approved version applicable to this work and requirement",
            "discovery": "Read an available confirmation; ask manager only if unavailable or inapplicable. scope is private.",
        },
        "note_schema": {
            "audience": "current brief audience",
            "share_price": "model share_price",
            "sensitivity": "mapping B2,C2,B3,C3 to current model sensitivity values",
            "source_versions": {"model": "version_id", "brief": "version_id"},
            "explanation": "describe audience and scenario assumptions",
            "audience_content": "required fields in current brief.audience_requirement",
        },
        "memo_schema": {
            "period": "source period",
            "metrics": "all output_cells metrics",
            "source_versions": {"financials": "version_id", "model": "version_id"},
            "citations": [
                {
                    "artifact_id": "financials",
                    "version_id": "version_id",
                    "location": " or ".join(
                        loc for aid, loc in citation_contract("memo").required_any_of
                    ),
                }
            ],
            "explanation": "explain assumptions, direction of changes and uncertainty",
        },
        "tools": "Use artifact IDs, not filesystem paths. read_file for text, sheet_read for XLSX.",
        "formula_subset": "Arithmetic + - * / ^, sheet references, SUM MIN MAX ABS ROUND, ranges.",
        "communications": "mail_send(to='manager', topic='scope', work_item_id=..., blocker_id=..., body=...) requests a work/version-bound confirmation. Replies can be old or unavailable; verify applicability.",
        "submission": "submit(work_item_id, answer={...}) pins required artifact versions; wait for review.",
    }
    add("guide", "policies/working_guide.json", json_bytes(guide), "manager")
    state["clock"] = 0
    store.put(state, "financials", json_bytes(disclosure(raw_spec, "current", 0)), "client")
    current_basis = None
    if "scope" not in state["unavailable_topics"]:
        current_basis = issue_basis(
            store,
            state,
            spec.assumptions,
            spec.facts["current"]["period"],
            1,
            [n["node_id"] for n in state["workflow"]["nodes"] if n["scenario_revision"] == 1],
            1,
            public=spec.project.information_access == "mail",
        )
    activate_ready(state, raw_spec, "disclosure-arrival-1")
    for rule in state["workflow"]["event_rules"]:
        if not rule["after_accepted"]:
            state["fired_rules"].append(rule["rule_id"])
            state["events"].append(
                {
                    "event_id": uuid.uuid4().hex,
                    "kind": "apply_rule",
                    "at": state["clock"] + rule["delay"],
                    "payload": {"rule_id": rule["rule_id"]},
                }
            )
    state["event_history"].append(
        {
            "event_id": "disclosure-arrival-1",
            "kind": "disclosure",
            "at": 0,
            "artifact_id": "financials",
            "version_id": "v2",
        }
    )
    state["messages"].append(
        {
            "message_id": "mail-1",
            "sender": "manager",
            "recipients": ["analyst"],
            "at": 0,
            "subject": "项目交接",
            "body": "请处理当前工作列表，阅读 guide 和历史材料。需要口径时可联系负责人。",
            "attachments": [{"artifact_id": "financials", "version_id": "v2"}],
        }
    )
    if spec.project.information_access == "mail" and current_basis:
        state["messages"].append(
            {
                "message_id": "mail-2",
                "sender": "manager",
                "recipients": ["analyst", "reviewer"],
                "at": 0,
                "subject": "已确认的 scope / 情景假设",
                "body": {
                    **current_basis,
                    "approved_basis": {
                        "artifact_id": "basis",
                        "version_id": current_basis["version_id"],
                    },
                },
                "attachments": [
                    {"artifact_id": "basis", "version_id": current_basis["version_id"]}
                ],
            }
        )
    atomic_write(store.control / "spec.json", json_bytes(raw_spec))
    store.save(state)
    return root
