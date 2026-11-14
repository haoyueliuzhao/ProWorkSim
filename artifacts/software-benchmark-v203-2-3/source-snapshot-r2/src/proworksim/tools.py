"""Model-visible tool schemas. Identity and evaluator access are not arguments."""


def _tool(name, description, properties=None, required=()):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": list(required),
                "additionalProperties": False,
            },
        },
    }


TEXT = {"type": "string"}
REFS = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"artifact_id": TEXT, "version_id": TEXT},
        "required": ["artifact_id", "version_id"],
        "additionalProperties": False,
    },
}
TOOLS = [
    _tool("list_files", "List accessible artifact IDs, current versions and possible staleness."),
    _tool(
        "search",
        "Search accessible current files and visible mail; returns snippets.",
        {"query": TEXT},
        ["query"],
    ),
    _tool(
        "read_file",
        "Read actual text/JSON content; XLSX uses sheet_read.",
        {"artifact_id": TEXT, "version_id": TEXT},
        ["artifact_id"],
    ),
    _tool(
        "file_history",
        "List accessible version metadata and input dependencies.",
        {"artifact_id": TEXT},
        ["artifact_id"],
    ),
    _tool(
        "write_file",
        "Write actual text to an owned artifact and create a version.",
        {"artifact_id": TEXT, "content": TEXT, "dependencies": REFS},
        ["artifact_id", "content"],
    ),
    _tool(
        "sheet_read",
        "Read XLSX formulas and evaluated values. Omit sheet to read all sheets.",
        {"artifact_id": TEXT, "sheet": TEXT, "version_id": TEXT},
    ),
    _tool(
        "sheet_update",
        "Edit XLSX cells using Sheet!A1 keys, recalculate and persist a new version."
        " Unknown sheet names create new sheets; errors remain in the workbook.",
        {
            "artifact_id": TEXT,
            "cells": {
                "type": "object",
                "additionalProperties": {"type": ["string", "number", "null"]},
            },
            "dependencies": REFS,
        },
        ["cells"],
    ),
    _tool(
        "sheet_recalculate",
        "Recalculate the actual XLSX; unsupported formulas report errors.",
        {"artifact_id": TEXT},
    ),
    _tool(
        "calculate",
        "Evaluate bounded numeric expressions (+ - * / **, SUM MIN MAX ABS ROUND). No filesystem or imports.",
        {
            "expression": TEXT,
            "variables": {"type": "object", "additionalProperties": {"type": "number"}},
        },
        ["expression"],
    ),
    _tool("mail_list", "List headers of accessible messages. Listing does not mark messages read."),
    _tool(
        "mail_read",
        "Read a visible message including versioned attachments.",
        {"message_id": TEXT},
        ["message_id"],
    ),
    _tool(
        "mail_send",
        "Send a request bound to work_item_id and optional blocker_id. scope uses manager, audience uses client. Replies can be old/unavailable; existing applicable basis may be reused without asking.",
        {
            "to": TEXT,
            "body": TEXT,
            "topic": TEXT,
            "attachments": REFS,
            "work_item_id": TEXT,
            "blocker_id": TEXT,
        },
        ["to", "body"],
    ),
    _tool(
        "work_list",
        "Read current work obligations, status, versioned submissions and business feedback.",
    ),
    _tool(
        "block_work",
        "Record a concrete blocker and notify the simulated manager.",
        {
            "work_item_id": TEXT,
            "reason": TEXT,
            "kind": {"type": "string", "enum": ["scope", "audience", "evidence"]},
            "requested_role": TEXT,
            "required_scope_version": {"type": "integer", "minimum": 1},
            "request_id": TEXT,
        },
        ["work_item_id", "reason"],
    ),
    _tool(
        "submit",
        "Submit current required artifact versions or a structured answer for business review.",
        {"work_item_id": TEXT, "answer": {"type": "object"}},
        ["work_item_id"],
    ),
    _tool(
        "withdraw",
        "Withdraw your own pending submission; preserves files and history, then permits resubmission.",
        {"work_item_id": TEXT, "submission_id": TEXT, "reason": TEXT},
        ["work_item_id", "submission_id", "reason"],
    ),
    _tool(
        "wait",
        "Advance discrete project time to receive replies/reviews/events. A tick is not a work hour.",
        {"ticks": {"type": "integer", "minimum": 1, "maximum": 100}},
    ),
]
