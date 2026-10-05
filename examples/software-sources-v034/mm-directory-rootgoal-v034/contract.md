# Normalize a record directory and produce its batch output

Deliver reusable `models.RecordSchema` and `consumer.catalog(records)`.
Each record has exactly `name` and `quantity`. A name is a string containing only
ASCII letters and ordinary spaces; stripping leading/trailing spaces leaves a
nonempty name. Preserve its letter case and interior spaces. Quantity is an
integer from 0 through 1000, or a nonempty string of decimal digits expressing
such an integer (leading zeros are allowed). Booleans, extra fields and every
other input shape are outside this contract and are not acceptance cases.

`RecordSchema.load` produces a fresh dictionary with the stripped name and an
integer quantity, using Marshmallow's integer conversion. `RecordSchema.dump`
serializes this loaded form to the same two fields, keeping quantity an integer.
The schema supports both one record and Marshmallow's `many=True` list behavior.

`catalog(records)` returns exactly
`{"records": [normalized records], "total_quantity": sum of their quantities}`.
Preserve input order and duplicate records. Nonempty batches must consume the
shared RecordSchema load and dump results, so the reusable API and consumer
output agree. Empty input returns `{"records": [], "total_quantity": 0}`; no
schema call is required for that shortcut. Do not mutate the input list or rows.

For example, `[{"name":" Pine ","quantity":"02"},
{"name":"Oak","quantity":3},{"name":" Pine ","quantity":"02"}]` yields
records Pine/2, Oak/3, Pine/2 in that order and total_quantity 7. This is one
complete root requirement, not a suggested division of execution work.

# Work and acceptance

The immutable root goal is shared by two equal executors. There are no assigned
execution tasks, module owners, or required communication patterns. Create and
revise your own work as useful; centralized completion and explicit publication
and import are both permitted. Each executor has a real private working copy.

The pinned Marshmallow source is read-only. Implement the named reusable schema
and application interfaces using its real API. `test_visible.py` checks the
public semantics below plus the same small upstream regression subset. Public
checks do not expose independent inputs or establish independent acceptance.
The full result requires the reusable API and all consumer results to agree with
this contract, along with unchanged caller inputs. Add exploratory checks only
to `test_member.py`. There is no CLI, filesystem service, network or persistence
to implement. No behavior outside the legal input domain below is assessed.
A fixed submission requires current-version public test execution and a fixed
patch; neither tool invocation nor submission implies acceptance.
