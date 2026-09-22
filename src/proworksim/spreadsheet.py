"""A bounded, explicit XLSX formula subset; the workbook is the authority.

Supports arithmetic, cross-sheet references, ranges, SUM/MIN/MAX/ABS/ROUND.
Unsupported functions, external references and cycles are reported, never faked.
"""

import ast
import io
import math
import operator
import re
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from openpyxl import load_workbook
from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.utils.cell import range_boundaries


class FormulaError(ValueError):
    pass


BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}


def excel_round(values):
    if not 1 <= len(values) <= 2:
        raise FormulaError("ROUND expects one or two arguments")
    digits = int(values[1]) if len(values) == 2 else 0
    if abs(digits) > 15:
        raise FormulaError("ROUND precision exceeds supported range")
    try:
        return float(
            Decimal(str(values[0])).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
        )
    except InvalidOperation as exc:
        raise FormulaError("ROUND result exceeds supported precision") from exc


FUNCTIONS = {"SUM": sum, "MIN": min, "MAX": max, "ABS": lambda xs: abs(xs[0]), "ROUND": excel_round}
CELL = re.compile(r"^\$?[A-Z]{1,3}\$?[1-9][0-9]{0,5}$")


def arithmetic(expression: str, variables: dict | None = None, resolver=None):
    if len(expression) > 8000:
        raise FormulaError("Expression is too long")
    variables = variables or {}
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise FormulaError("Invalid expression") from exc
    if sum(1 for _ in ast.walk(tree)) > 500:
        raise FormulaError("Expression is too complex")

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in variables:
            value = variables[node.id]
            if type(value) not in (int, float):
                raise FormulaError("Variables must be numeric")
            return value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp) and type(node.op) in BINOPS:
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 32:
                raise FormulaError("Exponent exceeds limit")
            return BINOPS[type(node.op)](left, right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            if node.func.id == "REF" and resolver and len(node.args) == 1:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    return resolver(arg.value)
            if node.func.id in FUNCTIONS:
                values = []
                for arg in node.args:
                    value = visit(arg)
                    values.extend(value if isinstance(value, list) else [value])
                return FUNCTIONS[node.func.id](values)
        raise FormulaError("Unsupported expression or function")

    try:
        result = visit(tree)
        if isinstance(result, list) or isinstance(result, complex) or not math.isfinite(result):
            raise FormulaError("Result must be a finite number")
        return result
    except (ZeroDivisionError, OverflowError, TypeError, IndexError, RecursionError) as exc:
        raise FormulaError(str(exc)) from exc


class Spreadsheet:
    def __init__(self, content: bytes):
        self.book = load_workbook(io.BytesIO(content), data_only=False)
        self.cache = {}
        self.active = set()

    def value(self, reference: str, current_sheet: str | None = None):
        reference = reference.replace("$", "")
        if "!" in reference:
            sheet, cell = reference.rsplit("!", 1)
            sheet = sheet.strip("'").replace("''", "'")
        else:
            sheet, cell = current_sheet, reference
        if sheet not in self.book.sheetnames:
            raise FormulaError(f"Unknown sheet: {sheet}")
        if ":" in cell:
            start_col, start_row, end_col, end_row = range_boundaries(cell)
            if (end_col - start_col + 1) * (end_row - start_row + 1) > 1000:
                raise FormulaError("Range exceeds 1000 cells")
            return [
                self.value(f"{sheet}!{c.coordinate}")
                for row in self.book[sheet].iter_rows(
                    min_row=start_row, max_row=end_row, min_col=start_col, max_col=end_col
                )
                for c in row
            ]
        if not CELL.fullmatch(cell):
            raise FormulaError(f"Unsupported reference: {reference}")
        key = f"{sheet}!{cell}"
        if key in self.cache:
            return self.cache[key]
        if key in self.active:
            raise FormulaError(f"Circular reference: {key}")
        raw = self.book[sheet][cell].value
        if not isinstance(raw, str) or not raw.startswith("="):
            return raw if raw is not None else 0
        self.active.add(key)
        try:
            parts = []
            for token in Tokenizer(raw).items:
                if token.type == "OPERAND" and token.subtype == "RANGE":
                    parts.append(f"REF({token.value!r})")
                elif token.type == "OPERATOR-POSTFIX" and token.value == "%":
                    parts.append("/100")
                else:
                    parts.append(token.value.replace("^", "**"))
            value = arithmetic("".join(parts), resolver=lambda ref: self.value(ref, sheet))
            self.cache[key] = value
            return value
        finally:
            self.active.remove(key)

    def read(self, sheet: str | None = None) -> dict:
        result = {}
        sheets = [sheet] if sheet else self.book.sheetnames
        for name in sheets:
            if name not in self.book.sheetnames:
                raise FormulaError(f"Unknown sheet: {name}")
            cells = {}
            for row in self.book[name]:
                for cell in row:
                    if cell.value is None:
                        continue
                    entry = {"raw": cell.value}
                    if cell.data_type == "f":
                        try:
                            entry["value"] = self.value(f"{name}!{cell.coordinate}")
                        except (ValueError, KeyError) as exc:
                            entry["error"] = str(exc)
                    else:
                        entry["value"] = cell.value
                    cells[cell.coordinate] = entry
            result[name] = cells
        return result

    def update(self, cells: dict):
        if len(cells) > 500:
            raise ValueError("At most 500 cells per update")
        validated = []
        for ref, value in cells.items():
            if not isinstance(ref, str) or "!" not in ref:
                raise ValueError("Use Sheet!A1 cell addresses")
            sheet, cell = ref.rsplit("!", 1)
            if not CELL.fullmatch(cell) or len(sheet) > 31 or re.search(r"[\[\]:*?/\\]", sheet):
                raise ValueError("Invalid sheet or cell address")
            if not sheet or type(value) not in (str, float, int, type(None)):
                raise ValueError("Cells must contain text, numbers or null")
            if isinstance(value, (float, int)) and not math.isfinite(value):
                raise ValueError("Cells must contain finite numbers")
            if isinstance(value, str) and len(value) > 8000:
                raise ValueError("Cell text is too long")
            col, row, _, _ = range_boundaries(cell)
            if row > 2000 or col > 100:
                raise ValueError("v0.1 supports at most 2000 rows and 100 columns")
            validated.append((sheet, cell, value))
        for sheet, cell, value in validated:
            if sheet not in self.book.sheetnames:
                self.book.create_sheet(sheet)
            self.book[sheet][cell] = value
        self.cache.clear()

    def serialize(self) -> bytes:
        stream = io.BytesIO()
        self.book.save(stream)
        # Persist evaluated caches IN the XLSX. Invalid formulas keep their formula
        # and get an Excel error cache; they are legitimate worker mistakes.
        namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ET.register_namespace("", namespace)
        source = zipfile.ZipFile(io.BytesIO(stream.getvalue()))
        output = io.BytesIO()
        with source, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
            for entry in source.infolist():
                data = source.read(entry.filename)
                match = re.fullmatch(r"xl/worksheets/sheet(\d+)\.xml", entry.filename)
                if match:
                    sheet = self.book.sheetnames[int(match.group(1)) - 1]
                    root = ET.fromstring(data)
                    for cell in root.iter(f"{{{namespace}}}c"):
                        if cell.find(f"{{{namespace}}}f") is None:
                            continue
                        value_node = cell.find(f"{{{namespace}}}v")
                        if value_node is None:
                            value_node = ET.SubElement(cell, f"{{{namespace}}}v")
                        try:
                            value_node.text = str(self.value(f"{sheet}!{cell.attrib['r']}"))
                            cell.attrib.pop("t", None)
                        except (ValueError, KeyError):
                            value_node.text = "#VALUE!"
                            cell.set("t", "e")
                    data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
                target.writestr(entry, data)
        return output.getvalue()
