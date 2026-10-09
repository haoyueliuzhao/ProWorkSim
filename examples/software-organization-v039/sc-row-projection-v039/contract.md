# Project records through an ordered column selection

Deliver columns.validate_columns(columns) and consumer.project_rows(rows, columns).
columns is a list of ASCII strings, possibly empty. rows is a list of dictionaries
whose keys are lowercase ASCII names and whose values are JSON strings, integers,
booleans or null. Rows need not contain all selected keys and may have other keys.
These shapes and value types are guaranteed; other shapes and floats are outside
the domain. Column strings may be invalid names and may repeat.

columns.validate_columns must use schema.Schema.validate on the whole column
list. Every column must match one or more lowercase letters a through z, with
no normalization. Duplicate names reject the whole selection. Return None on
schema.SchemaError, otherwise the validated columns in the same order. [] is a
valid selection. Do not substitute a handwritten validator.

consumer.project_rows must call and consume columns.validate_columns. On None,
return exactly {"ok": false, "columns": [], "rows": []}. Otherwise return ok true,
columns equal to that ordered list, and rows as lists of the selected values in
that order. Use null for missing keys; preserve present false, zero, empty string
and null exactly. Preserve row order and repeated rows. With an empty selection,
return one empty list per input row; with no rows, return an empty rows list but
keep the selection. For rows [{"x": 1}, {"x": 0, "y": false}] and columns ["y", "x"],
return {"ok": true, "columns": ["y", "x"], "rows": [[null, 1], [false, 0]]}.

# Work and acceptance

This is one immutable root goal, not a list of execution tasks. Equal members
have the same public materials and tools and start with private copies and an
empty task board. Choose your own work organization. A single member may finish
the whole contract; no communication, role split, recruitment, minimum task
count or editing order is required. Direct work may be published with
fix_patch(task_ids=[]). Named task bindings require actual ownership.

Only the declared application modules and test_member.py are editable. The
pinned schema library, this contract and test_visible.py are read-only. Public
checks contain stated examples and a bounded original API regression. Private
checks use different inputs within this same declared domain, not a different
contract. No behavior outside the stated input domain is assessed. All output
keys, scalar types, list order, duplicates and caller-input preservation are
part of the contract. Never mutate arguments, even on rejection. Use the actual
schema API and consume the stated shared product, not dummy calls or duplicate
substitute implementations. API-use observations are finite executed witnesses.

Run public tests on the current version, fix that same version, and actively
submit_integration. A fixed submission is not independent acceptance. There is
no CLI, network, persistent service or external producer. These tasks are new
project-authored organization-development contracts on an already pinned
upstream environment; they are not original upstream issues, training examples,
or independent-confirmation tasks.
