"""Synthetic bounded report review package; no fabricated historical review."""

import copy

from .public_formats import REPORT_FORMAT

BACKGROUND = "Context retained verbatim: this synthetic report is limited to two stated metrics."


def fixtures(*, incomplete=False):
    return {
        "period": "2026H1",
        "metrics": {
            "revenue": {"value": 120, "previous": 100},
            "cost": {"value": None if incomplete else 70, "previous": 80},
        },
    }


def check_spec(alias="dataset"):
    return {
        "kind": "research_report",
        "path": ["report"],
        "sources": [{"alias": alias, "reference_path": ["sources", alias]}],
        "claims": [
            {
                "claim_id": metric,
                "section_id": metric,
                "label": metric.title(),
                "source_alias": alias,
                "value_path": ["metrics", metric, "value"],
                "previous_path": ["metrics", metric, "previous"],
                "period_path": ["period"],
            }
            for metric in ("revenue", "cost")
        ],
    }


def contract(spec=None):
    return {
        "min_files": 1,
        "max_files": 2,
        "allowed_kinds": ["json"],
        "allowed_roles": ["report"],
        "required_fields": ["report", "sources"],
        "content_checks": [copy.deepcopy(spec or check_spec())],
    }


def package(
    project_id="REPORT",
    *,
    author="author",
    reviewer="reviewer",
    source_alias="dataset",
    incomplete=False,
):
    return {
        "project_id": project_id,
        "goal": "Review actual finite report assertions and repair only the affected sections",
        "participants": [author, reviewer],
        "objects": [
            {
                "alias": source_alias,
                "filename": source_alias + ".json",
                "owner": reviewer,
                "readers": [author, reviewer],
                "kind": "json",
                "data": fixtures(incomplete=incomplete),
            },
            {
                "alias": "report",
                "filename": "report.json",
                "owner": author,
                "readers": [author, reviewer],
                "kind": "json",
                "deliverable_role": "report",
                "data": {
                    "report": {
                        "sections": [{"section_id": "context", "body": BACKGROUND, "claims": []}]
                    }
                },
            },
        ],
        "works": [
            {
                "work_id": "research",
                "owner": author,
                "approval_policy": "review",
                "goal": "Reconcile body and evidence before approval",
                "requirements": {"input_policy": "fixed", "input_version": "v1",
                                 "public_format": copy.deepcopy(REPORT_FORMAT)},
                "deliverable_contract": contract(check_spec(source_alias)),
            }
        ],
        "grants": [
            {"actor_id": author, "power": power, "subject": "artifact", "work_nodes": ["research"]}
            for power in ("adopt", "create_object")
        ]
        + [
            {
                "actor_id": reviewer,
                "power": power,
                "subject": "deliverable",
                "work_nodes": ["research"],
            }
            for power in ("review", "approve")
        ],
        "provenance": {
            "kind": "synthetic",
            "source_evidence_refs": [],
            "note": "Synthetic finite report and public metric material",
        },
    }
