# Inventory import compatibility request

This is a new simulated customer request against the fixed public Marshmallow 4.3.1 codebase; it is not an upstream reported bug or a real historical maintenance task.

Add a keyword-only option `strip_whitespace=False` to `marshmallow.fields.String` (including its `Str` alias). With the option true, loading strings and valid UTF-8 bytes must remove leading/trailing Unicode whitespace while preserving interior whitespace. Decoding still happens as before; validators must see the normalized value. False or omitted preserves the existing load behavior. Dump/serialization must remain unchanged. Existing invalid type/invalid UTF-8 errors, allow_none, required, data_key, schema nesting and existing String subclasses must retain compatible behavior.

The simulated consumer `consumer.py` imports inventory records. Opt in for `InventorySchema.sku` only; preserve description whitespace and unchanged dump behavior. Add a useful source docstring description of the new option. Only `src/marshmallow/fields.py` and `consumer.py` are editable in this first bounded responsibility.

Read the relevant actual source, edit it through exact replacements, execute the visible test suite, and explicitly submit the source bundle and actual test report for review. Visible tests are incomplete examples, not an exhaustive checker. Final assessment reconstructs the submitted immutable source version and runs independent contract cases. A green visible test report and world approval alone do not prove acceptance.

Tools: read_source supports exact file paths and line windows. replace_source requires a unique exact old string and replacement; it records a new source version. run_tests executes the current bundle inside a fresh read-only Landlock/seccomp workspace, and writes `test_result` with its exact source reference. It never modifies or submits source. submit must name aliases `source` and `test_result` for work `SOFTWARE::change`. If you change source after testing, rerun tests. Editing after submission never changes that submission.
