# Repair nested validation-error reporting

Repair `consumer.validate_people(rows)`. An actual public test run against the
initial code is supplied before work; its failure comes from current application
code. Use `models.PersonSchema.load` per row. Valid rows appear in `accepted` as
loaded dictionaries (`fullName` becomes `name`, postal becomes int, unknown fields
are excluded). Rejected rows contribute only `{"index": zero_based_input_index,
"fields": sorted_leaf_paths}` to `rejected`; exclude partially valid records.
Error leaf paths follow Marshmallow's external error-tree keys, joined with dots.
For example, invalid postal inside address is `address.postal`, not `address`;
missing fullName is `fullName`. Preserve accepted and rejected input order.
Public example: Ari with postal "123"/North is accepted; Pat with postal "bad"/West
is rejected at index 1 with fields ["address.postal"]. Empty input gives two empty
lists. Repair and rerun the observed failing path.

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
