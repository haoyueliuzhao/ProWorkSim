# Validate and schedule nonoverlapping room bookings

Deliver rules.validate_booking(booking) and consumer.schedule_bookings(bookings)
using the real schema package. Each booking has exactly room, start and end.
room is a nonempty lowercase ASCII name; start/end are integers (not bool).
These input shapes are guaranteed. Endpoints may violate the booking policy:
a booking is valid exactly when 0 <= start < end <= 24. Hours are abstract integer
time units; there are no dates, time zones, capacity rules or external calendars.

rules.validate_booking must use schema.Schema.validate on the whole record with
that policy and return its validated record, or None on schema.SchemaError.
Do not replace the real validation with a handwritten substitute.

consumer.schedule_bookings consumes rules.validate_booking for each input record,
in input order. Reject invalid records. Also reject a valid record if it overlaps
an already accepted booking for the same room: x.start < y.end and y.start < x.end.
Adjacent endpoints do not overlap; bookings for different rooms do not conflict.
Earlier accepted records are never evicted, even when later records start earlier.
Duplicate bookings are separate candidates, so a second identical interval conflicts.

Return exactly {"accepted": accepted_validated_records_in_input_order,
"rejected_indices": zero_based_rejected_input_indices_in_order,
"hours": sum_of_end_minus_start_for_accepted_records}. Empty input returns empty
lists and hours 0; no per-record validator invocation is required for empty input.
For oak 2..5, oak 4..6, oak 5..7, retain the first and third records, reject index 1,
and report hours 5. Preserve the original list and every original dictionary.

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
