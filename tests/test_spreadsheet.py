import pytest

from proworksim.compiler import create_workbook
from proworksim.designer import design
from proworksim.spreadsheet import FormulaError, Spreadsheet, arithmetic


def test_formula_subset_references_ranges_percentage_and_cycle_errors():
    sheet = Spreadsheet(create_workbook(design().to_dict()))
    sheet.update(
        {
            "Analysis!A1": 2,
            "Analysis!A2": 3,
            "Analysis!B1": "=SUM(A1:A2)*10%+ABS(-2)+MAX(2,3)",
            "Analysis!B2": "=ROUND(Outputs!B6,2)",
            "Analysis!C1": "=C2",
            "Analysis!C2": "=C1",
            "Analysis!D1": "=XLOOKUP(A1,A1,A2)",
        }
    )
    assert sheet.value("Analysis!B1") == 5.5
    assert sheet.value("Analysis!B2") == round(sheet.value("Outputs!B6"), 2)
    values = Spreadsheet(sheet.serialize()).read("Analysis")["Analysis"]
    assert "Circular" in values["C1"]["error"]
    assert "Unsupported" in values["D1"]["error"]


@pytest.mark.parametrize(
    "expression", ["2**100000000", "__import__('os')", "(1).__class__", "1/0", "1e999"]
)
def test_calculator_rejects_unbounded_or_non_numeric_expressions(expression):
    with pytest.raises(FormulaError):
        arithmetic(expression)


def test_round_uses_excel_half_away_from_zero():
    assert arithmetic("ROUND(2.5, 0)") == 3
    assert arithmetic("ROUND(-2.5, 0)") == -3
    assert arithmetic("ROUND(1.125, 2)") == 1.13
