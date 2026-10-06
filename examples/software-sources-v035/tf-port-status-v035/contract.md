# Parse a port-status feed and deliver its report

Deliver adapter.port_records(text) and consumer.port_report(text) using the real
TextFSM parser and the supplied read-only ports.template. Input is empty or lines
"port NAME STATE", with one ordinary space between terms and an optional final
newline. NAME is a nonempty lowercase ASCII name; STATE is up or down. There are
no headers, invalid lines, extra columns or other whitespace cases. Repeated port
names are separate observations and must be retained.

adapter.port_records must instantiate textfsm.TextFSM from ports.template and
call its ParseText method. Convert its parsed NAME/STATE columns to
[{"name": name, "state": state}, ...] in record order. Do not write a replacement
line parser. Each call starts a fresh parse; empty input returns [].

consumer.port_report consumes adapter.port_records and returns exactly
{"records": records, "up": number_of_up_records, "down": number_of_down_records}.
Keep the same records, order and duplicates; counts are integers. Preserve input
and do not retain state between calls. For "port oak up\nport pine down\nport oak up"
return those three records, up 2 and down 1. Empty text has empty records and
zero counts.

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
