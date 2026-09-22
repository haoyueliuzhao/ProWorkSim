"""Semantic positions independent of workbook layout; no answer computation."""

from dataclasses import asdict, dataclass

from .spreadsheet import Spreadsheet


@dataclass(frozen=True)
class LayoutMap:
    layout_id: str
    input_sheet: str = "Inputs"
    output_sheet: str = "Outputs"
    sensitivity_sheet: str = "Sensitivity"
    input_column: str = "B"
    output_column: str = "B"
    input_offset: int = 0
    output_offset: int = 0

    def public(self):
        return asdict(self)

    def address(self, reference):
        sheet, cell = reference.split("!")
        if sheet == "Inputs":
            return f"{self.input_sheet}!{self.input_column}{int(cell[1:]) + self.input_offset}"
        if sheet == "Outputs":
            return f"{self.output_sheet}!{self.output_column}{int(cell[1:]) + self.output_offset}"
        if sheet == "Sensitivity":
            return f"{self.sensitivity_sheet}!{cell}"
        return reference


def layout_for(spec):
    return LayoutMap(**(spec.get("layout") or {"layout_id": "standard"}))


class SemanticSpreadsheet(Spreadsheet):
    """Read/perturb the same actual file using semantic addresses in the grader."""

    def __init__(self, content, layout):
        super().__init__(content)
        self.layout = layout

    def value(self, reference, current_sheet=None):
        # Internal formula resolution uses real sheet names. Only explicit canonical
        # addresses from the evaluator are adapted; formula parser callbacks bypass it.
        if current_sheet is None and "!" in reference:
            prefix = reference.split("!", 1)[0]
            if prefix in ("Inputs", "Outputs", "Sensitivity"):
                reference = self.layout.address(reference.replace("$", ""))
        return super().value(reference, current_sheet)

    def update(self, cells):
        return super().update({self.layout.address(k): v for k, v in cells.items()})
