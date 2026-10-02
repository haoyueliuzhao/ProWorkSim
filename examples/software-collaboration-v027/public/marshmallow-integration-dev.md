# Composing String normalization features

Both members have stable identities and separate private copies of pinned
Marshmallow source. Both may edit and test every declared editable path. Choose
the division of work, scheduling and integration yourselves using the task board.

The `whitespace` task adds keyword-only `strip_whitespace=False` to `fields.String`
and `Str`. Enabled loading strips leading/trailing Unicode whitespace from str
and valid UTF-8 bytes; validators see normalized values. Document the option.
Adapt `InventorySchema.sku` in `consumer.py` to opt in, preserving description
whitespace and unchanged dump behavior.

The `casefold` task adds keyword-only `casefold=False` to the same String class.
Enabled loading uses Python Unicode `str.casefold()` on decoded text. It is
independent of the whitespace option: casefold alone preserves edge whitespace.
When both options are enabled, both transformations take effect before validation.
Document the option. Defaults preserve existing strings; dump/serialization,
invalid type and invalid UTF-8 errors, allow_none, required, nesting and String
subclass behavior remain compatible. Consumer casefold remains disabled.

Both requirements modify a shared API. Passing a separate feature on each
member's patch does not prove the combined implementation works. Deliver one
tree containing both features and the consumer behavior; private acceptance
executes the combined tree and checks their interaction and regressions.

Editable files: `src/marshmallow/fields.py`, `consumer.py`, `test_member.py`.
Read files, use exact replacements or write editable files, inspect unified
diffs, publish immutable patches and exchange them. Real three-way merging may
write conflict markers, which you must resolve. Responsibility transfers do not
rewrite historical authors. Optional task dependencies gate patch publication
until the upstream patch is integrated or included in the same delivery.

`run_tests` runs fixed visible examples and your optional `test_member.py` inside
the existing OS sandbox. Fixed visible tests cannot be edited. Publish a fixed
patch, run actual tests on that exact tree and `submit_integration`; the parent
independently compares private API outputs, not model or unittest success claims.
Either member can deliver. No approval/adoption metadata is needed.

This reused development source and test family is only for interface development;
it is not new training support or independent confirmation.
