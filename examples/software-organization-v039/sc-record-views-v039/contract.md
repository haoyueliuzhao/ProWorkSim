# Provide two consistent views of canonical named records

Deliver records.build_records(rows), report.group_report(rows), and
query.select_group(rows, group). The report and query must use the same reusable
record representation produced by records.build_records, not independently
reimplement it. Either one member or any self-chosen group may complete all code.

rows is a list of dictionaries with exactly name and group, both ASCII strings;
these shapes are guaranteed. Other shapes are outside the domain. Raw strings
may be blank, mixed-case or contain punctuation. The query group argument is
already a nonempty lowercase ASCII-letter name and needs no normalization.

records.build_records uses schema.Schema.validate on the whole row list. Strip
outer whitespace and lowercase both strings. Each normalized name/group must
match one or more letters a through z; otherwise reject the entire list and
return None on schema.SchemaError. For valid input return one dictionary per row
with exactly position (original zero-based integer index), name and group, in
input order. Preserve duplicate records. Empty input returns [], not rejection.

report.group_report must call and consume records.build_records. Rejected input
returns {"ok": false, "groups": []}. Valid input returns ok true and groups as
{"group": canonical group name, "names": [canonical names]} dictionaries. Group
order is first occurrence in the records; names retain input order and duplicates
within each group. Do not sort groups or names.

query.select_group must call and consume records.build_records. Rejected input
returns {"ok": false, "matches": []}. Otherwise return ok true and matches as
{"position": original index, "name": canonical name} for every record in the
requested group, preserving original order and duplicates. Positions are not
renumbered after filtering. A missing group yields an empty matches list.

For [{"name": " Ada ", "group": "RED"}, {"name": "BOB", "group": "blue"},
{"name": "ada", "group": "red"}], build_records returns positions 0,1,2 and
names ada,bob,ada with groups red,blue,red. group_report lists red/[ada,ada] before
blue/[bob]; select_group(..., "red") returns [{"position": 0, "name": "ada"},
{"position": 2, "name": "ada"}] in matches. Both consumers accept empty rows.

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
