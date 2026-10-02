# Schema catalog export

Shared goal: repair optional-description handling and deliver a working schema catalog. Both members have equal permissions and both tasks begin unassigned. Choose responsibilities yourselves; either member may implement either or both changes.

1. Restore `schema.Schema.description`: preserve the caller's description exactly, including `None` and leading/trailing spaces. JSON Schema export must continue to work without an explicit description, preserving existing field type and required-key semantics and upstream regressions.
2. Implement `consumer.schema_catalog(specs)`. Each spec contains `name` (string), `field` (string), `kind` (one of `str`, `int`, `bool`), and `description` (string or `None`). Return one ordered record per spec: `{"name": spec["name"], "schema": <export>}`. Construct `Schema({field: matching_builtin_type}, name=name, description=description)` and obtain its JSON Schema using id `"urn:" + name`. Preserve the library output exactly; empty input returns `[]`. Use the real `Schema.json_schema` API instead of fabricating its dictionary.

Both the library fix and consumer are required. Exchange and integrate fixed patches if responsibilities are split; doing everything in one member is also a valid work route. The consumer requirement is a project derivation from the pinned SWE-smith task, not an upstream cooperative benchmark. Selected original tests in `test_visible.py` are a bounded subset, not the official full Docker suite.
