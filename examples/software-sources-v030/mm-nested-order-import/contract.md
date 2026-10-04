# Import nested order records

Implement `consumer.import_orders(rows)` using the provided `models.OrderSchema.load`
with collection semantics. `rows` is a list of orders with external `orderId`,
`buyer.email`, and `lines` containing `sku` and integer or integer-string `qty`.
Unknown fields at each schema level are ignored. The result preserves input order
and is a list of `{"id": str, "email": str, "units": int, "skus": list[str]}`.
`units` is the sum of every line quantity, `skus` preserves every line including
repeated values, and no lines gives zero and an empty list. Empty input gives `[]`.
The existing schemas already define this load contract; integrate their returned
objects with the consumer. Public normal example: order p-1, buyer a@example.org,
lines pen/"3" and ink/2 produces units 5 and skus ["pen", "ink"].

# Shared working agreement

The task starts from a public root requirement, source code and these acceptance
criteria. There are no preassigned execution subtasks or owners. Use the visible
task board to create or revise work and responsibility if needed. A fixed delivery
is only a version to assess, not a statement that independent acceptance passed.

`test_visible.py` executes a small original upstream regression subset and separate
public normal-path examples; passing the upstream subset alone does not establish
that the consumer works. The public examples below are part of the contract.
Independent checks use different inputs and remain controller-only. Member-authored
checks can be placed in `test_member.py`. The upstream library and visible test
files are read-only. The application modules listed in the workspace are editable.
Use the real Marshmallow API required below; reimplementing schema processing by
hand is outside the contract. Preserve caller inputs. Only specified valid input
shapes and specified validation errors are in scope; no CLI, network or persistence
is required.
