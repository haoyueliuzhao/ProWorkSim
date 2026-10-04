# Deliver a validated ledger importer and audit report

The shared root goal is a complete in-memory ledger import service. Two members
have equal tools and the same goal; create the work decomposition and ownership
yourselves. No execution subtasks or division of labour are supplied.

Deliver `consumer.ledger_report(rows)` and reusable `models.CentsField` /
`models.LedgerSchema`. A row has required string `id` and required money `amount`.
Money input must be a string matching digits with an optional decimal point and
one or two following digits (`0`, `001.2`, `7.00` are valid; signs, whitespace,
exponents, booleans, numeric objects and >2 fractional digits are invalid).
`CentsField` loads exact nonnegative integer minor units and dumps exactly two
fractional digits without leading integer zeros. `LedgerSchema` ignores unknown
fields. The consumer uses that schema's load and dump paths, validates each row
before duplicate detection, accepts the first valid row of each id, and rejects
later valid duplicates. Invalid rows never reserve an id. Return `accepted` rows
with id and canonical amount, `rejected` entries with original `index` and reason
`invalid` or `duplicate`, and canonical `total` of accepted amounts. Preserve row
order and exact arithmetic, including large amounts. Empty input produces empty
lists and total "0.00".

Public normal example: a/1.2, b/3.45, a/8.00, c/-1 accepts a/1.20 and b/3.45,
rejects indices 2 duplicate and 3 invalid, and totals 4.65. Completion requires
both the reusable field/schema behavior and the integrated consumer behavior.

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
