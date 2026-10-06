# Parse batch values and produce ordered per-batch totals

Deliver adapter.batch_values(text) and consumer.batch_totals(text) using real
TextFSM and the supplied read-only batches.template. Input is empty or lines
"batch NAME" and "value N", one ordinary space between terms and optional final
newline. NAME is a nonempty lowercase ASCII name; N is a single digit 0..9. Every
value follows a batch header. Headers can repeat or have no following values.
There are no malformed lines, extra columns or other whitespace cases.

adapter.batch_values instantiates textfsm.TextFSM from batches.template and
calls ParseText. Convert its BATCH/VALUE columns into
[{"batch": name, "value": integer}, ...] in encounter order, keeping repeated
values. Use the parser's Filldown result to associate each value with its header;
no hand-written line parser. A fresh parser is needed for each call.

consumer.batch_totals consumes adapter.batch_values and returns one record per
batch with at least one value, in first-value encounter order:
[{"batch": name, "count": integer_count, "total": integer_sum}, ...]. Repeated
headers of the same name contribute to the same batch. Empty text or headers
without values returns []. Preserve caller input; no state between calls.
For "batch oak\nvalue 2\nbatch pine\nvalue 3\nbatch oak\nvalue 2", return
oak/count2/total4 then pine/count1/total3.

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
Use the stated real API and reusable product: calling a dummy API and ignoring
its result does not implement the contract. Preserve caller inputs including
JSON scalar types. Output types are exact; floats and booleans do not substitute
for required integers. A current tested fixed submission is needed, but saving
a submission is not independent acceptance. There is no CLI, network, persistent
service or external producer to build.
