# Inventory API and consumer change

Both members can read, edit and test the real pinned Marshmallow source and its
inventory consumer, in separate private working copies. Decide who owns each
task and when to exchange or integrate fixed patches. Neither member is assigned
an implementation or review-only role. Either may perform the final delivery.

Add a keyword-only `strip_whitespace=False` option to `fields.String` and `Str`.
When enabled, deserialize strings and UTF-8 bytes by removing leading/trailing
Unicode whitespace. Preserve interior whitespace. Validators see the normalized
value. Default behavior, dump/serialization, invalid types and UTF-8 errors,
allow_none, required, data_key, nesting and String subclass behavior remain
compatible. Document the option in the source docstring.

Adapt `InventorySchema.sku` in `consumer.py` to opt in; preserve description
whitespace and dump behavior. The consumer must use the resulting library API.
The joint target is the library and consumer working together in one tree.

Use the lightweight task board to claim or transfer responsibility. A declared
dependency gates publishing a dependent patch until the upstream patch is in
the same tree (or both tasks are delivered in the same patch). Declaration is
optional: actual code execution determines functional dependency and correctness.
Published patches are immutable cumulative diffs against the shared baseline.
`integrate_patch` performs a real three-way merge; repair any conflict markers
in your own copy. Claims and earlier code edits keep their original author even
if task responsibility changes later.

Editable files: `src/marshmallow/fields.py`, `consumer.py`, `test_member.py`.
You may write exploratory tests to `test_member.py`. `run_tests` runs the fixed
visible examples then your tests in a fresh OS sandbox. These reports provide
feedback; private API observations are compared by the parent independently.
For delivery, publish a fixed patch of your final tree, run tests on that exact
tree and call `submit_integration`. A green report is not required to submit and
does not establish acceptance. Changes after submission do not change its tree.

This is interface development using the previous Marshmallow development asset,
not a fresh source, training task or independent confirmation task.
