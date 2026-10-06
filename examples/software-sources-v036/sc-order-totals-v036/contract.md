# Validate an entire nested order and produce exact integer totals

Deliver rules.validate_order(order) and consumer.price_order(order) using the real
schema package. An order has exactly lines (a list) and discount (an integer).
Each line has exactly sku (a nonempty lowercase ASCII name), quantity (integer),
and unit_price (integer). These input shapes are guaranteed, and bool is not an
integer input. Repeated sku names are separate lines. Monetary units are abstract
integer credits; there is no currency conversion, percentage, tax or rounding.

The policy is quantity >= 1, unit_price >= 0 and discount >= 0. Empty lines is
valid. A discount larger than the subtotal is valid. rules.validate_order must
use schema.Schema.validate on the whole nested object, returning its validated
object or None on schema.SchemaError. Do not use a handwritten substitute.

consumer.price_order must consume that validated whole object. If any line or
discount is rejected, return exactly
{"ok": false, "lines": [], "subtotal": 0, "discount": 0, "due": 0}.
Do not price only the valid subset. Otherwise return ok true, lines in original
order with exactly sku, quantity, unit_price and amount=quantity*unit_price,
subtotal=sum(amount), discount unchanged, and due=max(0, subtotal-discount).
For 2 units at 5 credits and 3 units at 2 credits with discount 7, subtotal is 16
and due is 9. Preserve order, duplicates, zero-price lines and every input object.

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
Use the stated real API and reusable product; calling a dummy API and ignoring
its result does not implement the contract. Preserve caller inputs, order and
the specified JSON scalar types. Integers are exact, not floats or booleans.
There is no hidden mutable state between calls. A current tested fixed submission
is needed, but saving a submission is not independent acceptance. There is no
CLI, network, persistent service or external producer to build.
