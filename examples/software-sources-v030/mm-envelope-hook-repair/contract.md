# Repair collection-envelope loading

The current implementation is intended to support both singleton and collection
envelopes but has a real defect. A public test run is performed before work and
its actual output is shown; this is supplied diagnosis feedback, not an autonomous
model discovery. Repair the application while preserving both paths.
`consumer.unpack_envelope(payload, many=False)` must use
`models.EnvelopeSchema.load`. For `many=False`, payload is `{"item": record}` and
the result is the loaded record. For `many=True`, payload is `{"items": records}`
and the result is the loaded list, including `[]`. Every record has `code` string
and `quantity` integer or integer-string; quantity becomes an int, including zero
and negative values. Public many example: pencil/"2" and paper/7 must load to
pencil/2 and paper/7; singleton clip/"9" must load to clip/9. Use the pinned
Marshmallow hook contract and retest the real failing path before delivery.

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
