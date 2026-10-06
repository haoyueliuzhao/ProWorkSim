# Validate a command batch before changing an active-name set

Deliver rules.validate_commands(commands) and
consumer.apply_commands(initial, commands), using the real schema package.
initial is a list of distinct lowercase ASCII names. Each command has exactly
op (a lowercase ASCII string) and name (a nonempty lowercase ASCII name).
The supported ops are put and drop; any other op is a policy rejection. Other
input shapes and extra fields are outside this contract. Commands may repeat.

rules.validate_commands uses schema.Schema.validate to validate the complete
list and returns the validated list, or None on schema.SchemaError if any op is
unsupported. The empty list is valid and returns []. No hand-written substitute
validator.

consumer.apply_commands first consumes that whole validated batch. If it is
rejected, return {"ok": false, "active": sorted original names} and apply none of
the commands. Otherwise process commands in order: put adds a name, drop removes
it if present. Return {"ok": true, "active": sorted final distinct names}. Empty
commands is valid. Preserve initial and commands; no hidden mutable state between
calls. For initial ["oak"], put pine then drop oak yields active ["pine"]. A put
followed by unsupported op leaves the original set intact with ok false.

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
