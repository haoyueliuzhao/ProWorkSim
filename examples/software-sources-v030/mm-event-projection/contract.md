# Export event objects through a serialization projection

Implement `consumer.export_events(rows)` using `models.EventSchema.dump` with
collection semantics. Input rows have strings `label`, `timestamp`, `owner`, and
`secret`. Timestamps are valid Python ISO datetime strings with optional timezone
and fractional seconds. Construct objects whose internal attributes are
`event_name`, `happened_at` (a datetime), `meta.owner`, and `secret`; serialize them
through the provided schema. Return dictionaries with only `title`, `at`, and
`owner`. `at` uses Python datetime ISO serialization, preserving timezone offsets
and fractional seconds. Never expose secret. Preserve order; empty input gives
`[]`. Public normal example: arrival at 2026-01-02T03:04:05+00:00 owned by Ada
exports that title, timestamp, owner and no secret.

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
