# Build a SQL script inventory from the real parser

Deliver reader.statement_records(script) and report.summarize(script).
The script is empty/whitespace or a sequence of valid, flat single-table SELECT,
UPDATE and DELETE statements. SELECT projects one column or one literal; UPDATE
sets one column to a constant; an optional WHERE compares one column with one
constant. Identifiers contain ASCII letters, digits and underscores and start
with a letter. Constants are nonnegative integers or single-quoted ASCII text
without escaped quotes; text may contain spaces or semicolons. Statement keywords
may be upper/lowercase. Spaces and newlines separate tokens/statements. There
are no comments, joins, nested queries, functions, transactions or invalid SQL
acceptance cases. Statements may repeat; the last semicolon is optional.

reader.statement_records uses real sqlparse.split and sqlparse.parse, then each
parsed Statement.get_type(). Return [{"text": split_piece, "kind": kind}, ...]
in script order. split_piece is exactly the text produced by sqlparse.split
(including its retained statement semicolon and internal spelling/whitespace);
kind is SELECT, UPDATE or DELETE from the real Statement API. Do not replace
the parser with string splitting or a second parser. Empty input returns [].

report.summarize consumes reader.statement_records and returns exactly
{"statements": records, "counts": {"SELECT": n, "UPDATE": n, "DELETE": n},
 "total": number_of_records}. Keep the same records/order and duplicates. Counts
and total are integers; include all three count keys even when zero. Empty input
has empty statements, all counts zero, and total zero. Preserve caller input.

For example, "SELECT label FROM bins; UPDATE bins SET flag = 1;" produces two
records with kinds SELECT/UPDATE, counts 1/1/0, and total 2. A semicolon inside
a quoted literal is not a statement boundary.

# Work and acceptance

This is one immutable root goal, not an execution task list. Two equal members
start with private copies and no assigned tasks or owners. Create, revise, claim
and coordinate your own work as useful. One member may complete everything;
communication, two-person editing and a particular work order are not required.

Only the declared application modules and test_member.py are editable. The real
pinned library, contract, public checks and supplied grammar assets are read-only.
Public checks cover the declared semantics plus a bounded original upstream
regression subset. Private acceptance uses different inputs under the same
contract. No behavior outside the declared legal input domain is assessed.
Use the stated real API and reusable product: calling a dummy API and ignoring
its result does not implement the contract. Preserve caller inputs including
JSON scalar types. Output types are exact; floats and booleans do not substitute
for required integers. A current tested fixed submission is needed, but saving
a submission is not independent acceptance. There is no CLI, network, persistent
service or external producer to build.
