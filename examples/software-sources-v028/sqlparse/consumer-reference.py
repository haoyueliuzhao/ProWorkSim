import sqlparse
from sqlparse.sql import Comparison


def comparison_records(expressions):
    records = []
    for expression in expressions:
        node = sqlparse.parse(expression)[0].tokens[0]
        if not isinstance(node, Comparison):
            raise ValueError("One comparison expression required")
        records.append({"left": str(node.left), "right": str(node.right)})
    return records
