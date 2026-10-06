# Build the latest-value view of a repeated-name reading feed

Deliver adapter.readings(text) and consumer.latest_readings(text), using the real
TextFSM parser and the read-only readings.template. Input is empty or lines
"reading NAME VALUE" with one ordinary space between terms and an optional final
newline. NAME is a nonempty lowercase ASCII name; VALUE is a nonnegative decimal
integer with no leading zeros except the number 0. There are no headers, invalid
lines or other whitespace cases. Repeated names are allowed, including decreases
and zero readings; this is a sequence of observations, not additive increments.

adapter.readings must instantiate textfsm.TextFSM with readings.template and call
ParseText, converting its NAME/VALUE columns to [{"name": name, "value": integer},
...] in exact record order with duplicates retained. Do not write a replacement
line parser. Each invocation starts a fresh parse; empty text returns [].

consumer.latest_readings consumes adapter.readings. For each name retain only the
last observed value, then return exactly {"latest": records_sorted_by_name,
"total": sum_of_those_latest_values}. Each latest record has name and integer
value. Sort names lexicographically; do not sort values or keep first occurrences.
For "reading oak 4\nreading pine 7\nreading oak 2", latest is oak 2 then pine 7,
and total is 9. Empty input returns {"latest": [], "total": 0}. A prior invocation
must not affect the next one. Preserve the caller's input text.

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
