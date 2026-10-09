# Normalize label names and build a stable index

Deliver labels.normalize_labels(values) and consumer.index_labels(values).
values is a list of ASCII strings, possibly empty. Strings may contain spaces,
uppercase letters or punctuation. Other input shapes are outside the domain.

labels.normalize_labels must use schema.Schema.validate on the entire list.
For each string, strip outer whitespace and lowercase it. The normalized result
must contain only one or more letters a through z. A blank or any other character
rejects the entire list: return None on schema.SchemaError. Otherwise return the
normalized list in input order, preserving repeated names. Empty input returns
[], which is valid, not rejection. Use schema validation to produce these values.

consumer.index_labels must call and consume labels.normalize_labels. On None,
return exactly {"ok": false, "names": [], "positions": []}. Otherwise names is
the unique normalized names in order of first appearance, and positions gives
each original item's zero-based index in names. For [" Red ", "BLUE", "red"],
return {"ok": true, "names": ["red", "blue"], "positions": [0, 1, 0]}.
Empty input returns ok true with both lists empty. No sorting is requested.

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
