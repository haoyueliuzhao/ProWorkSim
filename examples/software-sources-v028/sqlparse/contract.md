# Comparison export

Shared goal: repair the upstream comparison operand regression and deliver a working consumer export. Both members have equal permissions; choose, transfer and integrate responsibilities yourselves. Either member may implement either or both changes. Two-person participation is not imposed by the correctness checker.

1. `sqlparse.sql.Comparison.right` must return the last/right operand, preserving `left`, grouping, literal spelling, parentheses and existing parsing. Fix the real library regression; keep all selected upstream tests passing.
2. Implement `consumer.comparison_records(expressions)`: for each valid single comparison expression in input order, use `sqlparse.parse` and the parsed `Comparison.left` and `.right` properties; return `[{"left": <str operand>, "right": <str operand>}, ...]`. Preserve spelling, quoting and parentheses; an empty list returns `[]`. A parsed expression that is not a single Comparison raises `ValueError`.

The consumer must use the repaired library API, not a second ad hoc parser. The library and consumer are separate deliverable files. A published patch can be exchanged and integrated; source acceptance and consumer acceptance are both required. Initial owner is unassigned for both tasks.

This task starts from a pinned SWE-smith mutation. The consumer requirement is a project-derived requirement, not an upstream issue or an official SWE-smith cooperative task. Visible selected upstream regression tests are in `test_visible.py`; `test_member.py` is available for your own tests. The official whole-repository Docker suite is outside this bounded task.
