# Expand grouped work items into per-group sequential timelines

Deliver adapter.work_items(text) and consumer.work_timeline(text), using the real
TextFSM parser and the read-only work.template. Input is empty or sections that
start with "group NAME", followed by one or more "item NAME MINUTES" lines.
Every group name occurs in one section only. Names are nonempty lowercase ASCII;
item names may repeat. MINUTES is a nonnegative decimal integer, with no leading
zeros except 0. Use one ordinary space between terms, no blank or invalid lines,
and an optional final newline. These are abstract work units, not clock times.

adapter.work_items must instantiate textfsm.TextFSM using work.template and call
ParseText. Its Filldown GROUP associates each item with the latest section header.
Return [{"group": group, "item": item, "minutes": integer}, ...] in item order,
including repeated items and zero durations. Header lines are not item records;
do not append a phantom item at EOF. Each call starts fresh, and empty text returns
[]. Do not replace the declared real parser with a handwritten line parser.

consumer.work_timeline consumes adapter.work_items. Each group's first item starts
at 0; subsequent items start at the preceding finish in that same group; finish is
start plus minutes. Return exactly {"steps": step_records_in_input_order,
"totals": group_totals_in_first_group_order}. A step has group, item, start, finish.
A total has group and minutes equal to that group's final finish. Do not merely
return counts or sums: every intermediate start/finish is part of the contract.
For group oak with cut 2 then paint 3, the steps are cut 0..2 and paint 2..5.
A following group pine starts its own first item at 0. Empty input returns empty
steps and totals; preserve input, item order, duplicate item names and zero steps.

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
