"""Finite file capabilities used by WorldCore, with no authority or world state.

The existing bounded Spreadsheet evaluates the supported formula subset. ZIP
metadata is canonicalized here so replaying the same XLSX action writes exactly
identical bytes; legacy template serialization is deliberately unaffected.
"""

import copy
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from openpyxl import Workbook

from ..spreadsheet import Spreadsheet
from ..storage import json_bytes


@dataclass(frozen=True)
class Capability:
    kind: str
    application: str
    suffix: str


_CAPABILITIES = {
    "json": Capability("json", "files", ".json"),
    "xlsx": Capability("xlsx", "spreadsheets", ".xlsx"),
}


def capability_for(kind):
    try:
        return _CAPABILITIES[kind]
    except (KeyError, TypeError) as exc:
        raise ValueError("Supported file capabilities are json and xlsx") from exc


def _canonical_xlsx(content):
    """Remove only serialization timestamps; never recalculate or alter cells."""
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name in sorted(source.namelist()):
                data = source.read(name)
                if name == "docProps/core.xml":
                    root = ET.fromstring(data)
                    for field in ("created", "modified"):
                        element = root.find("{http://purl.org/dc/terms/}" + field)
                        if element is not None:
                            element.text = "2000-01-01T00:00:00Z"
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.create_system = 3
                entry.external_attr = 0o600 << 16
                target.writestr(entry, data)
    return output.getvalue()


def encode(kind, data):
    capability_for(kind)
    if not isinstance(data, dict):
        raise ValueError("File content must be an object")
    if kind == "json":
        return json_bytes(data)
    cells = data.get("cells", data)
    if not isinstance(cells, dict):
        raise ValueError("XLSX cells must be a mapping of Sheet!A1 to scalar values")
    if "cells" in data and set(data) != {"cells"}:
        raise ValueError("XLSX content accepts only the cells field")
    stream = io.BytesIO()
    Workbook().save(stream)
    sheet = Spreadsheet(stream.getvalue())
    sheet.update(cells)
    # Keep the normal default sheet for an empty workbook, but avoid adding a
    # phantom deliverable sheet when all input cells name different sheets.
    if len(sheet.book.sheetnames) > 1 and not any(
        cell.value is not None for row in sheet.book["Sheet"] for cell in row
    ):
        sheet.book.remove(sheet.book["Sheet"])
    return _canonical_xlsx(sheet.serialize())


def read(kind, content, sheet=None):
    capability_for(kind)
    if kind == "json":
        if sheet is not None:
            raise ValueError("JSON does not have sheets")
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("JSON file must contain an object")
        return data
    return Spreadsheet(content).read(sheet)


def update_xlsx(content, cells):
    if not isinstance(cells, dict):
        raise ValueError("XLSX cells must be a mapping")
    sheet = Spreadsheet(content)
    sheet.update(cells)
    return _canonical_xlsx(sheet.serialize())


def recalculate_xlsx(content):
    return _canonical_xlsx(Spreadsheet(content).serialize())


def capability_tools(applications):
    """Public finite schemas. WorldCore enforces its own context and ACL checks."""
    if "spreadsheets" not in applications:
        return []
    selector = {
        "alias": {"type": "string", "description": "Alias in the bound workspace"},
        "object_id": {"type": "string", "description": "Exact object identity"},
        "work_id": {
            "type": "string",
            "description": "Exact work edition for this read or edit; no automatic replacement",
        },
    }
    result = []
    for name, description, extra, required in (
        (
            "sheet_read",
            "Read cells and evaluated values/errors from an exact XLSX version. Select alias or object_id.",
            {"version_id": {"type": "string"}, "sheet": {"type": "string"}},
            [],
        ),
        (
            "sheet_update",
            "Write at most 500 Sheet!A1 cells and evaluated formula caches as a new XLSX version. Supports arithmetic, cell/range references, SUM, MIN, MAX, ABS and ROUND; up to 2000 rows and 100 columns. Select alias or object_id.",
            {
                "cells": {
                    "type": "object",
                    "description": "Sheet!A1 keys; values are strings, finite numbers, or null. Prefix formulas with =.",
                    "additionalProperties": {"type": ["string", "number", "null"]},
                },
                "dependencies": {"type": "array", "items": {"type": "object"}},
            },
            ["cells"],
        ),
        (
            "sheet_recalculate",
            "Recalculate the bounded formula subset and store a new XLSX version, preserving formula errors. Select alias or object_id.",
            {},
            [],
        ),
    ):
        result.append(
            {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {**copy.deepcopy(selector), **extra},
                    "required": required,
                    "additionalProperties": False,
                },
            }
        )
    return result
