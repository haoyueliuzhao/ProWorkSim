# Use one stable catalog for table and lookup views

Deliver records.build_catalog(rows), report.catalog_rows(rows), and
query.lookup_many(rows, keys). The table and lookup views must call and consume
the same records.build_catalog product, not separately rebuild its semantics.
No member or role is assigned to any module.

rows is a list of dictionaries with exactly key (an ASCII string) and value
(a JSON string, integer, boolean or null). These shapes and value types are
guaranteed; floats and other shapes are outside the domain. A key may be an
invalid name. Query keys is a list of valid nonempty lowercase ASCII-letter
names, possibly empty and with repeats; missing catalog names are allowed.

records.build_catalog uses schema.Schema.validate on the whole row list. Every
key must match one or more lowercase letters a through z, without normalization.
An invalid key rejects the whole input: return None on schema.SchemaError.
Otherwise return exactly {"keys": [...], "values": [...]}. Each distinct key
occurs once in keys, ordered by its FIRST occurrence in rows. Its aligned value
is from its LAST occurrence. Preserve JSON scalar types exactly, including the
difference between false, 0 and null. Empty rows returns both lists empty and
is valid. This is a pure per-call product, with no state carried between calls.

report.catalog_rows must consume records.build_catalog and return
{"ok": true, "rows": [{"key": key, "value": value}, ...]} in catalog order.
On None return {"ok": false, "rows": []}.

query.lookup_many must consume records.build_catalog and return ok true with
matches in query-key order, preserving repeated queries. Each match is exactly
{"key": query, "found": boolean, "value": latest value or null when absent}.
A present null has found true; a missing key has found false. On rejected rows
return {"ok": false, "matches": []}, even if query keys is empty.

For rows [{"key": "b", "value": 1}, {"key": "a", "value": false},
{"key": "b", "value": null}], the catalog is keys ["b", "a"], values [null,false].
The table preserves that order. Query ["b", "x", "a", "b"] keeps those four
entries: b is found with null, x is absent with null, a is found with false, and
b is found with null again. All empty-input combinations retain these rules.

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
no CLI, network, persistent service or external producer. This is a named handoff-state variant of an already-used project-authored
organization-development root, not a new source benchmark. The existing branch
and any initial public diagnostics are environment preparation, not work or
discoveries already performed by current members. Training and independent
confirmation are outside this task purpose.
